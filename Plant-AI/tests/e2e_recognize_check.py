"""端到端识别链路检查：把真正未参与训练的室内测试集图片打到 FastAPI /recognize，
核对返回的 species / knowledgeId 是否正确。

为什么要复现切分而不是随便抽图：
train30.py 的室内测试集是 stratified_split(indoor, (0.70,0.15,0.15), seed=42) 的
第三段。随机抽目录里的图，很可能抽到训练集里的，那样测出来的准确率是虚高的
「记忆分」，不能说明问题。这里复现同一套切分，只取 test 段。

只做链路与映射校验，sample-per-class 故意取小（默认 5），不为跑指标。
"""

import argparse
import json
import shutil
import sys
import urllib.request
from pathlib import Path

AI = Path("C:/Plant/plant-ai")
sys.path.insert(0, str(AI / "ml"))

from dataset import PlantDataset, get_val_transforms  # noqa: E402
from train30 import stratified_split  # noqa: E402

SEED = 42
API = "http://127.0.0.1:5000/recognize"


def post(path: str) -> dict:
    body = json.dumps({"image_path": path, "top_k": 3}).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=5, help="每类取多少张测试图")
    ap.add_argument("--out", default="C:/Plant/tests/results/e2e_recognize.json")
    args = ap.parse_args()

    labels = json.loads((AI / "output" / "labels.json").read_text(encoding="utf-8"))
    kid_by_name = {l["name"]: l["knowledge_id"] for l in labels}

    ds = PlantDataset(str(AI / "data" / "plants_indoor"), transform=get_val_transforms(224))
    _, _, test_idx = stratified_split(ds, (0.70, 0.15, 0.15), SEED)
    print(f"复现室内测试集: {len(test_idx)} 张")

    up = Path("C:/Plant/upload/recognize")
    up.mkdir(parents=True, exist_ok=True)

    by_class: dict[str, list[int]] = {}
    for i in test_idx:
        _, y = ds.samples[i]
        by_class.setdefault(ds.classes[y], []).append(i)

    hit = total = 0
    mismatches, fails = [], []
    per_class = {}
    for name in sorted(by_class):
        picks = by_class[name][: args.per_class]
        c = t = 0
        for i in picks:
            src = Path(ds.samples[i][0])
            dst = up / f"e2e_{src.name}"
            shutil.copyfile(src, dst)
            try:
                r = post(str(dst))
            except Exception as e:  # noqa: BLE001
                fails.append({"file": src.name, "true": name, "error": str(e)[:120]})
                continue
            if r.get("is_mock"):
                fails.append({"file": src.name, "true": name, "error": "服务返回 is_mock=true"})
                continue
            cands = r.get("candidates") or []
            top = cands[0] if cands else {}
            t += 1
            ok = top.get("knowledgeId") == kid_by_name.get(name)
            c += int(ok)
            if not ok:
                mismatches.append({
                    "file": src.name, "true": name, "true_kid": kid_by_name.get(name),
                    "pred": top.get("species"), "pred_kid": top.get("knowledgeId"),
                    "conf": top.get("confidence"),
                })
        per_class[name] = {"n": t, "correct": c, "acc": round(c / t, 4) if t else None}
        hit += c
        total += t
        print(f"  {name:8s} {c}/{t}  {'OK' if c == t else ''}")

    acc = hit / total if total else 0.0
    print(f"\n端到端(仅链路校验，样本小): {hit}/{total} = {acc:.4f}")
    if mismatches:
        print(f"\n误判 {len(mismatches)} 条:")
        for m in mismatches:
            print(f"  {m['true']} -> {m['pred']} (conf {m['conf']}, 图 {m['file']})")
    if fails:
        print(f"\n失败 {len(fails)} 条:")
        for f in fails[:10]:
            print(f"  {f['true']} {f['file']}: {f['error']}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({
        "note": "复现 seed=42 切分的室内 test 段；每类抽样少，仅验证链路与 knowledgeId 映射",
        "per_class": per_class,
        "total": total, "correct": hit, "acc": acc,
        "mismatches": mismatches, "failures": fails,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果写入 {args.out}")


if __name__ == "__main__":
    main()
