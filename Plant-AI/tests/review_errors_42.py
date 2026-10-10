"""把误判样本导出到目录，供人工核对「是模型错了，还是数据集标签错了」。

背景：室内测试集上有若干**高置信错误**（如 吊兰→富贵竹 0.94）。但 iNat 是社区标注，
有噪声（文档第七节见过「万年青」图里两株不同植物）。若这些"错误"其实是**标签错了**，
那模型是对的、真实识别率被低估，重训就是白费功夫。
所以先导出原图人工看，再决定要不要重训。
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
from recognizer import (                             # noqa: E402
    SPECIES_IMAGE_SIZE, TTA_SCALES, build_val_transform, build_val_transform_from_r,
)

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
    ap.add_argument("--min-conf", type=float, default=0.60,
                    help="只导出预测置信度 >= 此值的错误（低置信的闭集边界错误不关心）")
    ap.add_argument("--out", default="C:/Plant/_err_review")
    args = ap.parse_args()

    outdir = Path(args.out)
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)

    labels = json.loads((ROOT / "output" / "labels.json").read_text(encoding="utf-8"))

    import onnxruntime as ort
    sess = ort.InferenceSession(str(ROOT / "output" / "plant_model.onnx"),
                                providers=["CPUExecutionProvider"])
    r = int(SPECIES_IMAGE_SIZE * 1.14)
    tfs = [build_val_transform_from_r(int(r * s), SPECIES_IMAGE_SIZE) for s in TTA_SCALES]

    ds = PlantDataset(str(ROOT / "data" / "plants_indoor"))
    _, _, test_i = stratified_split(ds, (0.70, 0.15, 0.15), SEED)
    print(f"室内测试集 {len(test_i)} 张，导出置信度>={args.min_conf} 的误判")

    rows = []
    for i in test_i:
        p, lab = ds.samples[i]
        img = np.array(Image.open(p).convert("RGB"))
        xb = np.concatenate([tf(image=img)["image"].unsqueeze(0).numpy() for tf in tfs],
                            axis=0).astype(np.float32)
        logits = sess.run(None, {"input": xb})[0]
        probs = np.mean([softmax(logits[k]) for k in range(len(tfs))], axis=0)
        pred = int(probs.argmax())
        if pred == lab:
            continue
        conf = float(probs[pred])
        if conf < args.min_conf:
            continue
        true_name, pred_name = labels[lab]["name"], labels[pred]["name"]
        fn = f"{true_name}__被判为__{pred_name}__{conf:.2f}__i{i}.jpg"
        shutil.copy2(p, outdir / fn)
        rows.append({"i": i, "true": true_name, "pred": pred_name,
                     "conf": round(conf, 3), "src": str(p), "file": fn})

    rows.sort(key=lambda x: -x["conf"])
    (outdir / "manifest.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n共导出 {len(rows)} 张 -> {outdir}")
    agg = defaultdict(int)
    for x in rows:
        agg[(x["true"], x["pred"])] += 1
    print("\n按混淆对统计：")
    for (t, p), c in sorted(agg.items(), key=lambda kv: -kv[1]):
        print(f"  {t} → {p}  ×{c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
