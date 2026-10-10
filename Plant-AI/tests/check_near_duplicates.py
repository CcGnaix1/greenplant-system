"""近重复照片分析 —— 判断测试集准确率里有多少是「近似重复照」撑起来的。

为什么查这个
------------
iNat 的采集照常有「同一株植物连拍数张」的情况（同一次观察上传多张，角度/光线略有差异）。
如果训练集与测试集按**图片**随机切分，这些近似照会一半进训练、一半进测试 ——
模型在测试集上等于见到了「背过的题」，准确率虚高，而补同类数据也不会有任何泛化收益。

判据：
  * 测试集里有近重复落在训练集的比例（leak_rate）—— 高则准确率被高估
  * 类内近重复密度 —— 高则说明该类的「200 张」实际只是几十株的多次拍摄，
    再加同类数据是无效投入

用 dhash（16x16 差分哈希）判近似：缩放到灰度 16x16、比较相邻像素明暗，得到 256 位指纹。
汉明距离越小越像。dhash 对亮度/对比度变化不敏感，比 md5 更能抓住「同一株重拍」。
"""

import hashlib
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path("C:/Plant/plant-ai")
sys.path.insert(0, str(ROOT / "ml"))

from dataset import PlantDataset  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SEED = 42
HASH_BITS = 16
HASH_SIZE = HASH_BITS * HASH_BITS          # resize((W+1, H)) → 16x16 位
# 多层阈值：越严格越接近「同一张照片重传」，越松越接近「同一株换角度重拍」。
DUP_THRESHOLDS = (4, 8, 16, 24)
DUP_THRESHOLD = 8                           # 泄漏判定用的主阈值


def stratified_split(dataset, fracs, seed):
    """与 analyze_errors.py 完全一致的切分（复现同一份测试集）。"""
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


def dhash(path: str, bits: int = HASH_BITS) -> np.ndarray:
    """差分哈希：横向比较相邻像素，返回 bits*(bits-1) 位的 0/1 数组。"""
    img = Image.open(path).convert("L").resize((bits + 1, bits), Image.LANCZOS)
    a = np.asarray(img, dtype=np.int16)
    return (a[:, 1:] > a[:, :-1]).flatten()


def hamming_matrix(codes: np.ndarray) -> np.ndarray:
    """codes: (n, B) bool → (n, n) 汉明距离。用 XOR + 求和，n 不大时够快。"""
    x = codes.astype(np.uint8)
    return (x[:, None, :] != x[None, :, :]).sum(axis=2)


