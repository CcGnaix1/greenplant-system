"""分辨率归因：把「提分辨率」的收益拆成「训练分辨率」与「推理分辨率」两部分。

为什么必须做这个
----------------
320 那轮相比 224 基线涨了约 2.7 个点（测试集 0.8899 → 0.9170）。但两次热启动的
**起点不同**：224 轮从 20 类模型起（丢弃分类头），320 轮从已收敛的 30 类模型起。
所以不能直接把差值全算成分辨率的功劳 —— 起点更好也可能贡献一部分。

交叉评估能拆开：
    模型(224 训) × 输入224    基线
    模型(224 训) × 输入320    → 涨了说明「只是推理分辨率」的功劳，不训练也能拿
    模型(320 训) × 输入224    → 掉很多说明模型学到了 320 特有的特征（不可回退）
    模型(320 训) × 输入320    最终值

切分与 get_val_transforms 与 train30.py 完全一致，测试集不参与任何选优。
"""

import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Subset

ROOT = Path("C:/Plant/plant-ai")
sys.path.insert(0, str(ROOT / "ml"))

from dataset import PlantDataset, get_val_transforms   # noqa: E402
from train import create_model                         # noqa: E402
from train30 import ORIGINAL_20, stratified_split      # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SEED = 42
MODELS = {
    "224训": ROOT / "output_v30" / "best_model.pth",
    "320训": ROOT / "output_v30_320" / "best_model.pth",
}
RESOLUTIONS = (224, 320)


@torch.no_grad()
def acc(model, loader, device):
    model.eval()
    correct = total = 0
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        correct += int((model(images).argmax(1) == labels).sum().item())
        total += labels.size(0)
    return correct / total if total else 0.0


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    classes = PlantDataset(str(ROOT / "data" / "plants_indoor")).classes
    num_classes = len(classes)
    idx20 = [i for i, c in enumerate(classes) if c in ORIGINAL_20]

    # 与 train30.py 同一份切分
    ind_all = PlantDataset(str(ROOT / "data" / "plants_indoor"))
    _, _, test_i = stratified_split(ind_all, (0.70, 0.15, 0.15), SEED)
    print("=" * 78)
    print(f"分辨率归因实验（室内测试集 {len(test_i)} 张，与训练同一份切分）")
    print("=" * 78)

    # 各分辨率下的测试集 loader
    loaders = {}
    for r in RESOLUTIONS:
        ds = PlantDataset(str(ROOT / "data" / "plants_indoor"), transform=get_val_transforms(r))
        loaders[r] = DataLoader(Subset(ds, test_i), batch_size=32, shuffle=False,
                                num_workers=4, pin_memory=True)

    results = {}
    print(f"\n{'模型':8s} {'输入':>6s} {'总体':>8s} {'原20类':>8s} {'新增10类':>8s}")
    print("-" * 78)
    for mname, mpath in MODELS.items():
        if not mpath.is_file():
            print(f"{mname:8s}  权重缺失 {mpath}")
            continue
        for r in RESOLUTIONS:
            model = create_model(num_classes, pretrained=False)
            model.load_state_dict(torch.load(mpath, map_location="cpu", weights_only=True))
            model = model.to(device)

            # 各自算总体 / 原20 / 新增10
            def acc_sub(sub_idx):
                c = t = 0
                model.eval()
                with torch.no_grad():
                    for images, labels in loaders[r]:
                        images, labels = images.to(device), labels.to(device)
                        pred = model(images).argmax(1)
                        m = torch.zeros_like(labels, dtype=torch.bool)
                        for k in sub_idx:
                            m |= (labels == k)
                        c += int(((pred == labels) & m).sum().item())
                        t += int(m.sum().item())
                return c / t if t else 0.0

            all_acc = acc(model, loaders[r], device)
            o = acc_sub(idx20)
            n = acc_sub([i for i in range(num_classes) if i not in idx20])
            results[f"{mname}@{r}"] = {"all": all_acc, "orig20": o, "new10": n}
            print(f"{mname:8s} {r:6d} {all_acc:8.4f} {o:8.4f} {n:8.4f}")

    # ---------- 归因 ----------
    print("\n" + "=" * 78)
    print("归因")
    print("=" * 78)
    a = results.get("224训@224", {}).get("all")
    b = results.get("224训@320", {}).get("all")
    c = results.get("320训@224", {}).get("all")
    d = results.get("320训@320", {}).get("all")
    if None not in (a, b, c, d):
        print(f"224训模型: 输入224 ={a:.4f}  →  输入320 ={b:.4f}   差 {b - a:+.4f}")
        print(f"320训模型: 输入224 ={c:.4f}  →  输入320 ={d:.4f}   差 {d - c:+.4f}")
        print()
        print(f"总提升（320训@320 − 224训@224）: {d - a:+.4f}")
        print(f"  其中「仅推理分辨率」（224训@320 − 224训@224）: {b - a:+.4f}")
        print(f"  其中「训练分辨率获益」（320训@320 − 224训@320）: {d - b:+.4f}")
        print()
        if b - a > d - b:
            print("解读：收益**主要来自推理时用更高分辨率** —— 这意味着不重训、"
                  "只把推理输入改成 320 就能拿到大部分提升。")
        else:
            print("解读：收益主要来自**在 320 上训练** —— 模型学到了高分辨率下才有的特征，"
                  "推理也必须用 320 才能兑现（服务端要一起改）。")
        if c < a - 0.02:
            print(f"注意：320训模型在 224 输入下退到 {c:.4f}（低于 224训模型），"
                  f"说明它依赖高分辨率特征，**不可回退到 224 推理**。")

    Path("C:/Plant/tests/results/resolution_transfer.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n写入 C:/Plant/tests/results/resolution_transfer.json")


if __name__ == "__main__":
    main()
