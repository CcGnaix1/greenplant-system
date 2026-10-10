"""症状模型的诚实评估：域内 + 跨域。

为什么要单独做跨域这一环
------------------------
症状模型训练在 PlantVillage 上，那是**实验室照**：单叶、纯灰背景、打光均匀。
用户拿手机拍的是**整株、复杂背景、光照不均**。PlantVillage 官方测试集上的高分
（预期 ~0.99）只能说明「模型学会了区分这张数据集里的症状」，**不能**说明手机上可用。
所以这里额外做两件事：

  A. 域内基线：PlantVillage 官方 color_test —— 证明模型本身没问题
  B. 跨域行为：拿手上的**真实栽培照**（本项目 30 个品种的室内采集图，iNat
     captive/cultivated，多为健康的整株观叶植物）跑一遍，看它有多大比例把
     **健康植株误报成病害**，以及误报时的置信度有多高。
     —— 这批图没有症状标注，所以这不是「准确率」，而是「误报倾向」的量化：
        对一株健康的绿萝说「叶斑病 90%」正是用户最不能接受的失败模式。
     因此本脚本对 B 的结论一律标注为「参考性观察」，不冒充指标。

样本量刻意小（默认每类 8 张）——这是行为观察，不是跑基准。
"""

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch

AI = Path("C:/Plant/plant-ai")
sys.path.insert(0, str(AI / "ml"))
sys.path.insert(0, str(AI / "service"))

from dataset import get_val_transforms          # noqa: E402
from symptom_dataset import load_classes, load_meta  # noqa: E402
from train import create_model                  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

USER_PHOTOS = [
    "C:/Plant/upload/recognize/1790591866530.jpg",
    "C:/Plant/upload/recognize/1790592115186.jpg",
    "C:/Plant/upload/recognize/1790592978859.jpg",
    "C:/Plant/upload/recognize/1790645998546.jpg",
    "C:/Plant/upload/recognize/1790646025896.jpg",
]


def build(model_path, classes):
    m = create_model(len(classes), pretrained=False)
    m.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=True))
    m.eval()
    return m


