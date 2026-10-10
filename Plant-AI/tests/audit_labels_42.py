"""训练集标签审计 —— 找「模型高置信度反对其给定标签」的图，作为疑似错标的复核队列。

原理（confident learning 的简化版）
----------------------------------
模型已拟合训练集，若某张**训练图**模型仍以高置信度判成**别的类**，要么
  (a) 这张图的标签标错了（iNat 社区标注噪声，已亲眼见到若干），或
  (b) 图本身歧义/拍糊。
无论哪种，都值得人工复核 —— 错标数据会让模型学到错误的关联，是精度的隐形天花板。

⚠ 局限：模型见过这些标签，可能"背下"了错标，所以本审计会**漏掉**一部分错标
   （真正的 cleanlab 要交叉验证）。但高置信反对的图，误标概率显著高于均值。

用法：python tests/audit_labels_42.py --split train --min-conf 0.70
"""

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path("C:/Plant/plant-ai")
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "service"))

from dataset import PlantDataset                     # noqa: E402
from train30 import stratified_split                 # noqa: E402
from recognizer import SPECIES_IMAGE_SIZE, build_val_transform   # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SEED = 42


def softmax(x):
    e = np.exp(x - x.max())
    return e / e.sum()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train", choices=["train", "val", "test"])
    ap.add_argument("--min-conf", type=float, default=0.70)
    ap.add_argument("--out", default="C:/Plant/_label_audit")
    ap.add_argument("--top", type=int, default=120, help="导出前 N 张供复核")
    args = ap.parse_args()

    labels = json.loads((ROOT / "output" / "labels.json").read_text(encoding="utf-8"))

    import onnxruntime as ort
    sess = ort.InferenceSession(str(ROOT / "output" / "plant_model.onnx"),
                                providers=["CPUExecutionProvider"])
    tf = build_val_transform(SPECIES_IMAGE_SIZE)

    ds = PlantDataset(str(ROOT / "data" / "plants_indoor"))
    tr, va, te = stratified_split(ds, (0.70, 0.15, 0.15), SEED)
    idx = {"train": tr, "val": va, "test": te}[args.split]
    print(f"审计室内 {args.split} 段，{len(idx)} 张，阈值 conf>={args.min_conf}")

    suspects = []
    per_class = defaultdict(int)
    for n, i in enumerate(idx):
        p, lab = ds.samples[i]
        img = np.array(Image.open(p).convert("RGB"))
        x = tf(image=img)["image"].unsqueeze(0).numpy().astype(np.float32)
        probs = softmax(sess.run(None, {"input": x})[0][0])
        pred = int(probs.argmax())
        conf = float(probs[pred])
        if pred != lab and conf >= args.min_conf:
            tn, pn = labels[lab]["name"], labels[pred]["name"]
            suspects.append({"true": tn, "pred": pn, "conf": round(conf, 3),
                             "src": str(p), "i": i})
            per_class[tn] += 1
        if (n + 1) % 500 == 0:
            print(f"  ...已处理 {n + 1}/{len(idx)}，累计疑似 {len(suspects)}")

    suspects.sort(key=lambda x: -x["conf"])
    outdir = Path(args.out)
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    for k, s in enumerate(suspects[:args.top]):
        fn = f"{k:03d}__{s['true']}__疑为__{s['pred']}__{s['conf']:.2f}.jpg"
        shutil.copy2(s["src"], outdir / fn)
    (outdir / "manifest.json").write_text(
        json.dumps(suspects, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n疑似错标 {len(suspects)} 张 / {len(idx)} "
          f"= {len(suspects) / max(1, len(idx)):.1%}")
    print(f"已导出前 {min(args.top, len(suspects))} 张 -> {outdir}")
    print("\n按给定标签（疑似错标的类）排序：")
    for c, n in sorted(per_class.items(), key=lambda kv: -kv[1])[:15]:
        print(f"  {c:8s} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
