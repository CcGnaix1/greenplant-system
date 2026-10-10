"""识别准确率测试 —— 在**未参与训练**的验证集上评估推理服务实际加载的 ONNX 模型。

为什么要单独写这个脚本，而不是直接用 ml/evaluate.py：
    evaluate.py 在全部 2708 张图上评估，其中 2166 张是训练集，准确率会虚高到 ~0.99。
    那个数字不能用来论证泛化能力。train.py 用 random_split(seed=42, train_split=0.8)
    划分了训练/验证集，本脚本复现**完全相同**的切分，只评估其中的验证集
    （542 张，训练时从未被模型见过），得到的才是可信的泛化准确率。

评估对象是 output/plant_model.onnx —— 即 FastAPI 推理服务真正加载的文件，
不是 best_model.pth。预处理直接复用 service/recognizer.py 的 build_val_transform，
保证与服务线上路径逐字节一致（自己手写 resize 极易引入肉眼不可见的偏移）。

用法：
    C:/Plant/plant-ai/venv/Scripts/python.exe tests/accuracy_test.py
    C:/Plant/plant-ai/venv/Scripts/python.exe tests/accuracy_test.py --no-parity   # 跳过 pth 对比
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # C:/Plant
AI = ROOT / "plant-ai"
ML_DIR = AI / "ml"
SERVICE_DIR = AI / "service"
RESULT_DIR = Path(__file__).resolve().parent / "results"

# 与 train.py 的 TrainConfig 保持一致，改一处必须改两处
SEED = 42
TRAIN_SPLIT = 0.8
IMAGE_SIZE = 224
TOP_K = 3
# 训练侧报告的验证准确率，用于校验「评估复现」与「训练日志」是否一致。
# 注意要按被测模型填：初版模型 0.9096；室内微调后为 0.9225。
# 可用 --baseline 覆盖，避免换模型后这里变成误导性的硬编码。
DEFAULT_BASELINE = 0.9096

for _p in (str(ML_DIR), str(SERVICE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import onnxruntime as ort  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402
from sklearn.metrics import classification_report, confusion_matrix  # noqa: E402
from torch.utils.data import random_split  # noqa: E402

from dataset import PlantDataset  # noqa: E402  ml/dataset.py
from recognizer import build_val_transform  # noqa: E402  service/recognizer.py

# Windows 控制台默认 GBK，中文品种名直接 print 有风险，统一成 utf-8 并容错
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def reproduce_val_split(data_dir: Path, seed: int = SEED, train_split: float = TRAIN_SPLIT):
    """复现 train.py 的验证集下标。

    必须走一个真实的 random_split 而不是自己 torch.randperm —— random_split 内部
    如何切分属于实现细节，直接读它返回的 indices 才能保证与训练时逐样本一致。
    """
    full = PlantDataset(str(data_dir))
    n = len(full)
    if n == 0:
        raise SystemExit(f"数据集为空：{data_dir}")
    train_size = int(n * train_split)
    val_size = n - train_size
    gen = torch.Generator().manual_seed(seed)
    _, val_subset = random_split(full, [train_size, val_size], generator=gen)
    return full, list(val_subset.indices)


def infer_onnx(paths, transform, model_path: Path, labels: list) -> np.ndarray:
    """逐张跑 ONNX，返回 (N, num_classes) 的概率矩阵。"""
    sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    probs = []
    for i, p in enumerate(paths, 1):
        img = np.array(Image.open(p).convert("RGB"))
        x = transform(image=img)["image"].unsqueeze(0).numpy().astype(np.float32)
        logits = sess.run(None, {"input": x})[0][0]
        e = np.exp(logits - logits.max())
        probs.append(e / e.sum())
        if i % 100 == 0:
            print(f"  ONNX 推理 {i}/{len(paths)}")
    return np.array(probs)


def infer_torch(paths, transform, model_path: Path, num_classes: int) -> np.ndarray:
    """同一批图跑 PyTorch 权重，用于校验 ONNX 导出是否失真。"""
    from train import create_model  # ml/train.py

    model = create_model(num_classes, pretrained=False)
    model.load_state_dict(torch.load(str(model_path), map_location="cpu"))
    model.eval()

    probs = []
    with torch.no_grad():
        for i, p in enumerate(paths, 1):
            img = np.array(Image.open(p).convert("RGB"))
            x = transform(image=img)["image"].unsqueeze(0).float()
            probs.append(torch.softmax(model(x), dim=1)[0].numpy())
            if i % 100 == 0:
                print(f"  PyTorch 推理 {i}/{len(paths)}")
    return np.array(probs)


def topk_accuracy(probs: np.ndarray, labels: np.ndarray, k: int) -> tuple:
    rank = np.argsort(probs, axis=1)[:, ::-1][:, :k]
    hit = np.array([labels[i] in rank[i] for i in range(len(labels))])
    return float(hit.mean()), int(hit.sum())


def most_confused(cm: np.ndarray, names: list, top_n: int = 8) -> list:
    """挑出最容易被搞混的类别对（不含对角线）。"""
    pairs = []
    for i in range(len(names)):
        for j in range(len(names)):
            if i != j and cm[i, j] > 0:
                pairs.append((int(cm[i, j]), names[i], names[j]))
    pairs.sort(reverse=True)
    return pairs[:top_n]


def main():
    parser = argparse.ArgumentParser(description="验证集准确率测试")
    parser.add_argument("--data_dir", default=str(AI / "data" / "plants"))
    parser.add_argument("--model", default=str(AI / "output" / "plant_model.onnx"))
    parser.add_argument("--labels", default=str(AI / "output" / "labels.json"))
    parser.add_argument("--pth", default=str(AI / "output" / "best_model.pth"))
    parser.add_argument("--baseline", type=float, default=DEFAULT_BASELINE,
                        help="训练侧报告的 val_acc，用于校验复现是否一致（初版 0.9096 / 微调后 0.9225）")
    parser.add_argument("--no-parity", action="store_true", help="跳过 ONNX 与 pth 的一致性校验")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    model_path = Path(args.model)
    pth_path = Path(args.pth)

    for p in (data_dir, model_path, Path(args.labels)):
        if not p.exists():
            raise SystemExit(f"缺少必要文件: {p}")

    with open(args.labels, "r", encoding="utf-8") as f:
        label_meta = json.load(f)
    class_names = [x["name"] for x in label_meta]

    print("=" * 72)
    print("识别准确率测试 —— 验证集（未参与训练）")
    print("=" * 72)
    print(f"模型文件   : {model_path}")
    print(f"数据目录   : {data_dir}")

    full, val_indices = reproduce_val_split(data_dir)
    val_paths = [full.samples[i][0] for i in val_indices]
    val_labels = np.array([full.samples[i][1] for i in val_indices])

    print(f"全量样本   : {len(full)} 张 / {len(full.classes)} 类")
    print(f"训练集     : {len(full) - len(val_indices)} 张（index {0}..{len(full) - len(val_indices) - 1} 区间）")
    print(f"验证集     : {len(val_indices)} 张 ← 本次评估对象")
    print()

    if full.classes != class_names:
        print("警告: 目录类别顺序与 labels.json 不一致，标签映射可能错位")
        print(f"  目录: {full.classes}")
        print(f"  labels: {class_names}")

    transform = build_val_transform(IMAGE_SIZE)

    print("[1/3] ONNX 推理（推理服务实际加载的模型）")
    probs = infer_onnx(val_paths, transform, model_path, label_meta)

    top1_acc, top1_hit = topk_accuracy(probs, val_labels, 1)
    top3_acc, top3_hit = topk_accuracy(probs, val_labels, TOP_K)

    print()
    print("[2/3] 指标计算")
    print("-" * 72)
    print(f"Top-1 准确率 : {top1_acc:.4f}  ({top1_hit}/{len(val_labels)})")
    print(f"Top-3 准确率 : {top3_acc:.4f}  ({top3_hit}/{len(val_labels)})")
    diff = abs(top1_acc - args.baseline)
    print(f"训练侧报告   : {args.baseline:.4f}  (--baseline)")
    print(f"对比差异     : {diff:.4f}  → {'一致' if diff < 0.01 else '不一致，需排查切分或预处理'}")
    print()

    preds = probs.argmax(axis=1)
    print("各类别 精确率/召回率/F1:")
    print("-" * 72)
    report_str = classification_report(
        val_labels, preds, labels=list(range(len(class_names))),
        target_names=class_names, digits=4, zero_division=0,
    )
    print(report_str)

    cm = confusion_matrix(val_labels, preds, labels=list(range(len(class_names))))
    confused = most_confused(cm, class_names)
    if confused:
        print("最易混淆的类别对（真实 → 误判，次数）:")
        print("-" * 72)
        for cnt, a, b in confused:
            print(f"  {a} → {b}: {cnt} 次")
        print()

    # 误判样本明细，便于答辩时翻查具体图片
    wrong = [
        {
            "image": str(val_paths[i]),
            "true": class_names[int(val_labels[i])],
            "pred": class_names[int(preds[i])],
            "confidence": round(float(probs[i].max()), 4),
        }
        for i in range(len(val_labels)) if preds[i] != val_labels[i]
    ]

    parity = None
    if not args.no_parity:
        print("[3/3] ONNX 与 best_model.pth 一致性校验（验证导出未失真）")
        print("-" * 72)
        t_probs = infer_torch(val_paths, transform, pth_path, len(class_names))
        agree = float((t_probs.argmax(axis=1) == probs.argmax(axis=1)).mean())
        max_diff = float(np.abs(t_probs - probs).max())
        t_acc, _ = topk_accuracy(t_probs, val_labels, 1)
        print(f"预测一致率       : {agree:.4f}  (两者 argmax 相同的样本占比)")
        print(f"最大概率偏差     : {max_diff:.6f}")
        print(f"PyTorch Top-1    : {t_acc:.4f}   (ONNX {top1_acc:.4f})")
        print(f"结论             : {'导出保真' if agree > 0.99 else '存在偏差，需检查导出配置'}")
        print()
        parity = {
            "prediction_agreement": round(agree, 6),
            "max_prob_diff": round(max_diff, 8),
            "torch_top1": round(t_acc, 6),
        }
    else:
        print("[3/3] 跳过一致性校验（--no-parity）")
        print()

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "model": str(model_path),
        "dataset": {"total": len(full), "val_size": len(val_indices), "num_classes": len(class_names)},
        "split": {"seed": SEED, "train_split": TRAIN_SPLIT},
        "top1_accuracy": round(top1_acc, 6),
        "top3_accuracy": round(top3_acc, 6),
        "baseline_val_acc": args.baseline,
        "diff_vs_baseline": round(diff, 6),
        "per_class_report": report_str,
        "confusion_pairs": [{"count": c, "true": a, "pred": b} for c, a, b in confused],
        "misclassified_count": len(wrong),
        "parity": parity,
    }
    with open(RESULT_DIR / "accuracy_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    with open(RESULT_DIR / "per_class.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["品种", "精确率", "召回率", "F1", "样本数"])
        rep = classification_report(
            val_labels, preds, labels=list(range(len(class_names))),
            target_names=class_names, digits=4, zero_division=0, output_dict=True,
        )
        for name in class_names:
            m = rep[name]
            w.writerow([name, f"{m['precision']:.4f}", f"{m['recall']:.4f}",
                        f"{m['f1-score']:.4f}", int(m["support"])])

    with open(RESULT_DIR / "confusion_matrix.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["真实\\预测"] + class_names)
        for i, name in enumerate(class_names):
            w.writerow([name] + [int(v) for v in cm[i]])

    with open(RESULT_DIR / "misclassified.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["图片", "真实品种", "预测品种", "置信度"])
        for r in wrong:
            w.writerow([r["image"], r["true"], r["pred"], r["confidence"]])

    print("结果已保存:")
    for name in ("accuracy_result.json", "per_class.csv", "confusion_matrix.csv", "misclassified.csv"):
        print(f"  {RESULT_DIR / name}")


if __name__ == "__main__":
    main()