@torch.no_grad()
def predict(model, tf, paths, batch=32):
    """返回 [(top_symptom, confidence, all_probs)]。"""
    from PIL import Image
    out = []
    for i in range(0, len(paths), batch):
        chunk = paths[i:i + batch]
        arrs = []
        for p in chunk:
            img = np.array(Image.open(p).convert("RGB"))
            arrs.append(tf(image=img)["image"])
        x = torch.stack(arrs)
        probs = torch.softmax(model(x), dim=1).numpy()
        for row in probs:
            j = int(row.argmax())
            out.append((j, float(row[j]), row))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(AI / "output_symptom" / "best_model.pth"))
    ap.add_argument("--per-class", type=int, default=8, help="跨域观察每类抽几张")
    ap.add_argument("--out", default="C:/Plant/tests/results/symptom_crossdomain.json")
    args = ap.parse_args()

    meta = load_meta()
    classes = load_classes()
    labels = meta["labels"]
    healthy_idx = classes.index("healthy")

    model = build(args.model, classes)
    tf = get_val_transforms(224)

    # ---------- A. 域内基线 ----------
    print("=" * 78)
    print("A. 域内基线：PlantVillage 官方 color_test")
    print("=" * 78)
    rows = []
    with open(AI / "data" / "symptoms_index.csv", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("path,"):
                continue
            p, sym, split = line.rsplit(",", 2)
            if split == "test":
                rows.append((p.strip('"'), sym))
    test_paths = [p for p, _ in rows]
    test_y = [classes.index(s) for _, s in rows]

    preds = predict(model, tf, test_paths)
    conf = np.zeros((len(classes), len(classes)), dtype=np.int64)
    for (pred_idx, _, _), t in zip(preds, test_y):
        conf[t, pred_idx] += 1
    acc = float(np.trace(conf) / conf.sum())
    rec = {classes[c]: (float(conf[c, c] / conf[c].sum()) if conf[c].sum() else float("nan"))
           for c in range(len(classes))}
    valid = [v for v in rec.values() if not np.isnan(v)]
    macro = float(np.mean(valid))
    print(f"样本 {len(test_paths)} 张   准确率 {acc:.4f}   宏召回 {macro:.4f}")
    print(f"{'症状类':18s} {'召回':>8s} {'样本':>7s}")
    for c in classes:
        print(f"{c:18s} {rec[c]:8.4f} {conf[classes.index(c)].sum():7d}")

    # ---------- B. 跨域观察：健康栽培照会不会被误报 ----------
    print("\n" + "=" * 78)
    print("B. 跨域观察：真实栽培照（iNat captive/cultivated，多为健康整株）")
    print("=" * 78)
    print("说明：这批图**没有症状标注**，下面的数字是「误报倾向」而非准确率。")
    print("      关注点：健康植株被判成病害的比例，以及误报时的置信度。\n")

    rng = random.Random(0)
    indoor = AI / "data" / "plants_indoor"
    samples = []
    for d in sorted(p for p in indoor.iterdir() if p.is_dir()):
        fs = sorted([x for x in d.iterdir() if x.suffix.lower() in (".jpg", ".jpeg", ".png")])
        rng.shuffle(fs)
        for x in fs[: args.per_class]:
            samples.append((d.name, str(x)))
    print(f"抽样 {len(samples)} 张，覆盖 {len({s[0] for s in samples})} 个品种\n")

    preds2 = predict(model, tf, [p for _, p in samples])
    dist = Counter()
    high_conf_disease = []   # 置信度 >= 0.8 的非健康判定
    per_species = {}
    for (sp, path), (j, c, row) in zip(samples, preds2):
        pred = classes[j]
        dist[pred] += 1
        per_species.setdefault(sp, Counter())[pred] += 1
        if pred != "healthy" and c >= 0.8:
            high_conf_disease.append((sp, path, pred, c))

    print(f"{'预测症状':18s} {'张数':>6s} {'占比':>8s}")
    for name, n in dist.most_common():
        print(f"{name:18s} {n:>6d} {n / len(samples):8.1%}")

    healthy_rate = dist["healthy"] / len(samples)
    print(f"\n判为「健康」的比例: {healthy_rate:.1%}")
    print(f"置信度 >=0.8 的病害误报: {len(high_conf_disease)} 张 "
          f"（占 {len(high_conf_disease) / len(samples):.1%}）")
    if high_conf_disease:
        print("\n  高置信误报明细（这些是最该警惕的——模型很确信地说了错话）:")
        for sp, path, pred, c in high_conf_disease[:10]:
            print(f"    {sp:8s} → {pred:16s} {c:.2f}   {Path(path).name}")

    # ---------- C. 用户实拍 ----------
    print("\n" + "=" * 78)
    print("C. 用户实拍照片（无标注，仅供人工判读）")
    print("=" * 78)
    exist = [p for p in USER_PHOTOS if Path(p).is_file()]
    if exist:
        for p, (j, c, row) in zip(exist, predict(model, tf, exist)):
            top2 = np.argsort(row)[::-1][:2]
            extra = "  ".join(f"{classes[k]}={row[k]:.2f}" for k in top2[1:])
            print(f"  {classes[j]:16s} {c:.2f}   ({extra})   {Path(p).name}")
    else:
        print("  （未找到用户实拍照片，跳过）")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({
        "indomain": {"n": len(test_paths), "acc": acc, "macro_recall": macro, "per_class_recall": rec},
        "crossdomain_observation": {
            "note": "无症状标注，仅为误报倾向观察，不是准确率",
            "n": len(samples),
            "pred_distribution": dict(dist),
            "healthy_rate": healthy_rate,
            "high_conf_false_positives": len(high_conf_disease),
            "high_conf_details": [{"species": a, "path": b, "pred": c_, "conf": d}
                                  for a, b, c_, d in high_conf_disease],
            "per_species": {k: dict(v) for k, v in per_species.items()},
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果写入 {args.out}")


if __name__ == "__main__":
    main()
