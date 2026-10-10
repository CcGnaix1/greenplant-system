"""症状识别模型训练 —— 输入一张植物（叶片）照片，输出症状大类。

与 train30.py（品种识别）的分工
------------------------------
品种模型回答「这是什么植物」，本模型回答「它怎么了」。两者串联才是用户要的
「识别出是什么植物、得了什么病、给建议」。这个模型不认品种，只认症状状态。

为什么增强比品种模型更狠
------------------------
PlantVillage 是**实验室照**：单叶、纯灰背景、打光均匀。而用户拿手机拍的是**整株**、
背景杂乱、光照不均。这个域差距是本项目已知的最大风险，训练时只能用更强的增广
去逼近真实分布：随机裁剪/缩放、彩色抖动、模糊、随机遮挡（模拟背景杂物）。

选优指标为什么用宏召回而不是总体准确率
--------------------------------------
症状类严重不均衡（leaf_spot 约 2 万张，rust/pest 约 1500 张）。总体准确率会被大类
主导：把 rust 全判错也只掉 1 个点，却让「锈病」这类完全不可用。宏召回（各类召回的平均）
对小类一视同仁，用它选优才能保证每个症状类都可用。
"""

import argparse
import json
import sys
import time
from pathlib import Path

import albumentations as A
import numpy as np
import torch
import torch.nn as nn
from albumentations.pytorch import ToTensorV2
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Subset

ML_DIR = Path(__file__).resolve().parent
ROOT = ML_DIR.parent
sys.path.insert(0, str(ML_DIR))

from dataset import IMAGENET_MEAN, IMAGENET_STD, get_val_transforms  # noqa: E402
from symptom_dataset import (INDEX, TAXONOMY, SymptomDataset,  # noqa: E402
                             load_classes, load_meta, make_class_weights)
from train import create_model  # noqa: E402
from train30 import stratified_split  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SEED = 42


def train_transforms(image_size: int = 224):
    """比品种模型更强的增广，用于缓解 PlantVillage 实验室照 → 手机实拍的域差距。"""
    return A.Compose([
        A.RandomResizedCrop(image_size, image_size, scale=(0.5, 1.0)),
        A.HorizontalFlip(p=0.5),
        A.VerticalFlip(p=0.3),
        A.RandomRotate90(p=0.4),
        A.ShiftScaleRotate(shift_limit=0.1, scale_limit=0.15, rotate_limit=30,
                           border_mode=0, p=0.5),
        A.ColorJitter(brightness=0.4, contrast=0.4, saturation=0.4, hue=0.1, p=0.7),
        A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2, p=0.4),
        A.GaussianBlur(blur_limit=(3, 7), p=0.3),
        A.CoarseDropout(max_holes=8, max_height=32, max_width=32, p=0.3),
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ToTensorV2(),
    ])


@torch.no_grad()
def evaluate(model, loader, device, num_classes: int):
    """返回 (总体准确率, 宏召回, 各类召回 dict, 混淆矩阵)。"""
    model.eval()
    conf = np.zeros((num_classes, num_classes), dtype=np.int64)
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        pred = model(images).argmax(1)
        for t, p in zip(labels.view(-1).tolist(), pred.view(-1).tolist()):
            conf[t, p] += 1
    total = conf.sum()
    acc = float(np.trace(conf) / total) if total else 0.0
    rec = {}
    for c in range(num_classes):
        denom = conf[c].sum()
        rec[c] = float(conf[c, c] / denom) if denom else float("nan")
    valid = [v for v in rec.values() if not np.isnan(v)]
    macro = float(np.mean(valid)) if valid else 0.0
    return acc, macro, rec, conf


