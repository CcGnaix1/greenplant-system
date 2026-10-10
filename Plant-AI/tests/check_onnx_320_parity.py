"""上线前校验：ONNX(320) 的精度是否与 PyTorch 一致，且**用生产预处理路径**。

为什么必须单独校验这个
----------------------
两条链路各自持有预处理实现：
    ml/dataset.py:get_val_transforms      —— 训练/评估用
    service/recognizer.py:build_val_transform —— 推理用（刻意复制了一份）
两者一旦漂移（resize/crop 偏移差 1 像素这类），精度会静默下降，指标上完全看不出来。
所以这里不调 dataset.py，而是调 **recognizer 里那份**，并同时比对 ONNX 与 PyTorch
的输出，确认导出没有引入偏差。

判据：ONNX 在室内测试集上的准确率应与 result.json 的 indoor_test 一致。
默认值对应 30 类 MobileNetV3@320（indoor_test=0.9170）；校验 42 类 EfficientNet-B0 时
用 --arch efficientnet_b0 --pth/--onnx 指向 output_v42_320 --expected 0.9231。
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Subset

ROOT = Path("C:/Plant/plant-ai")
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "service"))

from dataset import PlantDataset                     # noqa: E402
from train import create_model                       # noqa: E402
from train30 import stratified_split                 # noqa: E402
# 生产代码路径 —— 不是 dataset.py 里那份
from recognizer import SPECIES_IMAGE_SIZE, build_val_transform  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SEED = 42


def main():
    ap = argparse.ArgumentParser(description="ONNX ↔ PyTorch 一致性 + 精度校验")
    ap.add_argument("--onnx", default=str(ROOT / "output_v30_320" / "plant_model.onnx"))
    ap.add_argument("--pth", default=str(ROOT / "output_v30_320" / "best_model.pth"))
    ap.add_argument("--arch", default="mobilenet_v3_large",
                    choices=["mobilenet_v3_large", "efficientnet_b0"])
    ap.add_argument("--expected", type=float, default=0.9170,
                    help="result.json 里记录的 indoor_test，用于核对")
    args = ap.parse_args()

    onnx_path = Path(args.onnx)
    pth_path = Path(args.pth)
    expected = args.expected

    print("=" * 78)
    print("ONNX(320) 上线校验")
    print("=" * 78)
    print(f"recognizer.SPECIES_IMAGE_SIZE = {SPECIES_IMAGE_SIZE}")
    print(f"onnx={onnx_path.name}  arch={args.arch}  expected={expected}")

    ds = PlantDataset(str(ROOT / "data" / "plants_indoor"))
    classes = ds.classes
    _, _, test_i = stratified_split(ds, (0.70, 0.15, 0.15), SEED)
    print(f"室内测试集 {len(test_i)} 张，类别 {len(classes)}")

    tf = build_val_transform(SPECIES_IMAGE_SIZE)

    import onnxruntime as ort
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    in_shape = sess.get_inputs()[0].shape
    print(f"ONNX 输入形状 {in_shape}，输出 {sess.get_outputs()[0].shape}")
    onnx_res = sess.get_inputs()[0]
    assert in_shape[2] == SPECIES_IMAGE_SIZE, "ONNX 输入分辨率与推理配置不一致！"

    model = create_model(len(classes), pretrained=False, arch=args.arch)
    model.load_state_dict(torch.load(pth_path, map_location="cpu", weights_only=True))
    model.eval()

    ok_onnx = ok_torch = same = 0
    max_diff = 0.0
    n = 0
    for i in test_i:
        p, lab = ds.samples[i]
        img = np.array(Image.open(p).convert("RGB"))
        x = tf(image=img)["image"].unsqueeze(0).numpy().astype(np.float32)

        lo_o = sess.run(None, {"input": x})[0][0]
        with torch.no_grad():
            lo_t = model(torch.from_numpy(x)).numpy()[0]

        po, pt = int(lo_o.argmax()), int(lo_t.argmax())
        ok_onnx += int(po == lab)
        ok_torch += int(pt == lab)
        same += int(po == pt)
        max_diff = max(max_diff, float(np.abs(lo_o - lo_t).max()))
        n += 1

    acc_o, acc_t = ok_onnx / n, ok_torch / n
    print(f"\nONNX(320) 准确率   {acc_o:.4f}  ({ok_onnx}/{n})")
    print(f"PyTorch(320) 准确率 {acc_t:.4f}  ({ok_torch}/{n})")
    print(f"两者 argmax 一致率  {same / n:.4f}   最大 logit 差 {max_diff:.2e}")
    print(f"训练时记录值        {expected:.4f}")

    ok = True
    if abs(acc_o - expected) > 0.01:
        print(f"\n[警告] ONNX 准确率与训练记录差 {abs(acc_o - expected):.4f}（>1 个点）")
        ok = False
    if acc_o < 0.90:
        print(f"\n[失败] ONNX 准确率 {acc_o:.4f} 低于 0.90，不该上线")
        ok = False
    if same != n:
        print(f"\n[警告] {n - same} 张 ONNX 与 PyTorch 判定不同")
    if abs(acc_o - acc_t) < 1e-9 and same == n:
        print("\nONNX 与 PyTorch 完全一致 —— 导出无偏差，生产预处理路径正确")
    print("\n" + ("通过：可以上线" if ok else "未通过：不要上线"))

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