def main():
    ds = PlantDataset(str(ROOT / "data" / "plants_indoor"))
    classes = ds.classes
    tr_i, va_i, te_i = stratified_split(ds, (0.70, 0.15, 0.15), SEED)
    role = {}
    for i in tr_i:
        role[i] = "train"
    for i in va_i:
        role[i] = "val"
    for i in te_i:
        role[i] = "test"

    n = len(ds.samples)
    print("=" * 88)
    print(f"近重复分析：室内集 {n} 张，切分 70/15/15（与 analyze_errors.py 同一份）")
    print(f"dhash {HASH_BITS}x{HASH_BITS}，汉明距离 <= {DUP_THRESHOLD} 判为近似重复")
    print("=" * 88)

    codes = np.zeros((n, HASH_SIZE), dtype=bool)
    failed = []
    for i, (p, _) in enumerate(ds.samples):
        try:
            h = dhash(p)
            if h.shape[0] != HASH_SIZE:
                raise ValueError(f"哈希长度 {h.shape[0]} != {HASH_SIZE}")
            codes[i] = h
        except Exception as e:  # noqa: BLE001
            failed.append((p, f"{type(e).__name__}: {e}"))
    if failed:
        # 早期版本这里静默 pass，导致哈希全零 → 所有图被误判成互相重复。别再用空 except。
        print(f"[错误] {len(failed)} 张图算哈希失败，分析不可信。前 3 例：")
        for p, e in failed[:3]:
            print(f"   {p}  {e}")
        raise SystemExit(1)

    # ---------- 类内近重复 ----------
    print(f"\n类内相似度（汉明距离：越小越像；两张**无关**图约 128，为随机基线）")
    print(f"\n{'品种':10s} {'张数':>5s} {'中位':>6s} {'最小':>6s} "
          + " ".join(f"{'<='+str(t):>7s}" for t in DUP_THRESHOLDS))
    print("-" * 88)
    by_class = defaultdict(list)
    for i, (_, lab) in enumerate(ds.samples):
        by_class[lab].append(i)

    weak = {"白掌", "芦荟", "薄荷", "橡皮树", "金钱树", "铜钱草", "龙血树"}
    rows = []
    for ci, cname in enumerate(classes):
        idxs = by_class[ci]
        if len(idxs) < 2:
            continue
        sub = codes[idxs]
        h = hamming_matrix(sub)
        iu = np.triu_indices(len(idxs), k=1)
        d = h[iu]
        cnts = {t: int((d <= t).sum()) for t in DUP_THRESHOLDS}
        rows.append({"name": cname, "n": len(idxs), "cnts": cnts,
                     "median": float(np.median(d)), "min": int(d.min())})
        mark = " *" if cname in weak else ""
        print(f"{cname:10s} {len(idxs):5d} {np.median(d):6.0f} {d.min():6d} "
              + " ".join(f"{cnts[t]:7d}" for t in DUP_THRESHOLDS) + mark)

    print("\n（* = 室内召回偏低的品种）")
    tot_pairs = sum(r["n"] * (r["n"] - 1) // 2 for r in rows)
    for t in DUP_THRESHOLDS:
        s = sum(r["cnts"][t] for r in rows)
        print(f"阈值 <={t:2d}: {s:7d} 对（占全部 {tot_pairs} 对的 {s / tot_pairs:.2%}）")

    # ---------- 跨角色泄漏 ----------
    print("\n" + "=" * 88)
    print("测试集泄漏检查（关键）")
    print("=" * 88)
    n_test = len(te_i)
    for t in DUP_THRESHOLDS:
        leak_test = leak_val = 0
        detail = {}
        for ci, cname in enumerate(classes):
            idxs = by_class[ci]
            te = [i for i in idxs if role[i] == "test"]
            tr = [i for i in idxs if role[i] == "train"]
            va = [i for i in idxs if role[i] == "val"]
            if not te or not tr:
                continue
            h = (codes[te][:, None, :] != codes[tr][None, :, :]).sum(axis=2)
            hit = (h <= t).any(axis=1)
            n_hit = int(hit.sum())
            leak_test += n_hit
            if n_hit:
                detail[cname] = n_hit
            if va:
                h2 = (codes[te][:, None, :] != codes[va][None, :, :]).sum(axis=2)
                leak_val += int((h2 <= t).any(axis=1).sum())
        print(f"阈值 <={t:2d}: 测试集 {n_test} 张中有 {leak_test:4d} 张在训练集里有近似照 "
              f"（{leak_test / n_test:5.1%}）；其中 {leak_val:4d} 张在验证集里也有"
              f"（{leak_val / n_test:5.1%}）")
        if t == DUP_THRESHOLD and detail:
            top = sorted(detail.items(), key=lambda x: -x[1])[:8]
            print("     泄漏最多的品种: " + "  ".join(f"{k}={v}" for k, v in top))

    print("\n解读：")
    print("  * <=4/<=8 那两档才是「几乎同一张照片」。它们泄漏 → 准确率被高估")
    print("  * <=16/<=24 那两档包含「同一株换角度重拍」，是泛化风险但不算作弊")
    print("  * 类内中位距离接近 128（随机基线）→ 类内是不同植株，多样性其实是够的，")
    print("    那么「再采同类更多照片」的收益有限，瓶颈可能在别处")


if __name__ == "__main__":
    main()
