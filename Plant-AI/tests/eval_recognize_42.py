"""42 类品种识别率评估 —— 复现训练时切分，在**未参与训练**的图上量化识别率。

为什么必须复现切分
------------------
随机抽目录里的图，很可能抽到训练集里的，测出来的是「记忆分」而非识别率。
这里用与 train30.py 完全一致的切分：
    室内 stratified_split(0.70/0.15/0.15, seed=42) 的第三段 = 测试集（选优未用）
    野外 random_split(0.8/0.2, seed=42) 的第二段 = 验证集
室内按类独立播种，与目录顺序无关，跨机可复现。

两条预处理路径
--------------
单视角：与生产 recognizer.build_val_transform 一致（parity 校验已确认 = 训练记录 0.9231）
TTA  ：生产实际启用的 3 视角平均（1.0 / 0.88 / 1.12，不含翻转）

判据：室内测试集 TTA 准确率应 ≥ 单视角（0.9231），若明显更低说明 TTA 实现与生产不一致。
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path("C:/Plant/plant-ai")
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "service"))

from dataset import PlantDataset                    # noqa: E402
from train30 import stratified_split                # noqa: E402
from recognizer import (                            # noqa: E402
    SPECIES_IMAGE_SIZE, TTA_SCALES, TTA_ENABLED,
    build_val_transform, build_val_transform_from_r,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SEED = 42


def softmax(x):
    e = np.exp(x - x.max())
    return e / e.sum()


def build_transforms():
    """返回 (single_tf, tta_tfs)。tta_tfs 为 None 表示关闭。"""
    single = build_val_transform(SPECIES_IMAGE_SIZE)
    if not TTA_ENABLED:
        return single, None
    r = int(SPECIES_IMAGE_SIZE * 1.14)
    tta = [build_val_transform_from_r(int(r * s), SPECIES_IMAGE_SIZE) for s in TTA_SCALES]
    return single, tta


def evaluate(ds, indices, sess, single_tf, tta_tfs, labels):
    n = len(indices)
    hit1_s = hit1_t = hit3_t = 0
    per_class_tot = defaultdict(int)
    per_class_hit = defaultdict(int)
    confus = defaultdict(int)          # (true_name, pred_name) -> 次数
    highconf_err = []                  # 高置信错误（置信度 >=0.8 且判错）
    for i in indices:
        p, lab = ds.samples[i]
        img = np.array(Image.open(p).convert("RGB"))
        true_name = labels[lab]["name"]

        x1 = single_tf(image=img)["image"].unsqueeze(0).numpy().astype(np.float32)
        lo_s = sess.run(None, {"input": x1})[0][0]
        pred_s = int(lo_s.argmax())

        # TTA：3 视角堆成一个 batch，一次推理
        if tta_tfs:
            xb = np.concatenate(
                [tf(image=img)["image"].unsqueeze(0).numpy() for tf in tta_tfs], axis=0
            ).astype(np.float32)
            logits = sess.run(None, {"input": xb})[0]           # (3, C)
            probs = np.mean([softmax(logits[k]) for k in range(logits.shape[0])], axis=0)
        else:
            probs = softmax(lo_s)
        pred_t = int(probs.argmax())

        hit1_s += int(pred_s == lab)
        hit1_t += int(pred_t == lab)
        top3 = np.argsort(probs)[::-1][:3]
        hit3_t += int(lab in top3)

        per_class_tot[true_name] += 1
        per_class_hit[true_name] += int(pred_t == lab)
        if pred_t != lab:
            confus[(true_name, labels[pred_t]["name"])] += 1
            if probs[pred_t] >= 0.80:
                highconf_err.append((true_name, labels[pred_t]["name"], float(probs[pred_t])))
    return {
        "n": n, "hit1_single": hit1_s, "hit1_tta": hit1_t, "hit3_tta": hit3_t,
        "per_class_tot": per_class_tot, "per_class_hit": per_class_hit,
        "confus": confus, "highconf_err": highconf_err,
    }


def report(title, r, labels):
    n = r["n"]
    print("\n" + "=" * 78)
    print(f"{title}（{n} 张，训练不可见）")
    print("=" * 78)
    print(f"  单视角 Top-1   {r['hit1_single'] / n:.4f}  ({r['hit1_single']}/{n})")
    print(f"  TTA    Top-1   {r['hit1_tta'] / n:.4f}  ({r['hit1_tta']}/{n})")
    print(f"  TTA    Top-3   {r['hit3_tta'] / n:.4f}  ({r['hit3_tta']}/{n})")

    worst = sorted(r["per_class_tot"], key=lambda c: r["per_class_hit"][c] / r["per_class_tot"][c])
    print(f"\n  召回最低的 10 个类：")
    for c in worst[:10]:
        tot, hit = r["per_class_tot"][c], r["per_class_hit"][c]
        print(f"    {c:8s} {hit / tot:.3f}  ({hit}/{tot})")
    print(f"  召回最高的 5 个类：")
    for c in worst[::-1][:5]:
        tot, hit = r["per_class_tot"][c], r["per_class_hit"][c]
        print(f"    {c:8s} {hit / tot:.3f}  ({hit}/{tot})")

    print(f"\n  最常混淆对（真实 → 误判）：")
    for (t, p), cnt in sorted(r["confus"].items(), key=lambda kv: -kv[1])[:8]:
        print(f"    {t} → {p}  ×{cnt}")

    print(f"\n  高置信错误（误判且置信度≥0.80）：{len(r['highconf_err'])} 条")
    for t, p, c in sorted(r["highconf_err"], key=lambda x: -x[2])[:10]:
        print(f"    {t} → {p}  {c:.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx", default=str(ROOT / "output" / "plant_model.onnx"),
                    help="默认测线上部署的那份")
    ap.add_argument("--labels", default=str(ROOT / "output" / "labels.json"))
    args = ap.parse_args()

    print("=" * 78)
    print("42 类品种识别率评估")
    print("=" * 78)
    print(f"ONNX  : {args.onnx}")
    print(f"分辨率: {SPECIES_IMAGE_SIZE}   TTA: {TTA_ENABLED} {TTA_SCALES if TTA_ENABLED else ''}")

    with open(args.labels, "r", encoding="utf-8") as f:
        labels = json.load(f)
    print(f"类别数: {len(labels)}")

    import onnxruntime as ort
    sess = ort.InferenceSession(args.onnx, providers=["CPUExecutionProvider"])
    in_shape = sess.get_inputs()[0].shape
    assert in_shape[2] == SPECIES_IMAGE_SIZE, f"ONNX 输入 {in_shape} 与配置 {SPECIES_IMAGE_SIZE} 不符"

    single_tf, tta_tfs = build_transforms()

    # ---- 室内测试集（选优未用）----
    indoor = PlantDataset(str(ROOT / "data" / "plants_indoor"))
    assert list(indoor.classes) == [l["name"] for l in labels], \
        "室内数据集类别顺序与 labels.json 不一致，标签会错位"
    _, _, ind_test_i = stratified_split(indoor, (0.70, 0.15, 0.15), SEED)
    r_ind = evaluate(indoor, ind_test_i, sess, single_tf, tta_tfs, labels)
    report("室内测试集", r_ind, labels)

    # ---- 野外验证集 ----
    wild = PlantDataset(str(ROOT / "data" / "plants"))
    n_w = len(wild)
    n_wtr = int(n_w * 0.8)
    g = torch.Generator().manual_seed(SEED)
    _, wval = torch.utils.data.random_split(wild, [n_wtr, n_w - n_wtr], generator=g)
    r_wild = evaluate(wild, list(wval.indices), sess, single_tf, tta_tfs, labels)
    report("野外验证集", r_wild, labels)

    print("\n" + "=" * 78)
    print("小结")
    print("=" * 78)
    print(f"  室内测试 TTA Top-1 = {r_ind['hit1_tta'] / r_ind['n']:.4f}（部署模型的实际识别率）")
    print(f"  野外验证 TTA Top-1 = {r_wild['hit1_tta'] / r_wild['n']:.4f}")
    dev = abs(r_ind['hit1_single'] / r_ind['n'] - 0.9231)
    print(f"  室内单视角与训练记录 0.9231 差 {dev:.4f}"
          + ("  （一致，模型与训练产物吻合）" if dev < 0.01 else "  ⚠ 偏差>1点，检查产物"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
