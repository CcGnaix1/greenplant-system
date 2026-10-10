"""症状模型 v2 —— 修「靠背景判病」的过报问题。

与 v1（train_symptom.py）的唯一区别在数据：v1 直接把 PlantVillage 原图喂给模型，
模型学到「画面里有不规则深色区域 = 病斑」，于是真实照片里的土壤/落叶/阴影全被
报成叶斑病（实测：健康整株照只有 29.6% 判为健康）。v2 用 symptom_bg.py 的合成管线
把叶片贴到真实背景上，并加入真实整株照作为健康样本。

选优指标为什么是「域内宏召回 + 真实照健康率」的加权
--------------------------------------------------
只看域内：v1 就是 0.9986，但真实照片全废 —— 这个指标量不出要紧的事。
只看真实照健康率：模型会退化成「一律报健康」，真实率 1.0 而域内宏召回塌到 1/6。
两者按 0.5/0.5 加权后，跛脚的解都拿不到高分，必须两边都站得住。

注意：真实照那批**没有健康标注**（iNat 的 captive/cultivated 只表示栽培个体），
所以它是「误报倾向」而非准确率，选优时当作一个较弱的信号用，报告里必须写清。
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Subset

ML_DIR = Path(__file__).resolve().parent
ROOT = ML_DIR.parent
sys.path.insert(0, str(ML_DIR))

from dataset import get_val_transforms                                  # noqa: E402
from symptom_bg import RealPhotoEval, SymptomBgDataset, split_indoor    # noqa: E402
from symptom_dataset import (INDEX, SymptomDataset, load_classes,       # noqa: E402
                             load_meta, make_class_weights)
from train import create_model                                          # noqa: E402
from train30 import stratified_split                                    # noqa: E402
from train_symptom import evaluate, train_transforms                    # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SEED = 42
HEALTHY = "healthy"


@torch.no_grad()
def real_photo_stats(model, loader, device, classes):
    """真实照片上的误报统计：判为健康的比例 + 高置信误报明细。"""
    model.eval()
    hi = classes.index(HEALTHY)
    healthy = total = 0
    high_conf_wrong = []
    for images, labels in loader:
        images = images.to(device)
        probs = torch.softmax(model(images), dim=1)
        pred = probs.argmax(1)
        conf = probs.max(1).values
        for p, c in zip(pred.tolist(), conf.tolist()):
            total += 1
            if p == hi:
                healthy += 1
            elif c >= 0.8:
                high_conf_wrong.append((classes[p], c))
    rate = healthy / total if total else 0.0
    return rate, total, high_conf_wrong


def main():
    ap = argparse.ArgumentParser(description="症状模型 v2（背景合成）")
    ap.add_argument("--index", default=str(INDEX))
    ap.add_argument("--out-dir", default=str(ROOT / "output_symptom_v2"))
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--label-smoothing", type=float, default=0.1)
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--num-workers", type=int, default=4)
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument("--composite-prob", type=float, default=0.7,
                    help="PlantVillage 样本合成到真实背景的概率")
    ap.add_argument("--real-healthy-frac", type=float, default=0.25,
                    help="真实整株照在训练集中的目标占比")
    ap.add_argument("--weight-power", type=float, default=0.5)
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = load_meta()
    classes = load_classes()
    num_classes = len(classes)

    print("=" * 84)
    print("症状模型 v2（背景合成 + 真实整株照）")
    print("=" * 84)
    print(f"设备 {device}" + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else ""))

    tr_paths, bg_paths, test_paths = split_indoor()
    print(f"真实栽培照划分: 训练(健康样本) {len(tr_paths)} / 背景池 {len(bg_paths)} / "
          f"跨域测试 {len(test_paths)}")
    print(f"合成概率 {args.composite_prob}，真实照目标占比 {args.real_healthy_frac}")

    tr_tf, va_tf = train_transforms(args.image_size), get_val_transforms(args.image_size)

    train_ds = SymptomBgDataset(args.index, bg_paths, tr_paths, classes, tr_tf,
                                split="train", composite_prob=args.composite_prob,
                                real_healthy_frac=args.real_healthy_frac)
    # 验证集用原图（不合成），与域内测试集同分布，指标可比
    val_all = SymptomDataset(args.index, "train", classes, va_tf)
    tr_idx, va_idx = stratified_split(val_all, (1 - args.val_frac, args.val_frac), SEED)

    pv_test = SymptomDataset(args.index, "test", classes, va_tf)
    real_test = RealPhotoEval(test_paths, classes, va_tf)

    counts = train_ds.counts()
    print(f"\n训练样本 {len(train_ds)}（其中真实照 {train_ds.real_count}）")
    print(f"  {'症状类':16s} {'训练':>8s}")
    for c in classes:
        print(f"  {c:16s} {counts[c]:>8d}")

    weights = make_class_weights(counts, classes, args.weight_power).to(device)
    print("类权重: " + "  ".join(f"{c}={w:.2f}" for c, w in zip(classes, weights.tolist())))
    crit = nn.CrossEntropyLoss(weight=weights, label_smoothing=args.label_smoothing)

    nw = args.num_workers
    bs = args.batch_size
    train_loader = DataLoader(train_ds, batch_size=bs, shuffle=True,
                              num_workers=nw, pin_memory=True, drop_last=True)
    val_loader = DataLoader(Subset(val_all, va_idx), batch_size=bs, shuffle=False,
                            num_workers=nw, pin_memory=True)
    pv_test_loader = DataLoader(pv_test, batch_size=bs, shuffle=False,
                                num_workers=nw, pin_memory=True)
    real_loader = DataLoader(real_test, batch_size=bs, shuffle=False,
                             num_workers=nw, pin_memory=True)

    model = create_model(num_classes, pretrained=True).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    sched = CosineAnnealingLR(opt, T_max=args.epochs, eta_min=args.lr * 0.01)

    print("\n" + "-" * 84)
    print(f"{'轮':>3} {'耗时':>6} {'train':>7} {'域内mac':>8} {'真实健康率':>10} "
          f"{'高置信误报':>10} {'选优分':>8}")
    print("-" * 84)

    best, best_epoch, history = -1.0, 0, []
    for epoch in range(args.epochs):
        t0 = time.time()
        train_ds.set_epoch(epoch)
        model.train()
        tc = tt = 0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            opt.zero_grad()
            out = model(images)
            loss = crit(out, labels)
            loss.backward()
            opt.step()
            tc += int((out.argmax(1) == labels).sum().item())
            tt += labels.size(0)
        sched.step()

        pv_acc, pv_macro, _, _ = evaluate(model, pv_test_loader, device, num_classes)
        r_healthy, r_total, hc = real_photo_stats(model, real_loader, device, classes)
        score = 0.5 * pv_macro + 0.5 * r_healthy
        dt = time.time() - t0

        print(f"{epoch + 1:3d} {dt:5.0f}s {tc / tt:7.4f} {pv_macro:8.4f} "
              f"{r_healthy:10.1%} {len(hc):10d} {score:8.4f}")

        history.append({"epoch": epoch + 1, "train_acc": tc / tt, "pv_test_macro_recall": pv_macro,
                        "pv_test_acc": pv_acc, "real_healthy_rate": r_healthy,
                        "high_conf_false_positives": len(hc), "score": score})
        if score > best:
            best, best_epoch = score, epoch + 1
            torch.save(model.state_dict(), out_dir / "best_model.pth")
            print(f"      [best] 已保存（域内宏召回{pv_macro:.4f} × 真实健康率{r_healthy:.1%}）")
        (out_dir / "history.json").write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- 最终评估 ----------
    final = create_model(num_classes, pretrained=False)
    final.load_state_dict(torch.load(out_dir / "best_model.pth", map_location="cpu",
                                     weights_only=True))
    final = final.to(device)

    print("-" * 84)
    pv_acc, pv_macro, pv_rec, pv_conf = evaluate(final, pv_test_loader, device, num_classes)
    r_healthy, r_total, hc = real_photo_stats(final, real_loader, device, classes)

    print(f"\n最优轮次 第 {best_epoch} 轮\n")
    print("=" * 84)
    print("A. 域内（PlantVillage 官方测试集，选优用的就是这个集，仅供对照）")
    print("=" * 84)
    print(f"准确率 {pv_acc:.4f}   宏召回 {pv_macro:.4f}")
    for c in range(num_classes):
        print(f"  {classes[c]:16s} 召回 {pv_rec[c]:.4f}  样本 {pv_conf[c].sum():5d}")

    print("\n" + "=" * 84)
    print("B. 跨域（真实整株栽培照，训练时不可见）—— 这才是「手机拍照能不能用」")
    print("=" * 84)
    print(f"样本 {r_total} 张（无健康标注，看的是误报倾向）")
    print(f"判为健康: {r_healthy:.1%}   置信度>=0.8 的病害误报: {len(hc)} 张 "
          f"({len(hc) / r_total:.1%})")
    print(f"\n对照 v1（未做背景合成）: 真实健康率 29.6%，高置信误报 7.9%")
    if hc:
        from collections import Counter
        print("  误报分布:", dict(Counter(p for p, _ in hc).most_common()))

    (out_dir / "result.json").write_text(json.dumps({
        "num_classes": num_classes,
        "classes": classes,
        "composite_prob": args.composite_prob,
        "real_healthy_frac": args.real_healthy_frac,
        "best_epoch": best_epoch,
        "selection_metric": "0.5*pv_test_macro_recall + 0.5*real_healthy_rate",
        "in_domain": {"acc": pv_acc, "macro_recall": pv_macro,
                      "per_class_recall": {classes[i]: pv_rec[i] for i in range(num_classes)}},
        "cross_domain": {"n": r_total, "healthy_rate": r_healthy,
                         "high_conf_false_positives": len(hc),
                         "note": "无健康标注，为误报倾向观察"},
        "v1_baseline": {"real_healthy_rate": 0.296, "high_conf_false_positive_rate": 0.079},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    labels = [{"name": c, "id": i, "label": meta["labels"][c],
               "dict_code": meta.get("dict_code", {}).get(c)} for i, c in enumerate(classes)]
    (out_dir / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(f"\n产物: {out_dir}/ (best_model.pth / labels.json / history.json / result.json)")


if __name__ == "__main__":
    main()
