"""用微调前后的模型，对比用户实拍照片的识别结果 —— 这是最终验收。

聚合指标（室内测试集 0.8591）只说明整体水平，
用户真正关心的是「我自己拍的那几张能不能认对」。
本脚本把同一个推理流程作用在这几张实拍图上，给出前后对比。
"""

import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path("C:/Plant/plant-ai")
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "service"))

from dataset import get_val_transforms   # noqa: E402
from train import create_model          # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 用户实拍（recognize_history 里的真实记录，置信度是当时线上模型的输出）
PHOTOS = [
    ("C:/Plant/upload/recognize/1790591866530.jpg", 0.9036, "09-28"),
    ("C:/Plant/upload/recognize/1790592115186.jpg", 0.9140, "09-28"),
    ("C:/Plant/upload/recognize/1790592978859.jpg", 0.8265, "09-28"),
    ("C:/Plant/upload/recognize/1790645998546.jpg", 0.4897, "09-29 ←低置信度"),
    ("C:/Plant/upload/recognize/1790646025896.jpg", 0.4580, "09-29 ←低置信度"),
]


def load_model(path, num_classes=20):
    m = create_model(num_classes, pretrained=False)
    m.load_state_dict(torch.load(path, map_location="cpu"))
    m.eval()
    return m


def predict(model, tf, path, k=3):
    img = np.array(Image.open(path).convert("RGB"))
    x = tf(image=img)["image"].unsqueeze(0).float()
    with torch.no_grad():
        p = torch.softmax(model(x), dim=1)[0].numpy()
    order = np.argsort(p)[::-1][:k]
    return [(names[i], float(p[i])) for i in order]


names = [x["name"] for x in json.loads((ROOT / "output" / "labels.json").read_text(encoding="utf-8"))]
tf = get_val_transforms(224)

before = load_model(ROOT / "output" / "best_model.pth")
after_path = ROOT / "output_indoor" / "best_model.pth"
after = load_model(after_path)
print("=" * 96)
print("用户实拍照片：微调前 vs 微调后")
print("=" * 96)
print(f"{'照片':16s} {'日期':16s} {'微调前 Top-1':>22s}  {'微调后 Top-1':>22s}")
print("-" * 96)

rows = []
for path, old_conf, when in PHOTOS:
    b = predict(before, tf, path)[0]
    a = predict(after, tf, path)[0]
    print(f"{Path(path).name[:14]:16s} {when:16s} {b[0] + ' ' + format(b[1], '.4f'):>22s}  "
          f"{a[0] + ' ' + format(a[1], '.4f'):>22s}")
    rows.append({"photo": Path(path).name, "before": b[0], "before_conf": b[1],
                 "after": a[0], "after_conf": a[1], "recorded_conf": old_conf})

print()
print("两张低置信度照片的 Top-3 明细：")
for path, old_conf, when in PHOTOS[3:]:
    b = predict(before, tf, path)
    a = predict(after, tf, path)
    print(f"\n  {Path(path).name}")
    print(f"    微调前: " + " | ".join(f"{n} {p:.3f}" for n, p in b))
    print(f"    微调后: " + " | ".join(f"{n} {p:.3f}" for n, p in a))

out = Path("C:/Plant/tests/results/user_photos_compare.json")
out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n结果已存: {out}")
