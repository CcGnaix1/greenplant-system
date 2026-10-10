"""在 best_model.pth 基础上微调，把模型适配到「室内盆栽」这一域。

为什么是微调而不是重训
----------------------
现有模型在野外照上 val_acc 0.9096，但室内照只有 0.46 —— 是**数据域不匹配**。
训练集已过拟合（train_acc 0.9986 / val_acc 0.9059，gap +0.09），
继续加轮次只会让 gap 更大，补不出没见过的东西。
所以正确做法是补一批室内数据后，用**低学习率、少量轮次**微调，
并从现有权重出发，避免把已学会的野外特征冲掉。

诚实性保障（这是本脚本最重要的设计）
------------------------------------
1. 野外验证集保持与 train.py 完全一致的切分（random_split seed=42, train_split=0.8），
   所以那 542 张**从未参与训练**，微调前后的 0.9096 可直接对比。
2. 室内数据切三段：train(70%) / val(15%) / test(15%)。
   val 用于选最优轮次，test 只用于最终汇报 —— 不用 test 选模型，否则又是自欺。
3. 同时监控两边的准确率：只涨室内、把野外搞崩了不算成功。

用法:
    python finetune.py                                  # 默认参数
    python finetune.py --epochs 10 --lr 1e-4
    python finetune.py --freeze-backbone                # 只训分类头（遗忘严重时用）
    python finetune.py --indoor-ratio 0.5               # 室内:野外 的目标比例

产物:
    output_indoor/best_model.pth      微调后的权重（不覆盖现有 output/）
    output_indoor/history.json        逐轮指标
    output_indoor/labels.json         标签映射（从现有 output/ 复制，保持 20 类一致）
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import ConcatDataset, DataLoader, Subset

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import TrainConfig                                    # noqa: E402
from dataset import PlantDataset, get_train_transforms, get_val_transforms  # noqa: E402
from train import create_model                                    # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SEED = 42


def stratified_split(dataset: PlantDataset, fracs: tuple, seed: int) -> list[list[int]]:
    """按类别分层切分，返回若干组下标。

    不用 random_split：它不保证每类比例一致，类别不均衡时
    某个类的样本可能全落进测试集，指标就会失真。
    """
    gen = torch.Generator().manual_seed(seed)
    by_class: dict[int, list[int]] = {}
    for idx, (_, label) in enumerate(dataset.samples):
        by_class.setdefault(label, []).append(idx)

    groups: list[list[int]] = [[] for _ in fracs]
    for label, idxs in by_class.items():
        perm = torch.randperm(len(idxs), generator=gen).tolist()
        shuffled = [idxs[i] for i in perm]
        n = len(shuffled)
        # 累计边界切分，保证各段凑满总数
        cuts, acc = [], 0.0
        for f in fracs[:-1]:
            acc += f
            cuts.append(int(round(n * acc)))
        prev = 0
        for gi, c in enumerate(cuts + [n]):
            groups[gi].extend(shuffled[prev:c])
            prev = c
    return groups


def evaluate(model, loader, device) -> tuple[float, float]:
    """返回 (准确率, 平均损失)。"""
    model.eval()
    crit = nn.CrossEntropyLoss()
    correct = total = 0
    loss_sum = 0.0
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            out = model(images)
            loss_sum += crit(out, labels).item() * labels.size(0)
            correct += (out.argmax(1) == labels).sum().item()
            total += labels.size(0)
    if total == 0:
        return 0.0, 0.0
    return correct / total, loss_sum / total


def main():
    ap = argparse.ArgumentParser(description="室内域微调")
    ap.add_argument("--wild-dir", default=str(ROOT / "data" / "plants"))
    ap.add_argument("--indoor-dir", default=str(ROOT / "data" / "plants_indoor"))
    ap.add_argument("--init", default=str(ROOT / "output" / "best_model.pth"),
                    help="起点权重，默认用当前部署的 best_model.pth")
    ap.add_argument("--src-labels", default=str(ROOT / "output" / "labels.json"))
    ap.add_argument("--out-dir", default=str(ROOT / "output_indoor"),
                    help="输出目录，刻意与 output/ 分开，避免未验收就覆盖线上模型")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch-size", type=int, default=48)
    ap.add_argument("--lr", type=float, default=1e-4, help="必须远小于原始训练的 1e-3")
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--label-smoothing", type=float, default=0.1)
    ap.add_argument("--indoor-ratio", type=float, default=0.5,
                    help="室内样本在训练集中的目标占比（0.5=各占一半）")
    ap.add_argument("--freeze-backbone", action="store_true",
                    help="冻结特征提取层，只训分类头。遗忘严重时用")
    ap.add_argument("--num-workers", type=int, default=4)
    ap.add_argument("--image-size", type=int, default=224)
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    wild_dir = Path(args.wild_dir)
    indoor_dir = Path(args.indoor_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 76)
    print("室内域微调")
    print("=" * 76)
    print(f"设备      : {device}" + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else ""))
    print(f"起点权重  : {args.init}")
    print(f"野外数据  : {wild_dir}")
    print(f"室内数据  : {indoor_dir}")
    print()

    # ---------- 1. 野外：复现 train.py 的切分，保证 542 张验证集仍然干净 ----------
    wild_all = PlantDataset(str(wild_dir), transform=get_val_transforms(args.image_size))
    n_wild = len(wild_all)
    n_train = int(n_wild * 0.8)
    gen = torch.Generator().manual_seed(SEED)
    wild_train_idx, wild_val_idx = torch.utils.data.random_split(
        wild_all, [n_train, n_wild - n_train], generator=gen
    )
    wild_train_idx = list(wild_train_idx.indices)
    wild_val_idx = list(wild_val_idx.indices)
    print(f"野外: 共 {n_wild} 张 -> 训练 {len(wild_train_idx)} / 验证 {len(wild_val_idx)}（与 train.py 切分一致）")

    # ---------- 2. 室内：分层切 train/val/test ----------
    indoor_all = PlantDataset(str(indoor_dir), transform=get_val_transforms(args.image_size))
    ind_train_i, ind_val_i, ind_test_i = stratified_split(indoor_all, (0.70, 0.15, 0.15), SEED)
    print(f"室内: 共 {len(indoor_all)} 张 -> 训练 {len(ind_train_i)} / 验证 {len(ind_val_i)} / 测试 {len(ind_test_i)}")

    # ---------- 3. 类别必须完全对齐，否则标签错位 ----------
    if wild_all.classes != indoor_all.classes:
        print("\n[错误] 两个数据集的类别顺序不一致，直接训练会导致标签错位：")
        print(f"  野外: {wild_all.classes}")
        print(f"  室内: {indoor_all.classes}")
        raise SystemExit(1)
    classes = wild_all.classes
    num_classes = len(classes)
    print(f"类别  : {num_classes} 类，两侧顺序一致")

    # 起点模型的类别数也要对得上
    src_labels = json.loads(Path(args.src_labels).read_text(encoding="utf-8"))
    if [x["name"] for x in src_labels] != classes:
        print("\n[错误] 现有 labels.json 的类别顺序与数据集不一致：")
        print(f"  labels: {[x['name'] for x in src_labels]}")
        raise SystemExit(1)

    # ---------- 4. 采样配比：把室内的比例调到 --indoor-ratio ----------
    n_ind_use = len(ind_train_i)
    n_wild_use = len(wild_train_idx)
    ratio = min(max(args.indoor_ratio, 0.05), 0.95)
    # 保持室内全用，按比例决定用多少野外（室内数据来之不易且是目标域）
    want_wild = int(n_ind_use * (1 - ratio) / ratio)
    if want_wild <= n_wild_use:
        g = torch.Generator().manual_seed(SEED)
        pick = torch.randperm(n_wild_use, generator=g)[:want_wild].tolist()
        wild_use = [wild_train_idx[i] for i in pick]
        ind_use = ind_train_i
    else:
        # 野外不够就用满，反过来限制室内
        wild_use = wild_train_idx
        want_ind = int(n_wild_use * ratio / (1 - ratio))
        g = torch.Generator().manual_seed(SEED)
        pick = torch.randperm(n_ind_use, generator=g)[:min(want_ind, n_ind_use)].tolist()
        ind_use = [ind_train_i[i] for i in pick]

    actual = len(ind_use) / (len(ind_use) + len(wild_use))
    print(f"训练集: 室内 {len(ind_use)} + 野外 {len(wild_use)} = {len(ind_use) + len(wild_use)}（室内占比 {actual:.1%}）\n")

    # ---------- 5. 组装 DataLoader ----------
    tr_tf = get_train_transforms(args.image_size)
    va_tf = get_val_transforms(args.image_size)
    wild_tr_set = PlantDataset(str(wild_dir), transform=tr_tf)
    ind_tr_set = PlantDataset(str(indoor_dir), transform=tr_tf)
    train_ds = ConcatDataset([Subset(wild_tr_set, wild_use), Subset(ind_tr_set, ind_use)])

    wild_val_set = PlantDataset(str(wild_dir), transform=va_tf)
    ind_val_set = PlantDataset(str(indoor_dir), transform=va_tf)
    ind_test_set = PlantDataset(str(indoor_dir), transform=va_tf)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              num_workers=args.num_workers, pin_memory=True)
    wild_val_loader = DataLoader(Subset(wild_val_set, wild_val_idx), batch_size=args.batch_size,
                                 shuffle=False, num_workers=args.num_workers, pin_memory=True)
    ind_val_loader = DataLoader(Subset(ind_val_set, ind_val_i), batch_size=args.batch_size,
                                shuffle=False, num_workers=args.num_workers, pin_memory=True)
    ind_test_loader = DataLoader(Subset(ind_test_set, ind_test_i), batch_size=args.batch_size,
                                 shuffle=False, num_workers=args.num_workers, pin_memory=True)

    # ---------- 6. 模型 ----------
    model = create_model(num_classes, pretrained=False)
    state = torch.load(args.init, map_location="cpu")
    model.load_state_dict(state)
    model = model.to(device)
    print(f"已加载权重: {args.init}")

    if args.freeze_backbone:
        for p in model.features.parameters():
            p.requires_grad = False
        print("已冻结特征提取层（只训分类头）")

    trainable = [p for p in model.parameters() if p.requires_grad]
    print(f"可训练参数: {sum(p.numel() for p in trainable) / 1e6:.2f}M\n")

    crit = nn.CrossEntropyLoss(label_smoothing=args.label_smoothing)
    opt = torch.optim.AdamW(trainable, lr=args.lr, weight_decay=args.weight_decay)
    sched = CosineAnnealingLR(opt, T_max=args.epochs, eta_min=args.lr * 0.01)

    # 基线（微调前的水平），后面所有对比都以它为参照
    base_wild, _ = evaluate(model, wild_val_loader, device)
    base_ind, _ = evaluate(model, ind_val_loader, device)
    print(f"微调前基线: 野外验证 {base_wild:.4f} | 室内验证 {base_ind:.4f}\n")
    print("-" * 76)

    best_score = -1.0
    best_epoch = 0
    history = []

    for epoch in range(args.epochs):
        t0 = time.time()
        model.train()
        tl = tc = tt = 0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            opt.zero_grad()
            out = model(images)
            loss = crit(out, labels)
            loss.backward()
            opt.step()
            tl += loss.item() * labels.size(0)
            tc += (out.argmax(1) == labels).sum().item()
            tt += labels.size(0)
        sched.step()

        w_acc, _ = evaluate(model, wild_val_loader, device)
        i_acc, _ = evaluate(model, ind_val_loader, device)
        # 选优标准：两边准确率之和。只涨单边不算好模型。
        score = w_acc + i_acc

        dt = time.time() - t0
        print(f"Epoch {epoch + 1:2d}/{args.epochs} ({dt:5.1f}s)  "
              f"train={tc / tt:.4f}  野外验证={w_acc:.4f}  室内验证={i_acc:.4f}  "
              f"和={score:.4f}  野外变化={w_acc - base_wild:+.4f}")

        history.append({
            "epoch": epoch + 1,
            "train_acc": tc / tt,
            "wild_val_acc": w_acc,
            "indoor_val_acc": i_acc,
            "score": score,
            "lr": opt.param_groups[0]["lr"],
        })

        if score > best_score:
            best_score = score
            best_epoch = epoch + 1
            torch.save(model.state_dict(), out_dir / "best_model.pth")
            print(f"         [best] 已保存 (野外{w_acc:.4f} + 室内{i_acc:.4f})")

        with open(out_dir / "history.json", "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    # ---------- 7. 用最优权重在「从未用于选优」的室内测试集上出最终数 ----------
    print("-" * 76)
    print(f"最优轮次: 第 {best_epoch} 轮（按 野外验证+室内验证 之和选取）")
    final = create_model(num_classes, pretrained=False)
    final.load_state_dict(torch.load(out_dir / "best_model.pth", map_location="cpu"))
    final = final.to(device)

    f_wild, _ = evaluate(final, wild_val_loader, device)
    f_ind_val, _ = evaluate(final, ind_val_loader, device)
    f_ind_test, _ = evaluate(final, ind_test_loader, device)

    print()
    print("=" * 76)
    print("最终结果")
    print("=" * 76)
    print(f"                    微调前      微调后      变化")
    print(f"野外验证集({len(wild_val_idx):4d}张)   {base_wild:.4f}      {f_wild:.4f}      {f_wild - base_wild:+.4f}")
    print(f"室内验证集({len(ind_val_i):4d}张)   {base_ind:.4f}      {f_ind_val:.4f}      {f_ind_val - base_ind:+.4f}")
    print(f"室内测试集({len(ind_test_i):4d}张)   (未用)      {f_ind_test:.4f}      —（选优未用此集，可作最终汇报数）")
    print()
    if f_wild < 0.85:
        print("[警告] 野外验证集掉到 0.85 以下，说明发生了明显的灾难性遗忘。")
        print("       建议加 --freeze-backbone 重跑，或降低 --indoor-ratio。")
    elif f_wild < base_wild - 0.03:
        print("[注意] 野外验证集下降超过 3 个点，建议调低 --indoor-ratio 或减少轮次。")
    else:
        print("[OK] 野外能力基本保持，室内能力提升 —— 符合预期。")

    shutil.copy(args.src_labels, out_dir / "labels.json")
    (out_dir / "result.json").write_text(json.dumps({
        "base_wild_val_acc": base_wild,
        "base_indoor_val_acc": base_ind,
        "final_wild_val_acc": f_wild,
        "final_indoor_val_acc": f_ind_val,
        "final_indoor_test_acc": f_ind_test,
        "best_epoch": best_epoch,
        "indoor_ratio": actual,
        "init": args.init,
        "freeze_backbone": args.freeze_backbone,
        "epochs": args.epochs,
        "lr": args.lr,
        "sizes": {"wild_train": len(wild_use), "indoor_train": len(ind_use),
                  "wild_val": len(wild_val_idx), "indoor_val": len(ind_val_i),
                  "indoor_test": len(ind_test_i)},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n产物: {out_dir}/ (best_model.pth / labels.json / history.json / result.json)")
    print("验收通过后再用 export_onnx.py 导出并替换线上模型。")


if __name__ == "__main__":
    main()
