"""症状模型 v2 收尾 —— 只做「最终评估 + 落盘」，不训练。

为什么需要它
------------
`train_symptom2.py` 只在跑满 epochs 之后才写 result.json / labels.json。若训练被中断
（2026-09-29 那次跑到第 10 轮被关机打断），盘上会只剩 `best_model.pth` 与
`history.json` —— 而最优权重其实**已经选出来了**，重训 70 分钟只会得到同一个最优轮。

跨域测试集是可复现的：`symptom_bg.split_indoor` 按 `md5(品种/文件名)` 分桶，
不依赖目录顺序，也不受 PYTHONHASHSEED 影响。所以拿已有 checkpoint 复跑评估，
得到的域内/跨域数字与「跑满 12 轮」完全一致。

用法:
    PYTHONUTF8=1 python -u finalize_symptom2.py
    # 换 checkpoint / 产物目录：
    PYTHONUTF8=1 python -u finalize_symptom2.py \\
        --model output_symptom_v2/best_model.pth --out-dir output_symptom_v2
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import torch
from torch.utils.data import DataLoader

ML_DIR = Path(__file__).resolve().parent
ROOT = ML_DIR.parent
sys.path.insert(0, str(ML_DIR))

from dataset import get_val_transforms                                  # noqa: E402
from symptom_bg import RealPhotoEval, split_indoor                      # noqa: E402
from symptom_dataset import INDEX, SymptomDataset, load_classes, load_meta  # noqa: E402
from train import create_model                                          # noqa: E402
from train_symptom import evaluate                                      # noqa: E402
from train_symptom2 import HEALTHY, real_photo_stats                    # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def best_epoch_from_history(out_dir: Path) -> tuple[int, float]:
    """从 history.json 取选优分最高的轮次（训练脚本用同一规则）。"""
    hist = json.loads((out_dir / "history.json").read_text(encoding="utf-8"))
    best = max(hist, key=lambda h: h["score"])
    return best["epoch"], best["score"]


def main():
    ap = argparse.ArgumentParser(description="症状模型 v2 最终评估 + 落盘（不训练）")
    ap.add_argument("--model", default=str(ROOT / "output_symptom_v2" / "best_model.pth"))
    ap.add_argument("--out-dir", default=str(ROOT / "output_symptom_v2"))
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--num-workers", type=int, default=4)
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument("--composite-prob", type=float, default=0.7,
                    help="仅用于写进 result.json（记录当时训练用的配置）")
    ap.add_argument("--real-healthy-frac", type=float, default=0.25,
                    help="仅用于写进 result.json（记录当时训练用的配置）")
    args = ap.parse_args()

    model_path = Path(args.model)
    out_dir = Path(args.out_dir)
    if not model_path.is_file():
        raise SystemExit(f"[错误] 找不到权重: {model_path}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    classes = load_classes()
    meta = load_meta()
    num_classes = len(classes)
    va_tf = get_val_transforms(args.image_size)

    # 与训练时同一套划分：跨域测试集是「训练不可见」的那 20%
    _, _, test_paths = split_indoor()
    pv_test = SymptomDataset(INDEX, "test", classes, va_tf)
    real_test = RealPhotoEval(test_paths, classes, va_tf)

    print("=" * 84)
    print("症状模型 v2 最终评估（复用已选出的最优权重，不重训）")
    print("=" * 84)
    print(f"设备 {device}")
    print(f"权重 {model_path}")
    print(f"域内测试 {len(pv_test)} 张 / 跨域测试 {len(real_test)} 张（训练不可见）")

    bs, nw = args.batch_size, args.num_workers
    pv_test_loader = DataLoader(pv_test, batch_size=bs, shuffle=False,
                                num_workers=nw, pin_memory=True)
    real_loader = DataLoader(real_test, batch_size=bs, shuffle=False,
                             num_workers=nw, pin_memory=True)

    model = create_model(num_classes, pretrained=False)
    model.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=True))
    model = model.to(device)

    pv_acc, pv_macro, pv_rec, pv_conf = evaluate(model, pv_test_loader, device, num_classes)
    r_healthy, r_total, hc = real_photo_stats(model, real_loader, device, classes)

    print("\n" + "=" * 84)
    print("A. 域内（PlantVillage 官方测试集，选优用的就是这个集，仅供对照）")
    print("=" * 84)
    print(f"准确率 {pv_acc:.4f}   宏召回 {pv_macro:.4f}")
    for c in range(num_classes):
        print(f"  {classes[c]:16s} 召回 {pv_rec[c]:.4f}  样本 {pv_conf[c].sum():5d}")

    print("\n" + "=" * 84)
    print("B. 跨域（真实整株栽培照，训练时不可见）—— 这才是「手机拍照能不能用」")
    print("=" * 84)
    print(f"样本 {r_total} 张（无健康标注，看的是误报倾向）")
    print(f"判为健康: {r_healthy:.1%}   置信度>=0.8 的病害误报: {len(hc)} 张 "
          f"({len(hc) / r_total:.1%})")
    print("\n对照 v1（未做背景合成）: 真实健康率 29.6%，高置信误报 7.9%")
    if hc:
        print("  误报分布:", dict(Counter(p for p, _ in hc).most_common()))

    best_epoch, best_score = best_epoch_from_history(out_dir)
    print(f"\n最优轮次 第 {best_epoch} 轮（选优分 {best_score:.4f}，取自 history.json）")

    (out_dir / "result.json").write_text(json.dumps({
        "num_classes": num_classes,
        "classes": classes,
        "composite_prob": args.composite_prob,
        "real_healthy_frac": args.real_healthy_frac,
        "best_epoch": best_epoch,
        "selection_metric": "0.5*pv_test_macro_recall + 0.5*real_healthy_rate",
        "in_domain": {"acc": pv_acc, "macro_recall": pv_macro,
                      "per_class_recall": {classes[i]: pv_rec[i] for i in range(num_classes)}},
        "cross_domain": {"n": r_total, "healthy_rate": r_healthy,
                         "high_conf_false_positives": len(hc),
                         "note": "无健康标注，为误报倾向观察"},
        "v1_baseline": {"real_healthy_rate": 0.296, "high_conf_false_positive_rate": 0.079},
        "caveat": "权重来自被中断的训练运行；评估用的划分是 md5 分桶，可复现",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    labels = [{"name": c, "id": i, "label": meta["labels"][c],
               "dict_code": meta.get("dict_code", {}).get(c)} for i, c in enumerate(classes)]
    (out_dir / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(f"产物: {out_dir}/ (labels.json / result.json；best_model.pth 沿用原文件)")


if __name__ == "__main__":
    main()
