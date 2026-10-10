"""分析当前模型在室内测试集上的错误分布 —— 用来决定下一批该采什么数据。

为什么先做这个：盲目「多采一些」只会重复模型已经学会的分布，
真正该补的是它反复出错的那部分。本脚本复现 finetune.py 的三段切分，
在**未参与选优的测试集**上定位失败模式：
  * 哪些类拖后腿（召回率低）
  * 哪些类对经常互相误判
  * 哪些是「高置信度错误」（最危险，用户完全无从察觉）
"""

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Subset

ROOT = Path("C:/Plant/plant-ai")
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "service"))

from dataset import PlantDataset, get_val_transforms  # noqa: E402
from train import create_model                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SEED = 42
if len(sys.argv) > 1 and sys.argv[1] == "--wild":
    # 想看野外验证集的错误分布就加 --wild
    DATA = ROOT / "data" / "plants"
    SPLIT = "wild"
else:
    DATA = ROOT / "data" / "plants_indoor"
    SPLIT = "indoor"

MODEL = ROOT / "output" / "plant_model.onnx"


def stratified_split(dataset, fracs, seed):
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


def main():
    names = [x["name"] for x in json.loads((ROOT / "output" / "labels.json").read_text(encoding="utf-8"))]
    ds = PlantDataset(str(DATA), transform=get_val_transforms(224))
    classes = ds.classes

    if SPLIT == "indoor":
        _, val_i, test_i = stratified_split(ds, (0.70, 0.15, 0.15), SEED)
        idx = test_i
        title = "室内测试集（未参与选优）"
    else:
        gen = torch.Generator().manual_seed(SEED)
        n = len(ds)
        tr = int(n * 0.8)
        _, val_sub = torch.utils.data.random_split(ds, [tr, n - tr], generator=gen)
        idx = list(val_sub.indices)
        title = "野外验证集"

    print("=" * 88)
    print(f"错误分析：{title}  共 {len(idx)} 张")
    print("=" * 88)

    import onnxruntime as ort
    sess = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])

    paths, labels, preds, confs, probs_all = [], [], [], [], []
    for i in idx:
        p, lab = ds.samples[i]
        img = np.array(Image.open(p).convert("RGB"))
        x = ds.transform(image=img)["image"].unsqueeze(0).numpy().astype(np.float32)
        lo = sess.run(None, {"input": x})[0][0]
        e = np.exp(lo - lo.max())
        pr = e / e.sum()
        paths.append(p)
        labels.append(lab)
        preds.append(int(pr.argmax()))
        confs.append(float(pr.max()))
        probs_all.append(pr)

    labels = np.array(labels)
    preds = np.array(preds)
    confs = np.array(confs)

    acc = (labels == preds).mean()
    print(f"\n总体准确率: {acc:.4f} ({int((labels==preds).sum())}/{len(labels)})\n")

    # ---- 各类召回率 ----
    print("各类召回率（低=该类被认不出，是采集重点）:")
    print("-" * 88)
    rec = []
    for ci, cname in enumerate(classes):
        m = labels == ci
        if m.sum() == 0:
            continue
        r = (preds[m] == ci).mean()
        rec.append((r, cname, int(m.sum())))
    for r, cname, n in sorted(rec):
        flag = "  <-- 偏低" if r < 0.80 else ""
        print(f"  {cname:10s} 召回 {r:.3f}  ({int(r*n)}/{n}){flag}")

    # ---- 混淆对 ----
    print("\n最常被搞混的类别对（真实 -> 误判，次数）:")
    print("-" * 88)
    wrong = labels != preds
    pairs = Counter()
    for t, p in zip(labels[wrong], preds[wrong]):
        pairs[(classes[t], classes[p])] += 1
    if not pairs:
        print("  无")
    for (t, p), n in pairs.most_common(12):
        print(f"  {t:10s} -> {p:10s} {n} 次")

    # ---- 高置信度错误（最危险）----
    print("\n高置信度错误（置信度>=0.7 却答错 —— 用户会当真，最该优先解决）:")
    print("-" * 88)
    hi = wrong & (confs >= 0.7)
    if hi.sum() == 0:
        print("  无（说明模型没有「自信地错」，实际体验尚可）")
    else:
        order = np.argsort(-confs)
        shown = 0
        for i in order:
            if not hi[i]:
                continue
            print(f"  {confs[i]:.3f}  {classes[labels[i]]:8s} -> 误判 {classes[preds[i]]:8s}  {Path(paths[i]).name}")
            shown += 1
            if shown >= 12:
                break
        print(f"  ... 共 {int(hi.sum())} 张")

    # ---- 低置信度（可由候选列表兜底）----
    lo_mask = wrong & (confs < 0.5)
    print(f"\n低置信度错误（<0.5）: {int(lo_mask.sum())} 张 —— 前端会给出候选列表，用户体验影响较小")

    # ---- 落盘，便于人工看具体图 ----
    rows = []
    for i in range(len(labels)):
        rows.append({
            "image": paths[i],
            "true": classes[labels[i]],
            "pred": classes[preds[i]],
            "conf": round(float(confs[i]), 4),
            "correct": bool(labels[i] == preds[i]),
        })
    out = Path(f"C:/Plant/tests/results/error_analysis_{SPLIT}.json")
    out.write_text(json.dumps({
        "split": SPLIT, "total": len(labels), "accuracy": round(float(acc), 4),
        "per_class_recall": {c: round(float(r), 4) for r, c, _ in rec},
        "confusion_pairs": [{"true": t, "pred": p, "count": n} for (t, p), n in pairs.most_common()],
        "high_conf_errors": int(hi.sum()),
        "items": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n明细已存: {out}")


if __name__ == "__main__":
    main()
