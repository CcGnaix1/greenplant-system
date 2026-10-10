"""ONNX 导出脚本 — 把 PyTorch 模型转成推理服务用的 ONNX。

使用方法:
    python export_onnx.py --model_path output/best_model.pth

    # 类别数默认从 labels.json 自动推断（train.py 会生成），无需手动传。
    # 若 labels.json 不在默认位置，可显式指定：
    python export_onnx.py --model_path output/best_model.pth --num_classes 6

可选 INT8 量化:
    python export_onnx.py --model_path output/best_model.pth --quantize
"""

import argparse
import json
import os
import sys

import numpy as np
import torch

from config import TrainConfig
from train import create_model


def export_onnx(model, output_path: str, image_size: int = 224, dynamic_batch: bool = True):
    """导出 ONNX 模型。

    image_size 必须与训练时一致：320 训练的模型喂 224 输入会掉约 5 个点
    （实测 0.9170 → 0.8591），因为模型学到的是高分辨率下才有的特征。
    导出的空间维度是**静态**的，所以推理侧喂错尺寸会直接报错而不是静默降精度。
    """
    model.eval()
    dummy = torch.randn(1, 3, image_size, image_size)

    dynamic_axes = None
    if dynamic_batch:
        dynamic_axes = {"input": {0: "batch"}, "output": {0: "batch"}}

    torch.onnx.export(
        model,
        dummy,
        output_path,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes=dynamic_axes,
        opset_version=13,
        do_constant_folding=True,
    )

    file_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"ONNX 模型已导出: {output_path} ({file_size:.1f} MB)")


def quantize_onnx(input_path: str, output_path: str):
    """INT8 量化 ONNX 模型"""
    from onnxruntime.quantization import QuantType, quantize_dynamic

    quantize_dynamic(
        input_path,
        output_path,
        weight_type=QuantType.QUInt8,
    )

    file_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"量化模型已保存: {output_path} ({file_size:.1f} MB)")


def resolve_num_classes(explicit, labels_path: str, fallback: int) -> int:
    """推断类别数。

    刻意不设「默认 20」——那是上一版脚本的陷阱：类别数不匹配时
    load_state_dict 会直接报 size mismatch，报错信息还不容易看出原因。
    这里优先从 labels.json（train.py 生成）读真实类别数。
    """
    if explicit is not None:
        return explicit
    if os.path.isfile(labels_path):
        with open(labels_path, "r", encoding="utf-8") as f:
            n = len(json.load(f))
        print(f"从 {labels_path} 推断类别数: {n}")
        return n
    print(f"未找到 {labels_path}，回退到默认类别数 {fallback}")
    return fallback


def main():
    defaults = TrainConfig()
    parser = argparse.ArgumentParser(description="导出 ONNX 模型")
    parser.add_argument("--model_path", type=str, required=True, help="PyTorch 模型路径(best_model.pth)")
    parser.add_argument("--num_classes", type=int, default=None,
                        help="类别数；默认从 labels.json 自动推断")
    parser.add_argument("--labels_path", type=str, default=defaults.labels_path,
                        help="labels.json 路径，用于自动推断类别数")
    parser.add_argument("--output", type=str, default=defaults.onnx_path,
                        help="ONNX 输出路径")
    parser.add_argument("--image-size", type=int, default=224,
                        help="训练时用的输入分辨率，必须与训练一致（默认 224）")
    parser.add_argument("--arch", default="mobilenet_v3_large",
                        choices=["mobilenet_v3_large", "efficientnet_b0"],
                        help="骨干网，必须与训练时一致，否则 load_state_dict 报 size mismatch")
    parser.add_argument("--quantize", action="store_true", help="是否进行 INT8 量化")
    args = parser.parse_args()

    num_classes = resolve_num_classes(args.num_classes, args.labels_path, defaults.num_classes)

    model = create_model(num_classes, pretrained=False, arch=args.arch)
    model.load_state_dict(torch.load(args.model_path, map_location="cpu", weights_only=True))

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    export_onnx(model, args.output, image_size=args.image_size)

    if args.quantize:
        quant_path = args.output.replace(".onnx", "_quant.onnx")
        quantize_onnx(args.output, quant_path)

    # 验证导出的模型能真的推理；失败必须让脚本非零退出，否则会误以为导出成功
    import onnxruntime as ort
    session = ort.InferenceSession(args.output, providers=["CPUExecutionProvider"])
    dummy = np.random.randn(1, 3, args.image_size, args.image_size).astype(np.float32)
    outputs = session.run(None, {"input": dummy})
    print(f"ONNX 验证通过，输入 {args.image_size}x{args.image_size}，"
          f"输出形状: {outputs[0].shape}（应为 (1, {num_classes})）")
    if outputs[0].shape[-1] != num_classes:
        print("警告: 输出维度与类别数不一致，请检查 --num_classes")
        sys.exit(1)

    # 空间维度是静态的，这里回读一次确认导出时用的确实是用户要的分辨率。
    # 推理侧若按别的尺寸喂会直接报错，所以导出分辨率必须与推理配置一致。
    in_shape = session.get_inputs()[0].shape
    if in_shape[2] != args.image_size or in_shape[3] != args.image_size:
        print(f"警告: ONNX 输入空间维度 {in_shape[2:]} 与 --image-size {args.image_size} 不符")
        sys.exit(1)


if __name__ == "__main__":
    main()
