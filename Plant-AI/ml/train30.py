"""30 类重训：在 20 类模型基础上热启动，扩到 30 类（20 现有 + 10 新增）。

为什么不能沿用 finetune.py
--------------------------
finetune.py 只改权重、不动结构，输出仍是 20 类。这次类别数变成 30，
分类头换了，所以必须重训。但不必从零开始 —— 已学到的骨干特征
（边缘/叶形/纹理）依然有效，用**热启动**比随机初始化收敛快得多。

热启动怎么做
------------
用「形状匹配」过滤旧权重：形状一致的键照常加载，形状不符的自动丢弃。
20 类分类头的最后一层是 (20,1280)，新的要求 (30,1280)，形状不符会被过滤掉；
其余几百个键形状一致，全部继承。这样不需要手工列出要跳过哪些键。

数据设计
--------
两个域都参与训练，避免模型把「域」当成类别的捷径：
    data/plants/         野外照  (20 类旧 + 10 类新)
    data/plants_indoor/  室内照  (20 类旧 + 10 类新)
两侧目录集合必须与 species.json 完全一致，否则标签错位 —— 脚本内断言拦截。

评估口径（防止指标自欺）
------------------------
* 野外验证集沿用 random_split(seed=42, 0.8)，与初版/微调版同一切分，可直接对比
* 室内数据分 train/val/test，test 不参与选优
* 选优看 野外验证 + 室内验证 之和
* 额外汇报「仅原 20 类」的准确率 —— 扩类后整体通常下降，
  必须把「新增类拖累」和「原类退化」两件事分开看
"""

import argparse
import hashlib
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
# 初版的 20 个类，用于「扩类后原类是否退化」的对比
ORIGINAL_20 = [
    "兰花", "发财树", "吊兰", "多肉植物", "富贵竹", "常春藤", "文竹", "栀子花",
    "橡皮树", "琴叶榕", "白掌", "绿萝", "茉莉花", "薄荷", "虎皮兰", "袖珍椰子",
    "迷迭香", "铜钱草", "鹅掌柴", "龟背竹",
]


def _class_seed(seed: int, key) -> int:
    """由 (全局种子, 类名) 派生的每类种子。

    关键性质：**只依赖类名，不依赖其它类**。所以新增类别时，已有类的切分
    完全不变，新旧模型可以落在同一批测试图上对比。

    旧实现是全局共用一个 Generator，`randperm` 依次消费随机数 —— 一旦类的数量或
    排序变了，后面所有类的切分全部位移，导致「加了个新类，老类的测试集也换了」，
    指标不可比（2026-09-30 扩到 42 类时踩到）。
    """
    h = hashlib.md5(str(key).encode("utf-8")).hexdigest()
    return (seed * 1_000_003 + int(h[:8], 16)) % (2 ** 31 - 1)


def stratified_split(dataset, fracs, seed):
    """按类分层切分，避免类别不均衡时某类样本全落进一段。

    每类独立播种（见 _class_seed），所以**类之间互不影响**。
    """
    names = getattr(dataset, "classes", None)
    by_class = {}
    for idx, (_, label) in enumerate(dataset.samples):
        by_class.setdefault(label, []).append(idx)
    groups = [[] for _ in fracs]
    for label, idxs in by_class.items():
        # 用类名而非类下标做 key —— 下标会随新增类别而变化，类名不会
        key = names[label] if names is not None and label < len(names) else label
        g = torch.Generator().manual_seed(_class_seed(seed, key))
        perm = torch.randperm(len(idxs), generator=g).tolist()
        sh = [idxs[i] for i in perm]
        n = len(sh)
        cuts, acc = [], 0.0
        for f in fracs[:-1]:
            acc += f
            cuts.append(int(round(n * acc)))
        prev = 0
        for gi, c in enumerate(cuts + [n]):
            groups[gi].extend(sh[prev:c])
            prev = c
    return groups


def evaluate(model, loader, device, subset_classes=None):
    """返回 (总体准确率, 命中数, 总数)。subset_classes 给定时只统计这些类的样本。"""
    model.eval()
    crit = nn.CrossEntropyLoss()
    correct = total = 0
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            out = model(images)
            pred = out.argmax(1)
            hit = (pred == labels)
            if subset_classes is not None:
                m = torch.zeros_like(hit)
                for c in subset_classes:
                    m |= (labels == c)
                hit = hit & m
                total += int(m.sum().item())
            else:
                total += labels.size(0)
            correct += int(hit.sum().item())
    return (correct / total if total else 0.0), correct, total


