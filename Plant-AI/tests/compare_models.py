"""在同一批「两个模型都没训过」的图上对比新旧模型 —— 回答「扩类有没有把原有类搞坏」。

为什么不能直接用各自的测试集比
------------------------------
两个模型的训练切分不同（320 模型用的是**旧的共享 generator**切分，新模型用**按类独立播种**
的新切分），所以：
    * 旧模型在**新测试集**上会偏高 —— 新测试集里有约 10% 的图是它训练时见过的
      （实测：旧模型在新测试集 0.9804 vs 在它自己的测试集 0.9170，30 个类全体 +6 点）
    * 新模型在**旧测试集**上同理偏高
所以必须只在「两边的训练集都不包含」的图上比。这里的过程：

    eval = (旧测试集 ∪ 新测试集) − (旧训练集 ∪ 新训练集)

旧切分用 `old_stratified_split` **原样复刻**（共享 generator 那版），并用
`results/error_analysis_indoor.json` 里记录的旧测试集做**自校验** —— 复刻对了才说明
重算出的旧训练集可信（自校验失败会直接报错退出，不会带着错的口径继续）。
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset

ROOT = Path("C:/Plant/plant-ai")
RESULTS = Path("C:/Plant/tests/results")
sys.path.insert(0, str(ROOT / "ml"))

from dataset import PlantDataset, get_val_transforms   # noqa: E402
from train import create_model                         # noqa: E402
from train30 import stratified_split                   # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SEED = 42
ORIGINAL_30 = [
    "兰花", "发财树", "吊兰", "多肉植物", "富贵竹", "常春藤", "文竹", "栀子花",
    "橡皮树", "琴叶榕", "白掌", "绿萝", "茉莉花", "薄荷", "虎皮兰", "袖珍椰子",
    "迷迭香", "铜钱草", "鹅掌柴", "龟背竹",
    "金钱树", "万年青", "龙血树", "红掌", "鹤望兰", "竹芋", "芦荟", "豆瓣绿",
    "波斯顿蕨", "散尾葵",
]


class PathDataset(Dataset):
    def __init__(self, paths, tf):
        self.paths, self.tf = paths, tf

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, i):
        img = np.array(Image.open(self.paths[i]).convert("RGB"))
        return self.tf(image=img)["image"], 0


def old_stratified_split(dataset, fracs, seed):
    """旧实现（共享 generator）——原样复刻，用于重算 320 模型的训练集。

    不要"改进"这个函数：它的价值就是逐位复现历史行为。新实现见 train30.stratified_split。
    """
    g = torch.Generator().manual_seed(seed)
    by_class = {}
    for idx, (_, label) in enumerate(dataset.samples):
        by_class.setdefault(label, []).append(idx)
    groups = [[] for _ in fracs]
    for label, idxs in by_class.items():
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


class _View:
    """把 42 类数据集"缩回"成当初的 30 类视图（标签重映射到 0..29）。"""

    def __init__(self, ds, keep):
        keepset = set(keep)
        names = sorted(keep)
        self.classes = names
        idx = {n: i for i, n in enumerate(names)}
        self.samples = [(p, idx[ds.classes[l]]) for p, l in ds.samples if ds.classes[l] in keepset]


def load_model(model_dir: Path, arch: str, device):
    labels = json.loads((model_dir / "labels.json").read_text(encoding="utf-8"))
    names = [x["name"] for x in labels]
    m = create_model(len(names), pretrained=False, arch=arch)
    m.load_state_dict(torch.load(model_dir / "best_model.pth", map_location="cpu",
                                 weights_only=True))
    return m.to(device).eval(), names


@torch.no_grad()
def eval_on(model, names, paths, truth, device, size, bs=32):
    idx_of = {n: i for i, n in enumerate(names)}
    ds = PathDataset(paths, get_val_transforms(size))
    loader = DataLoader(ds, batch_size=bs, shuffle=False, num_workers=4, pin_memory=True)
    hit = same = 0
    per = {}
    for (images, _), start in zip(loader, range(0, len(paths), bs)):
        pred = model(images.to(device)).argmax(1).cpu().tolist()
        for k, pr in enumerate(pred):
            tn = truth[start + k]
            t = idx_of.get(tn)
            if t is None:
                continue
            same += 1
            ok = int(pr == t)
            hit += ok
            c = per.setdefault(tn, [0, 0])
            c[0] += ok
            c[1] += 1
    return (hit / same if same else 0.0), same, per


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", default=str(ROOT / "output_v30_320"))
    ap.add_argument("--old-arch", default="mobilenet_v3_large")
    ap.add_argument("--new", required=True, help="新模型目录（含 labels.json / best_model.pth）")
    ap.add_argument("--new-arch", default="efficientnet_b0")
    ap.add_argument("--size", type=int, default=320)
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    indoor = PlantDataset(str(ROOT / "data" / "plants_indoor"))

    # ---------- 新切分（类独立） ----------
    ntr, nva, nte = stratified_split(indoor, (0.70, 0.15, 0.15), SEED)
    new_train = {indoor.samples[i][0] for i in ntr}
    new_test = [indoor.samples[i][0] for i in nte]
    new_test_truth = [indoor.classes[indoor.samples[i][1]] for i in nte]

    # ---------- 旧切分（复刻） + 自校验 ----------
    view = _View(indoor, ORIGINAL_30)
    otr, ova, ote = old_stratified_split(view, (0.70, 0.15, 0.15), SEED)
    old_train = {view.samples[i][0] for i in otr}
    old_test = {view.samples[i][0] for i in ote}

    saved = json.loads((RESULTS / "error_analysis_indoor.json").read_text(encoding="utf-8"))["items"]
    saved_paths = {it["image"] for it in saved}
    inter = old_test & saved_paths
    print("=" * 80)
    print("旧切分复刻自校验")
    print("=" * 80)
    print(f"  复刻出的旧测试集 {len(old_test)} 张；json 记录 {len(saved_paths)} 张")
    print(f"  重合 {len(inter)} 张（{len(inter) / max(1, len(saved_paths)):.1%}）")
    if len(inter) / max(1, len(saved_paths)) < 0.99:
        raise SystemExit("[失败] 旧切分复刻不对，无法重算旧训练集。"
                         "不要在此前提下做对比（口径不可信）。")
    print("  自校验通过：旧切分复刻正确，重算出的旧训练集可信\n")

    # ---------- 两模型都没训过的评估集 ----------
    # 直接用「整个图片池 − (旧训练集 ∪ 新训练集)」：
    # 这些图两个模型都没见过，无论它原本属于哪个 val/test 段，都是合法的留出数据。
    # 比起"只在两个测试集里找"，这样能多出近一倍的样本。
    bad = old_train | new_train
    eval_paths, eval_truth = [], []
    for p, l in indoor.samples:
        if p not in bad:
            eval_paths.append(p)
            eval_truth.append(indoor.classes[l])
    print("评估集 = 整个图片池 − (旧训练集 ∪ 新训练集)")
    print(f"  旧训练集 {len(old_train)} 张 / 新训练集 {len(new_train)} 张")
    print(f"  → 两模型都没训过 {len(eval_paths)} 张（占池子 {len(eval_paths) / len(indoor.samples):.1%}）\n")

    old_m, old_names = load_model(Path(args.old), args.old_arch, device)
    new_m, new_names = load_model(Path(args.new), args.new_arch, device)
    common = [c for c in old_names if c in set(new_names)]

    print("=" * 80)
    print(f"旧 {Path(args.old).name:22s} {len(old_names):3d} 类  {args.old_arch}")
    print(f"新 {Path(args.new).name:22s} {len(new_names):3d} 类  {args.new_arch}")
    print(f"共同类 {len(common)}；分辨率 {args.size}")
    print("=" * 80)

    sel = [(p, t) for p, t in zip(eval_paths, eval_truth) if t in set(common)]
    ps, ts = [x[0] for x in sel], [x[1] for x in sel]
    a_old, n_, per_old = eval_on(old_m, old_names, ps, ts, device, args.size)
    a_new, _, per_new = eval_on(new_m, new_names, ps, ts, device, args.size)
    print(f"\n【可归因对比】原 30 类，{n_} 张（两模型均未训练过）")
    print(f"  旧模型 {a_old:.4f}")
    print(f"  新模型 {a_new:.4f}   Δ {a_new - a_old:+.4f}")

    print(f"\n  逐类（只看退化明显的）:")
    rows = []
    for c in common:
        o, n2 = per_old.get(c), per_new.get(c)
        if not o or not n2:
            continue
        rows.append((n2[0] / n2[1] - o[0] / o[1], c, o, n2))
    for d, c, o, n2 in sorted(rows)[:6]:
        print(f"    {c:10s} {o[0] / o[1]:.3f} → {n2[0] / n2[1]:.3f}  {d:+.3f}  (n={o[1]})")
    if max(rows)[0] > 0:
        print(f"  提升最多:")
        for d, c, o, n2 in sorted(rows, reverse=True)[:3]:
            print(f"    {c:10s} {o[0] / o[1]:.3f} → {n2[0] / n2[1]:.3f}  {d:+.3f}  (n={o[1]})")

    # ---------- 新模型自己的测试集（含新类，全 42 类）----------
    a_full, n_full, per_full = eval_on(new_m, new_names, new_test, new_test_truth, device, args.size)
    print(f"\n【新模型自身】新测试集 {n_full} 张（42 类）: {a_full:.4f}")
    new_only = [c for c in new_names if c not in set(old_names)]
    if new_only:
        sel = [(p, t) for p, t in zip(new_test, new_test_truth) if t in set(new_only)]
        if sel:
            aa, cc, perN = eval_on(new_m, new_names, [x[0] for x in sel],
                                   [x[1] for x in sel], device, args.size)
            print(f"  其中新增 {len(new_only)} 类: {aa:.4f}（{cc} 张）")
            print(f"  {'新类':10s} {'召回':>7s} {'样本':>5s}")
            for c in sorted(perN, key=lambda k: perN[k][0] / perN[k][1]):
                h, t = perN[c]
                tag = "  ←偏低" if h / t < 0.8 else ""
                print(f"  {c:10s} {h / t:7.3f} {t:5d}{tag}")

    (RESULTS / "compare_models.json").write_text(json.dumps({
        "old": str(args.old), "new": str(args.new),
        "eval_set": len(eval_paths), "common": len(common),
        "old_acc": a_old, "new_acc": a_new, "delta": a_new - a_old,
        "new_model_own_test": a_full,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n写入 {RESULTS / 'compare_models.json'}")


if __name__ == "__main__":
    main()
