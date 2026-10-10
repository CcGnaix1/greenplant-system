"""测试时增强（TTA）的增益测量 —— 不重训，只多推几次取平均。

思路
----
同一张图在推理时做多种轻微变换（水平翻转、轻微缩放），各自算 softmax 后平均，
再取 argmax。多视角平均能压掉单视角的偶然错误，通常 +0.5~2 点，代价是推理变慢。

为什么先量再上线
----------------
TTA 不是稳赚的：若模型已经很稳、或各视角高度相关，增益可能接近 0，
而推理耗时按视角数线性增长。所以先在**未参与选优的室内测试集**上量出真实增益，
再决定要不要并入 `recognizer.py`。

预处理必须与 recognizer.build_val_transform 同族
----------------------------------------------
基准视角刻意复刻它（Resize(int(size*1.14)) + CenterCrop(size)），
否则量到的增益里混着「换了预处理」的效应，不可归因。
"""

import argparse
import json
import sys
from pathlib import Path

import albumentations as A
import numpy as np
import torch
from albumentations.pytorch import ToTensorV2
from PIL import Image
from torch.utils.data import DataLoader, Subset

ROOT = Path("C:/Plant/plant-ai")
sys.path.insert(0, str(ROOT / "ml"))

from dataset import IMAGENET_MEAN, IMAGENET_STD, PlantDataset  # noqa: E402
from train import create_model                                 # noqa: E402
from train30 import ORIGINAL_20, stratified_split              # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SEED = 42
SIZE = 320
BASE_R = int(SIZE * 1.14)          # 与 recognizer 一致的 364


def make_tf(r, flip: bool):
    ops = [A.Resize(r, r)]
    if flip:
        ops.append(A.HorizontalFlip(p=1.0))
    ops += [A.CenterCrop(SIZE, SIZE),
            A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
            ToTensorV2()]
    return A.Compose(ops)


# 视角集合：基准 / 翻转让 / 缩小看整体 / 放大看细节，各自再带一次翻转
VIEWS = {
    "基准":      make_tf(BASE_R, False),
    "基准+翻转": make_tf(BASE_R, True),
    "缩小":      make_tf(int(BASE_R * 0.88), False),
    "缩小+翻转": make_tf(int(BASE_R * 0.88), True),
    "放大":      make_tf(int(BASE_R * 1.12), False),
    "放大+翻转": make_tf(int(BASE_R * 1.12), True),
}


@torch.no_grad()
def probs_for(model, paths, tf, device, bs=32):
    """返回 (n, C) 的 softmax 概率。"""
    out = []
    model.eval()
    for i in range(0, len(paths), bs):
        arrs = []
        for p in paths[i:i + bs]:
            img = np.array(Image.open(p).convert("RGB"))
            arrs.append(tf(image=img)["image"])
        x = torch.stack(arrs).to(device)
        out.append(torch.softmax(model(x), dim=1).cpu().numpy())
    return np.concatenate(out, axis=0)


def acc(probs, y):
    return float((probs.argmax(1) == y).mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "output_v30_320" / "best_model.pth"))
    ap.add_argument("--out", default="C:/Plant/tests/results/tta_eval.json")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ds = PlantDataset(str(ROOT / "data" / "plants_indoor"))
    classes = ds.classes
    _, _, test_i = stratified_split(ds, (0.70, 0.15, 0.15), SEED)
    paths = [ds.samples[i][0] for i in test_i]
    y = np.array([ds.samples[i][1] for i in test_i])
    idx20 = [i for i, c in enumerate(classes) if c in ORIGINAL_20]

    model = create_model(len(classes), pretrained=False)
    model.load_state_dict(torch.load(args.model, map_location="cpu", weights_only=True))
    model = model.to(device)

    print("=" * 78)
    print(f"TTA 增益测量（室内测试集 {len(paths)} 张，320 分辨率，{device}）")
    print("=" * 78)

    single = {}
    for name, tf in VIEWS.items():
        p = probs_for(model, paths, tf, device)
        single[name] = p
        print(f"  单视角 {name:10s} 准确率 {acc(p, y):.4f}")

    base = single["基准"]
    print(f"\n{'组合':28s} {'准确率':>8s} {'较基准':>8s}")
    print("-" * 78)

    combos = {
        "基准":                          ["基准"],
        "基准+翻转":                     ["基准", "基准+翻转"],
        "基准+翻转+缩小":                ["基准", "基准+翻转", "缩小", "缩小+翻转"],
        "全部 6 视角":                   list(VIEWS.keys()),
        "基准+缩小":                     ["基准", "缩小"],
        "基准+缩小+放大":                ["基准", "缩小", "放大"],
        "基准+缩小+放大+各自翻转":        list(VIEWS.keys()),
    }
    results = {}
    for label, names in combos.items():
        blend = np.mean([single[n] for n in names], axis=0)
        a = acc(blend, y)
        results[label] = a
        print(f"{label:28s} {a:8.4f} {a - acc(base, y):+8.4f}")

    # 原20类 / 新增10类 的细分（确认 TTA 不是只帮某一部分）
    best_label = max(results, key=results.get)
    best_probs = np.mean([single[n] for n in combos[best_label]], axis=0)
    print(f"\n最优组合「{best_label}」细分：")
    for tag, idxs in (("原20类", idx20),
                      ("新增10类", [i for i in range(len(classes)) if i not in idx20])):
        m = np.isin(y, idxs)
        print(f"  {tag:8s} n={int(m.sum()):4d}  基准 {acc(base[m], y[m]):.4f}"
              f"  →  TTA {acc(best_probs[m], y[m]):.4f}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({
        "size": SIZE, "n": len(paths),
        "single_view": {k: acc(v, y) for k, v in single.items()},
        "combos": results,
        "baseline": acc(base, y),
        "best": best_label,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n写入 {args.out}")
    print(f"\n结论：最优是「{best_label}」，{acc(base, y):.4f} → {results[best_label]:.4f}"
          f"（{results[best_label] - acc(base, y):+.4f}）")


if __name__ == "__main__":
    main()