def main():
    ap = argparse.ArgumentParser(description="症状识别模型训练")
    ap.add_argument("--index", default=str(INDEX))
    ap.add_argument("--taxonomy", default=str(TAXONOMY))
    ap.add_argument("--out-dir", default=str(ROOT / "output_symptom"))
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--label-smoothing", type=float, default=0.1)
    ap.add_argument("--val-frac", type=float, default=0.15, help="从 train 里再切出多少做选优")
    ap.add_argument("--num-workers", type=int, default=4)
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument("--weight-power", type=float, default=0.5, help="类权重 = (N/(K*n))^power")
    ap.add_argument("--no-class-weights", action="store_true")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = load_meta(Path(args.taxonomy))
    classes = load_classes(Path(args.taxonomy))
    num_classes = len(classes)

    print("=" * 82)
    print("症状识别模型训练")
    print("=" * 82)
    print(f"设备    : {device}" + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else ""))
    print(f"症状类  : {num_classes} 类")
    for i, c in enumerate(classes):
        print(f"    [{i}] {c:16s} {meta['labels'][c]}"
              + (f"  → symptom_dict.{meta['dict_code'][c]}" if c in meta.get("dict_code", {}) else ""))

    # ---------- 数据 ----------
    tr_tf, va_tf = train_transforms(args.image_size), get_val_transforms(args.image_size)
    full_train = SymptomDataset(args.index, "train", classes, tr_tf, Path(args.taxonomy))
    train_eval_ds = SymptomDataset(args.index, "train", classes, va_tf, Path(args.taxonomy))
    test_ds = SymptomDataset(args.index, "test", classes, va_tf, Path(args.taxonomy))

    counts = full_train.counts()
    print(f"\n训练集 {len(full_train)} 张 / 测试集 {len(test_ds)} 张")
    print(f"{'症状类':16s} {'train':>8s} {'test':>8s}")
    for c in classes:
        tc = sum(1 for _, i in test_ds.samples if classes[i] == c)
        print(f"{c:16s} {counts[c]:>8d} {tc:>8d}")

    tr_idx, va_idx = stratified_split(full_train, (1 - args.val_frac, args.val_frac), SEED)
    train_loader = DataLoader(Subset(full_train, tr_idx), batch_size=args.batch_size,
                              shuffle=True, num_workers=args.num_workers, pin_memory=True)
    val_loader = DataLoader(Subset(train_eval_ds, va_idx), batch_size=args.batch_size,
                            shuffle=False, num_workers=args.num_workers, pin_memory=True)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False,
                             num_workers=args.num_workers, pin_memory=True)
    print(f"切分    : 训练 {len(tr_idx)} / 验证 {len(va_idx)}（测试集选优不参与）\n")

    # ---------- 类权重 ----------
    weights = None
    if not args.no_class_weights:
        weights = make_class_weights(counts, classes, args.weight_power).to(device)
        print("类权重(power=%.2f): %s" % (args.weight_power,
              "  ".join(f"{c}={w:.2f}" for c, w in zip(classes, weights.tolist()))))
    crit = nn.CrossEntropyLoss(weight=weights, label_smoothing=args.label_smoothing)

    # ---------- 模型 ----------
    model = create_model(num_classes, pretrained=True).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    sched = CosineAnnealingLR(opt, T_max=args.epochs, eta_min=args.lr * 0.01)

    print("\n" + "-" * 82)
    print(f"{'轮':>3} {'耗时':>7} {'train':>8} {'val_acc':>8} {'val宏召回':>10}")
    print("-" * 82)

    best_macro, best_epoch, history = -1.0, 0, []
    for epoch in range(args.epochs):
        t0 = time.time()
        model.train()
        tc = tt = 0
        tot_loss = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            opt.zero_grad()
            out = model(images)
            loss = crit(out, labels)
            loss.backward()
            opt.step()
            tot_loss += float(loss.item()) * labels.size(0)
            tc += int((out.argmax(1) == labels).sum().item())
            tt += labels.size(0)
        sched.step()

        v_acc, v_macro, _, _ = evaluate(model, val_loader, device, num_classes)
        dt = time.time() - t0
        print(f"{epoch + 1:3d} {dt:6.0f}s {tc / tt:8.4f} {v_acc:8.4f} {v_macro:10.4f}")

        history.append({"epoch": epoch + 1, "loss": tot_loss / tt, "train_acc": tc / tt,
                        "val_acc": v_acc, "val_macro_recall": v_macro,
                        "lr": opt.param_groups[0]["lr"]})
        if v_macro > best_macro:
            best_macro, best_epoch = v_macro, epoch + 1
            torch.save(model.state_dict(), out_dir / "best_model.pth")
            print("      [best] 已保存（按验证集宏召回选优）")
        (out_dir / "history.json").write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- 最终评估 ----------
    print("-" * 82)
    final = create_model(num_classes, pretrained=False)
    final.load_state_dict(torch.load(out_dir / "best_model.pth", map_location="cpu", weights_only=True))
    final = final.to(device)

    t_acc, t_macro, t_rec, conf = evaluate(final, test_loader, device, num_classes)
    print(f"\n最优轮次: 第 {best_epoch} 轮（验证宏召回 {best_macro:.4f}）\n")
    print("=" * 82)
    print("测试集结果（PlantVillage 官方 color_test，选优未用）")
    print("=" * 82)
    print(f"总体准确率 {t_acc:.4f}    宏召回 {t_macro:.4f}\n")
    print(f"{'症状类':16s} {'召回':>8s} {'样本':>7s}   主要混淆")
    for c in range(num_classes):
        row = conf[c].copy()
        row[c] = 0
        top = np.argsort(row)[::-1][:2]
        mix = ", ".join(f"{classes[j]}({row[j]})" for j in top if row[j] > 0)
        print(f"{classes[c]:16s} {t_rec[c]:8.4f} {conf[c].sum():7d}   {mix or '-'}")

    print("\n⚠ 这些指标是**实验室单叶照**上的分数。用户手机拍的是整株、复杂背景，"
          "\n  实测会显著低于此值——域差距是本模型已知的主要局限，报告里必须写明。")

    # ---------- labels.json ----------
    labels = [{
        "name": c, "id": i,
        "label": meta["labels"][c],
        "dict_code": meta.get("dict_code", {}).get(c),
    } for i, c in enumerate(classes)]
    (out_dir / "labels.json").write_text(
        json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")

    (out_dir / "result.json").write_text(json.dumps({
        "num_classes": num_classes,
        "classes": classes,
        "best_epoch": best_epoch,
        "selection_metric": "val_macro_recall",
        "sizes": {"train": len(tr_idx), "val": len(va_idx), "test": len(test_ds)},
        "train_counts": counts,
        "metrics": {
            "test_acc": t_acc,
            "test_macro_recall": t_macro,
            "per_class_recall": {classes[i]: t_rec[i] for i in range(num_classes)},
        },
        "caveat": "指标基于 PlantVillage 实验室单叶照；真实手机整株照会因域差距下降",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n产物: {out_dir}/ (best_model.pth / labels.json / history.json / result.json)")


if __name__ == "__main__":
    main()