def main():
    ap = argparse.ArgumentParser(description="30 类重训（热启动）")
    ap.add_argument("--wild-dir", default=str(ROOT / "data" / "plants"))
    ap.add_argument("--indoor-dir", default=str(ROOT / "data" / "plants_indoor"))
    ap.add_argument("--species", default=str(Path(__file__).resolve().parent / "species.json"))
    ap.add_argument("--species-ids", default=str(ROOT / "data" / "species_ids.json"))
    ap.add_argument("--init", default=str(ROOT / "output" / "best_model.pth"),
                    help="热启动用的旧权重（20 类）。传空串则从零训练")
    ap.add_argument("--arch", default="mobilenet_v3_large",
                    choices=["mobilenet_v3_large", "efficientnet_b0"],
                    help="骨干网。换架构时热启动无法继承（键名形状都不同），需从 ImageNet 权重训")
    ap.add_argument("--out-dir", default=str(ROOT / "output_v30"))
    ap.add_argument("--epochs", type=int, default=18)
    ap.add_argument("--batch-size", type=int, default=48)
    ap.add_argument("--lr", type=float, default=3e-4,
                    help="热启动用中等学习率：骨干只需微调，新分类头需较大步长")
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--label-smoothing", type=float, default=0.1)
    ap.add_argument("--num-workers", type=int, default=4)
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument("--freeze-epochs", type=int, default=2,
                    help="前 N 轮冻结骨干，只训新分类头，避免随机头初期把骨干带偏")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    wild_dir, indoor_dir = Path(args.wild_dir), Path(args.indoor_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("30 类重训（热启动）")
    print("=" * 80)
    print(f"设备    : {device}" + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else ""))
    print(f"热启动  : {args.init or '（从零训练）'}")

    # ---------- 1. 类别一致性 ----------
    species = json.loads(Path(args.species).read_text(encoding="utf-8"))["classes"]
    wild_all = PlantDataset(str(wild_dir), transform=get_val_transforms(args.image_size))
    indoor_all = PlantDataset(str(indoor_dir), transform=get_val_transforms(args.image_size))
    for name, ds in (("野外", wild_all), ("室内", indoor_all)):
        if set(ds.classes) != set(species):
            missing = set(species) - set(ds.classes)
            extra = set(ds.classes) - set(species)
            print(f"\n[错误] {name}数据集与 species.json 不一致")
            print(f"  缺: {sorted(missing)}")
            print(f"  多: {sorted(extra)}")
            raise SystemExit(1)
        if ds.classes != wild_all.classes:
            print(f"\n[错误] {name}数据集类别顺序与野外不一致，会导致标签错位")
            raise SystemExit(1)
    classes = wild_all.classes
    num_classes = len(classes)
    print(f"类别    : {num_classes} 类（{len(ORIGINAL_20)} 原有 + {num_classes - len(ORIGINAL_20)} 新增）")
    print(f"野外    : {len(wild_all)} 张")
    print(f"室内    : {len(indoor_all)} 张")

    # knowledge_id 映射必须覆盖所有类
    name2kid = json.loads(Path(args.species_ids).read_text(encoding="utf-8"))
    unmapped = [c for c in classes if c not in name2kid]
    if unmapped:
        print(f"\n[错误] 这些类别在 species_ids.json 里没有 knowledge_id: {unmapped}")
        raise SystemExit(1)

    # ---------- 2. 切分 ----------
    n_w = len(wild_all)
    n_wtr = int(n_w * 0.8)
    g = torch.Generator().manual_seed(SEED)
    wtr_sub, wval_sub = torch.utils.data.random_split(wild_all, [n_wtr, n_w - n_wtr], generator=g)
    wild_tr_i, wild_val_i = list(wtr_sub.indices), list(wval_sub.indices)

    ind_tr_i, ind_val_i, ind_test_i = stratified_split(indoor_all, (0.70, 0.15, 0.15), SEED)
    print(f"切分    : 野外 训练{len(wild_tr_i)}/验证{len(wild_val_i)}；"
          f"室内 训练{len(ind_tr_i)}/验证{len(ind_val_i)}/测试{len(ind_test_i)}")

    tr_tf, va_tf = get_train_transforms(args.image_size), get_val_transforms(args.image_size)
    wild_tr_set = PlantDataset(str(wild_dir), transform=tr_tf)
    ind_tr_set = PlantDataset(str(indoor_dir), transform=tr_tf)
    train_ds = ConcatDataset([Subset(wild_tr_set, wild_tr_i), Subset(ind_tr_set, ind_tr_i)])

    wild_val_set = PlantDataset(str(wild_dir), transform=va_tf)
    ind_val_set = PlantDataset(str(indoor_dir), transform=va_tf)
    ind_test_set = PlantDataset(str(indoor_dir), transform=va_tf)

    bs, nw = args.batch_size, args.num_workers
    train_loader = DataLoader(train_ds, batch_size=bs, shuffle=True, num_workers=nw, pin_memory=True)
    wild_val_loader = DataLoader(Subset(wild_val_set, wild_val_i), batch_size=bs, shuffle=False,
                                 num_workers=nw, pin_memory=True)
    ind_val_loader = DataLoader(Subset(ind_val_set, ind_val_i), batch_size=bs, shuffle=False,
                                num_workers=nw, pin_memory=True)
    ind_test_loader = DataLoader(Subset(ind_test_set, ind_test_i), batch_size=bs, shuffle=False,
                                 num_workers=nw, pin_memory=True)
    print(f"训练集  : {len(train_ds)} 张（野外{len(wild_tr_i)} + 室内{len(ind_tr_i)}）\n")

    # ---------- 3. 模型 + 热启动 ----------
    # 没有热启动权重时**必须**用 ImageNet 预训练权重。
    # 这里原来写死 pretrained=False（依赖 --init 提供权重），一旦传 --init ""（换骨干网
    # 时无法热启动，只能走这条路），骨干就会是**随机初始化**的 —— 在 1 万多张图上
    # 从零训 EfficientNet 效果远差于微调 ImageNet 权重，而且前几轮准确率只有个位数
    # （2026-09-30 实测：第 1/2 轮 train 4.6% / 7.6%），很容易被误当成"还没收敛"。
    has_init = bool(args.init) and Path(args.init).is_file()
    model = create_model(num_classes, pretrained=not has_init, arch=args.arch)
    transferred = 0
    if args.init and Path(args.init).is_file():
        state = torch.load(args.init, map_location="cpu", weights_only=True)
        own = model.state_dict()
        keep = {k: v for k, v in state.items() if k in own and own[k].shape == v.shape}
        dropped = [k for k in state if k not in keep]
        model.load_state_dict(keep, strict=False)
        transferred = len(keep)
        print(f"热启动: 继承 {len(keep)}/{len(state)} 个权重张量")
        print(f"        丢弃 {len(dropped)} 个（形状不符，应只有旧分类头）: {dropped}")
    model = model.to(device)

    # 前 N 轮冻结骨干：新分类头是随机初始化的，初期梯度很大，
    # 若此时骨干一起更新，会把已经学好的特征带偏 —— 热启动继承的权重与
    # ImageNet 预训练权重都属于「已经学好」，两种情况都该先冻一下。
    # （原来只在 args.init 存在时冻结，改成用预训练权重的路径后就不再适用。）
    if args.freeze_epochs > 0:
        for p in model.features.parameters():
            p.requires_grad = False
        print(f"前 {args.freeze_epochs} 轮冻结骨干，只训新分类头"
              f"（起始权重：{'热启动 ' + args.init if has_init else 'ImageNet 预训练'}）")

    def make_opt(lr):
        ps = [p for p in model.parameters() if p.requires_grad]
        return torch.optim.AdamW(ps, lr=lr, weight_decay=args.weight_decay), ps

    opt, trainable = make_opt(args.lr)
    sched = CosineAnnealingLR(opt, T_max=args.epochs, eta_min=args.lr * 0.01)
    print(f"可训练参数: {sum(p.numel() for p in trainable) / 1e6:.2f}M\n")

    crit = nn.CrossEntropyLoss(label_smoothing=args.label_smoothing)

    idx20 = [i for i, c in enumerate(classes) if c in ORIGINAL_20]
    print("-" * 80)
    print(f"{'轮':>3} {'耗时':>6} {'train':>7} {'野外val':>8} {'室内val':>8} {'和':>7} {'原20类':>7}")
    print("-" * 80)

    best_score, best_epoch, history = -1.0, 0, []
    for epoch in range(args.epochs):
        t0 = time.time()

        if args.freeze_epochs > 0 and epoch == args.freeze_epochs:
            for p in model.features.parameters():
                p.requires_grad = True
            opt, trainable = make_opt(args.lr)
            sched = CosineAnnealingLR(opt, T_max=args.epochs - epoch, eta_min=args.lr * 0.01)
            print(f"  [解冻] 第 {epoch + 1} 轮起骨干参与训练，"
                  f"可训练参数 {sum(p.numel() for p in trainable) / 1e6:.2f}M")

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

        w_acc, _, _ = evaluate(model, wild_val_loader, device)
        i_acc, _, _ = evaluate(model, ind_val_loader, device)
        o_acc, _, o_n = evaluate(model, wild_val_loader, device, subset_classes=idx20)
        score = w_acc + i_acc
        dt = time.time() - t0

        print(f"{epoch + 1:3d} {dt:5.0f}s {tc / tt:7.4f} {w_acc:8.4f} {i_acc:8.4f} "
              f"{score:7.4f} {o_acc:7.4f}")

        history.append({"epoch": epoch + 1, "train_acc": tc / tt, "wild_val_acc": w_acc,
                        "indoor_val_acc": i_acc, "orig20_wild_acc": o_acc, "score": score,
                        "lr": opt.param_groups[0]["lr"]})

        if score > best_score:
            best_score, best_epoch = score, epoch + 1
            torch.save(model.state_dict(), out_dir / "best_model.pth")
            print(f"      [best] 已保存")

        (out_dir / "history.json").write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- 4. 最终评估 ----------
    print("-" * 80)
    final = create_model(num_classes, pretrained=False, arch=args.arch)
    final.load_state_dict(torch.load(out_dir / "best_model.pth", map_location="cpu", weights_only=True))
    final = final.to(device)

    r = {}
    r["wild_val"], _, wn = evaluate(final, wild_val_loader, device)
    r["indoor_val"], _, ivn = evaluate(final, ind_val_loader, device)
    r["indoor_test"], _, itn = evaluate(final, ind_test_loader, device)
    r["wild_val_orig20"], _, _ = evaluate(final, wild_val_loader, device, subset_classes=idx20)
    r["indoor_test_orig20"], _, _ = evaluate(final, ind_test_loader, device, subset_classes=idx20)

    # 新增 10 类的单独表现
    idx_new = [i for i, c in enumerate(classes) if c not in ORIGINAL_20]
    r["wild_val_new10"], _, _ = evaluate(final, wild_val_loader, device, subset_classes=idx_new)
    r["indoor_test_new10"], _, _ = evaluate(final, ind_test_loader, device, subset_classes=idx_new)

    print(f"\n最优轮次: 第 {best_epoch} 轮\n")
    print("=" * 80)
    print("最终结果")
    print("=" * 80)
    print(f"野外验证集 ({wn:4d}张)          {r['wild_val']:.4f}")
    print(f"  其中 原20类            {r['wild_val_orig20']:.4f}")
    print(f"  其中 新增10类          {r['wild_val_new10']:.4f}")
    print(f"室内验证集 ({ivn:4d}张)          {r['indoor_val']:.4f}")
    print(f"室内测试集 ({itn:4d}张，选优未用) {r['indoor_test']:.4f}")
    print(f"  其中 原20类            {r['indoor_test_orig20']:.4f}")
    print(f"  其中 新增10类          {r['indoor_test_new10']:.4f}")
    print()
    print("对照：20 类版本的旧指标 —— 野外验证 0.9225 / 室内测试 0.8591")
    print("扩类后整体下降属正常（分母多了 10 个更难的类），")
    print("关键看「原20类」是否基本保持，以及「新增10类」是否可用。")

    # labels.json（供推理服务映射 knowledgeId）
    labels = [{"name": c, "id": i, "knowledge_id": name2kid[c]} for i, c in enumerate(classes)]
    (out_dir / "labels.json").write_text(
        json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")

    (out_dir / "result.json").write_text(json.dumps({
        "num_classes": num_classes,
        "best_epoch": best_epoch,
        "init": args.init,
        "transferred_tensors": transferred,
        "sizes": {"wild_train": len(wild_tr_i), "wild_val": len(wild_val_i),
                  "indoor_train": len(ind_tr_i), "indoor_val": len(ind_val_i),
                  "indoor_test": len(ind_test_i)},
        "metrics": r,
        "baseline_20class": {"wild_val": 0.9225, "indoor_test": 0.8591},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n产物: {out_dir}/ (best_model.pth / labels.json / history.json / result.json)")


if __name__ == "__main__":
    main()
