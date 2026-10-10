"""模型评估脚本 — 计算 Top-1/5 准确率、混淆矩阵、分类报告

使用方法:
    python evaluate.py --model_path ./output/best_model.pth --data_dir ./data/plants
"""

import argparse
import json
import os

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from sklearn.metrics import classification_report, confusion_matrix

from config import EvalConfig
from dataset import PlantDataset, get_val_transforms
from train import create_model


def evaluate():
    # 默认值取自 EvalConfig（按脚本位置解析），不要硬编码相对路径
    defaults = EvalConfig()
    parser = argparse.ArgumentParser(description="植物识别模型评估")
    parser.add_argument("--model_path", type=str, default=defaults.model_path)
    parser.add_argument("--data_dir", type=str, default=defaults.data_dir)
    parser.add_argument("--batch_size", type=int, default=defaults.batch_size)
    parser.add_argument("--output_dir", type=str, default=defaults.output_dir)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"使用设备: {device}")

    # 数据集
    dataset = PlantDataset(args.data_dir, transform=get_val_transforms(224))
    num_classes = len(dataset.classes)
    print(f"数据集: {len(dataset)} 张图片, {num_classes} 个类别")

    dataloader = DataLoader(
        dataset, batch_size=args.batch_size,
        shuffle=False, num_workers=4, pin_memory=True,
    )

    # 加载模型
    model = create_model(num_classes, pretrained=False)
    model.load_state_dict(torch.load(args.model_path, map_location=device))
    model = model.to(device)
    model.eval()

    # 收集预测结果
    all_preds = []
    all_labels = []
    all_probs = []

    with torch.no_grad():
        for images, labels in dataloader:
            images = images.to(device)
            outputs = model(images)
            probs = torch.softmax(outputs, dim=1)

            _, predicted = outputs.max(1)
            all_preds.extend(predicted.cpu().numpy())
            all_labels.extend(labels.numpy())
            all_probs.extend(probs.cpu().numpy())

    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)
    all_probs = np.array(all_probs)

    # Top-1 准确率
    top1_correct = (all_preds == all_labels).sum()
    top1_acc = top1_correct / len(all_labels)
    print(f"\nTop-1 准确率: {top1_acc:.4f} ({top1_correct}/{len(all_labels)})")

    # Top-5 准确率
    top5_preds = np.argsort(all_probs, axis=1)[:, -5:]
    top5_correct = sum(
        all_labels[i] in top5_preds[i] for i in range(len(all_labels))
    )
    top5_acc = top5_correct / len(all_labels)
    print(f"Top-5 准确率: {top5_acc:.4f} ({top5_correct}/{len(all_labels)})")

    # 分类报告
    print("\n分类报告:")
    report = classification_report(
        all_labels, all_preds,
        target_names=dataset.classes,
        digits=4,
    )
    print(report)

    # 保存评估结果
    os.makedirs(args.output_dir, exist_ok=True)

    result = {
        "top1_accuracy": float(top1_acc),
        "top5_accuracy": float(top5_acc),
        "num_classes": num_classes,
        "num_samples": len(all_labels),
        "classification_report": report,
    }

    with open(os.path.join(args.output_dir, "eval_result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 混淆矩阵
    cm = confusion_matrix(all_labels, all_preds)
    np.savetxt(
        os.path.join(args.output_dir, "confusion_matrix.csv"),
        cm, delimiter=",", fmt="%d",
    )

    print(f"\n评估结果已保存到: {args.output_dir}/")


if __name__ == "__main__":
    evaluate()
