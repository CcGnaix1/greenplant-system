"""ONNX + CPU 推理基准测试 —— 测量各模型的单视角 / TTA 延迟。

用途
----
回答「在 CPU 部署目标上，哪个骨干网划算」这个问题。
GPU 上的性价比排序不能直接搬到 CPU 上：ResNet-50 在 GPU 上很快，
在 CPU 上是 EfficientNet-B0 的 3 倍耗时却精度更低。

用法
----
    # 只测已部署的两个模型（output/ 与 output_symptom/）
    python tests/bench_cpu_onnx.py

    # 额外导出候选骨干网做横向对比（需要 torch + torchvision + onnx）
    python tests/bench_cpu_onnx.py --candidates

    # 指定线程数（默认对比 1 / 4 / 默认）
    python tests/bench_cpu_onnx.py --threads 4

说明
----
* 路径全部相对本脚本计算，**不依赖 C:/Plant/plant-ai**（本包内其它多数测试脚本会写死）。
* 候选骨干网的权重是随机初始化的 —— 这不影响延迟：推理耗时只取决于网络结构，
  与权重数值无关。只有精度指标才需要真权重。
* 结果受机器负载影响，脚本对每项取多轮中位数的最小值以降低噪声，
  但**请把它当相对比较用，不要当绝对性能承诺**。
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parent.parent
RUNS = 15
ROUNDS = 3
WARMUP = 3


def median_latency(session, in_name: str, shape: tuple[int, ...]) -> float:
    """返回一次 session.run 的中位延迟（毫秒）。"""
    x = np.random.rand(*shape).astype(np.float32)
    for _ in range(WARMUP):
        session.run(None, {in_name: x})
    ts = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        session.run(None, {in_name: x})
        ts.append((time.perf_counter() - t0) * 1000)
    return float(np.median(ts))


def make_session(path: Path, threads: int) -> tuple[ort.InferenceSession, str]:
    so = ort.SessionOptions()
    if threads > 0:
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
    sess = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
    return sess, sess.get_inputs()[0].name


def onnx_disk_size(path: Path) -> float:
    """ONNX 体积（MB）。

    大模型的权重可能被 torch 存成外部数据文件（<model>.onnx.data），
    只看 .onnx 主文件会得到 0 MB 这种误导性结果，所以要把同名前缀的文件一起算。
    """
    total = 0
    for f in [path, Path(str(path) + ".data")]:
        if f.is_file():
            total += f.stat().st_size
    return total / 1024 / 1024


def measure(path: Path, threads: int) -> dict:
    """测量单个 ONNX 模型的单视角与 TTA(×3) 延迟。"""
    sess, in_name = make_session(path, threads)
    inp = sess.get_inputs()[0]
    size = inp.shape[-1] if isinstance(inp.shape[-1], int) else None
    out = sess.get_outputs()[0]
    n_cls = out.shape[-1] if isinstance(out.shape[-1], int) else None

    info = {
        "path": path,
        "size": size,
        "classes": n_cls,
        "mb": onnx_disk_size(path),
        "single": None,
        "tta": None,
        "tta_note": "",
    }
    if size is None:
        info["tta_note"] = "输入尺寸动态，跳过"
        return info

    try:
        info["single"] = min(
            median_latency(sess, in_name, (1, 3, size, size)) for _ in range(ROUNDS)
        )
    except Exception as e:  # noqa: BLE001
        info["tta_note"] = f"单视角失败: {str(e)[:40]}"
        return info

    try:
        info["tta"] = min(
            median_latency(sess, in_name, (3, 3, size, size)) for _ in range(ROUNDS)
        )
    except Exception:  # noqa: BLE001
        info["tta_note"] = "不支持动态 batch（无法一次喂 3 视角）"

    return info


def deployed_models() -> list[tuple[str, Path]]:
    return [
        ("品种模型 EfficientNet-B0", ROOT / "output" / "plant_model.onnx"),
        ("症状模型 MobileNetV3-L", ROOT / "output_symptom" / "plant_symptom.onnx"),
    ]


def build_candidate(arch: str, num_classes: int, size: int):
    """构造候选骨干网（随机权重）并替换分类头，返回 eval 模式的模型。"""
    import torch
    from torchvision import models

    if arch == "mobilenet_v3_large":
        m = models.mobilenet_v3_large(weights=None)
        m.classifier[-1] = torch.nn.Linear(m.classifier[-1].in_features, num_classes)
    elif arch == "efficientnet_b0":
        m = models.efficientnet_b0(weights=None)
        m.classifier[-1] = torch.nn.Linear(m.classifier[-1].in_features, num_classes)
    elif arch == "resnet50":
        m = models.resnet50(weights=None)
        m.fc = torch.nn.Linear(m.fc.in_features, num_classes)
    elif arch == "convnext_tiny":
        m = models.convnext_tiny(weights=None)
        m.classifier[-1] = torch.nn.Linear(m.classifier[-1].in_features, num_classes)
    elif arch == "vit_b_16":
        m = models.vit_b_16(weights=None, image_size=size)
        m.heads.head = torch.nn.Linear(m.heads.head.in_features, num_classes)
    else:
        raise SystemExit(f"未知架构: {arch}")
    return m.eval()


CANDIDATES = ["mobilenet_v3_large", "efficientnet_b0", "resnet50", "convnext_tiny", "vit_b_16"]


def measure_candidates(threads: int, size: int, num_classes: int, out_dir: Path) -> list[tuple[str, dict]]:
    import torch

    # torch >= 2.6 的 torch.onnx.export 默认走 dynamo 新导出器，需要额外安装 onnxscript，
    # 而且导出的是静态 batch。显式关掉 dynamo 走旧导出器：既免掉这个依赖，
    # 也保证 dynamic_axes 真正生效（否则 TTA 的 batch=3 会报维度错误）。
    # torch < 2.6 不认识 dynamo 参数，所以探测一下再传。
    export_kwargs = {}
    try:
        import inspect

        if "dynamo" in inspect.signature(torch.onnx.export).parameters:
            export_kwargs["dynamo"] = False
    except (TypeError, ValueError):
        pass

    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for arch in CANDIDATES:
        path = out_dir / f"{arch}.onnx"
        model = build_candidate(arch, num_classes, size)
        # 清掉上一轮的残留：torch 可能把权重写成外部数据文件，不删会读到旧的
        for stale in [path, Path(str(path) + ".data")]:
            if stale.is_file():
                stale.unlink()
        torch.onnx.export(
            model,
            torch.randn(1, 3, size, size),
            str(path),
            opset_version=17,
            input_names=["input"],
            output_names=["output"],
            dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
            **export_kwargs,
        )
        n_params = sum(p.numel() for p in model.parameters()) / 1e6
        info = measure(path, threads)
        info["params"] = n_params
        results.append((arch, info))
    return results


def fmt(v: float | None) -> str:
    return f"{v:.1f} ms" if v else "—"


def main() -> int:
    ap = argparse.ArgumentParser(description="ONNX + CPU 推理基准测试")
    ap.add_argument("--candidates", action="store_true",
                    help="额外导出候选骨干网做横向对比（需要 torch/torchvision/onnx）")
    ap.add_argument("--threads", type=int, default=4,
                    help="intra_op_num_threads，0 表示用 onnxruntime 默认值")
    ap.add_argument("--size", type=int, default=320, help="候选骨干网的测试分辨率")
    ap.add_argument("--classes", type=int, default=42, help="候选骨干网的类别数")
    ap.add_argument("--out-dir", default=str(Path(tempfile.gettempdir()) / "plant_arch_bench"),
                    help="候选 ONNX 的导出目录（默认放系统临时目录，避免几百 MB 落进仓库）")
    args = ap.parse_args()

    print(f"onnxruntime {ort.__version__} | 逻辑核数 {os.cpu_count()} | "
          f"intra_op={args.threads if args.threads else '默认'}\n")

    print("## 已部署模型\n")
    print("| 模型 | 输入 | 类别 | 单视角 | TTA(×3) | 备注 |")
    print("|---|---|---|---|---|---|")
    for tag, path in deployed_models():
        if not path.is_file():
            print(f"| {tag} | — | — | — | — | 文件不存在: {path} |")
            continue
        info = measure(path, args.threads)
        ratio = f"{info['tta'] / info['single']:.1f}×" if info["tta"] and info["single"] else ""
        note = info["tta_note"] or (f"TTA 是单视角的 {ratio}" if ratio else "")
        print(f"| {tag} | {info['size']} | {info['classes']} | {fmt(info['single'])} | "
              f"{fmt(info['tta'])} | {note} |")

    if args.candidates:
        print(f"\n## 候选骨干网（@{args.size}，{args.classes} 类，随机权重）\n")
        print("| 骨干网 | 参数量 | ONNX | 单视角 | TTA(×3) | 备注 |")
        print("|---|---|---|---|---|---|")
        try:
            results = measure_candidates(args.threads, args.size, args.classes, Path(args.out_dir))
        except ImportError as e:
            print(f"| — | — | — | — | — | 缺少依赖: {e} |")
            return 1
        for arch, info in results:
            ratio = f"{info['tta'] / info['single']:.1f}×" if info["tta"] and info["single"] else ""
            note = info["tta_note"] or (f"TTA 是单视角的 {ratio}" if ratio else "")
            print(f"| {arch} | {info.get('params', 0):.1f} M | {info['mb']:.0f} MB | "
                  f"{fmt(info['single'])} | {fmt(info['tta'])} | {note} |")
        print(f"\n候选 ONNX 已导出到: {args.out_dir}")

    print("\n> 权重随机初始化不影响延迟（耗时只取决于网络结构）。")
    print("> 数值受机器负载影响，请作相对比较用。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
