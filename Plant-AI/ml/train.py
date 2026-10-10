"""MobileNetV3-Large 迁移学习训练脚本

使用方法:
    python train.py --data_dir ./data/plants --epochs 50 --batch_size 32
"""

import argparse
import json
import os
import time

import torch
import torch.nn as nn
from torch.optim.lr_scheduler import CosineAnnealingLR, StepLR
from torch.utils.data import DataLoader, random_split
from torchvision.models import (EfficientNet_B0_Weights, MobileNet_V3_Large_Weights,
                                efficientnet_b0, mobilenet_v3_large)

from config import TrainConfig
from dataset import PlantDataset, get_train_transforms, get_val_transforms

# 可选骨干网。两个模型的 `.classifier[-1]` 都是最后一层 Linear，换头代码通用；
# `.features` 都存在，冻结骨干的代码也通用。
# MobileNetV3-Large：约 5.5M 参数 / 0.22 GFLOPs
# EfficientNet-B0 ：约 5.3M 参数 / 0.39 GFLOPs（参数接近但更深、感受野更大，
#                   细粒度分类通常更好，代价是推理略慢）
ARCHS = {
    "mobilenet_v3_large": (mobilenet_v3_large, MobileNet_V3_Large_Weights.DEFAULT),
    "efficientnet_b0": (efficientnet_b0, EfficientNet_B0_Weights.DEFAULT),
}


def create_model(num_classes: int, pretrained: bool = True, arch: str = "mobilenet_v3_large"):
    """按 arch 创建模型并替换分类头。

    arch 默认 mobilenet_v3_large，这样既有的脚本与测试不用改就能跑 ——
    部署产物是 ONNX（自包含），推理侧不关心骨干；只有导出与再训练才对得上。
    """
    if arch not in ARCHS:
        raise SystemExit(f"未知架构 {arch}，可选: {list(ARCHS)}")
    ctor, weights_enum = ARCHS[arch]
    model = ctor(weights=weights_enum if pretrained else None)
    # 替换分类头
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, num_classes)
    return model


def train_one_epoch(model, dataloader, criterion, optimizer, device, epoch):
    model.train()
    total_loss, correct, total = 0, 0, 0

    for batch_idx, (images, labels) in enumerate(dataloader):
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item()
        _, predicted = outputs.max(1)
        correct += predicted.eq(labels).sum().item()
        total += labels.size(0)

        if (batch_idx + 1) % 20 == 0:
            print(f"  Batch {batch_idx + 1}/{len(dataloader)}: Loss={loss.item():.4f}")

    avg_loss = total_loss / len(dataloader)
    accuracy = correct / total
    return avg_loss, accuracy


def validate(model, dataloader, criterion, device):
    model.eval()
    total_loss, correct, total = 0, 0, 0

    with torch.no_grad():
        for images, labels in dataloader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            loss = criterion(outputs, labels)

            total_loss += loss.item()
            _, predicted = outputs.max(1)
            correct += predicted.eq(labels).sum().item()
            total += labels.size(0)

    avg_loss = total_loss / len(dataloader)
    accuracy = correct / total
    return avg_loss, accuracy


def main():
    # argparse 的默认值取自 TrainConfig，而不是硬编码相对路径 ——
    # 否则会把 config.py 里按脚本位置解析出的绝对路径覆盖掉，
    # 换目录/换工作目录运行就会扫到空数据集。
    defaults = TrainConfig()
    parser = argparse.ArgumentParser(description="植物识别模型训练")
    parser.add_argument("--data_dir", type=str, default=defaults.data_dir)
    parser.add_argument("--epochs", type=int, default=defaults.epochs)
    parser.add_argument("--batch_size", type=int, default=defaults.batch_size)
    parser.add_argument("--lr", type=float, default=defaults.learning_rate)
    parser.add_argument("--output_dir", type=str, default=defaults.output_dir)
    parser.add_argument("--resume", type=str, default=None,
                        help="从 checkpoint 续训，例如 output/checkpoint_epoch20.pth")
    args = parser.parse_args()

    config = TrainConfig(
        data_dir=args.data_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        output_dir=args.output_dir,
    )

    os.makedirs(config.output_dir, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"使用设备: {device}")

    # 数据集
    full_dataset = PlantDataset(
        config.data_dir,
        transform=get_train_transforms(config.image_size),
    )
    config.num_classes = len(full_dataset.classes)
    print(f"数据集: {len(full_dataset)} 张图片, {config.num_classes} 个类别")

    if len(full_dataset) == 0:
        raise SystemExit(
            f"数据集为空：{config.data_dir} 下没找到任何图片。\n"
            "请先往每个品种子目录放图（每类建议 100~200 张）再训练。"
        )

    # 立刻写 labels.json：它只依赖目录结构，不依赖训练结果。
    # 原先放在训练全部跑完才写，一旦中途中断就没有标签文件，导出的 ONNX 无法用。
    full_dataset.save_labels(config.labels_path, config.species_ids_path)

    # 划分训练/验证集。固定 generator，保证切分可复现，指标才有可比性。
    train_size = int(len(full_dataset) * config.train_split)
    val_size = len(full_dataset) - train_size
    split_gen = torch.Generator().manual_seed(config.seed)
    train_dataset, val_dataset = random_split(
        full_dataset, [train_size, val_size], generator=split_gen
    )

    # 验证集使用 val transforms
    val_dataset.dataset = PlantDataset(
        config.data_dir,
        transform=get_val_transforms(config.image_size),
    )

    train_loader = DataLoader(
        train_dataset, batch_size=config.batch_size,
        shuffle=True, num_workers=config.num_workers, pin_memory=True,
    )
    val_loader = DataLoader(
        val_dataset, batch_size=config.batch_size,
        shuffle=False, num_workers=config.num_workers, pin_memory=True,
    )

    # 模型
    model = create_model(config.num_classes, config.pretrained).to(device)
    print(f"模型: {config.model_name} ({sum(p.numel() for p in model.parameters()) / 1e6:.1f}M 参数)")

    # 损失函数 + 优化器
    criterion = nn.CrossEntropyLoss(label_smoothing=config.label_smoothing)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    scheduler = CosineAnnealingLR(optimizer, T_max=config.epochs, eta_min=config.min_lr)

    # 训练循环
    best_acc = 0
    history = []
    start_epoch = 0

    # 续训：从 checkpoint 恢复，避免中断后从 epoch 0 重跑
    if args.resume:
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model_state_dict"])
        if "optimizer_state_dict" in ckpt:
            optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        start_epoch = ckpt.get("epoch", 0)
        best_acc = ckpt.get("best_acc", ckpt.get("val_acc", 0)) or 0
        # 学习率调度器也要推进到对应位置，否则 LR 会从头开始衰减
        for _ in range(start_epoch):
            scheduler.step()
        hist_path = os.path.join(config.output_dir, "history.json")
        if os.path.isfile(hist_path):
            with open(hist_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        print(f"[续训] 从 {args.resume} 恢复到第 {start_epoch} 轮，"
              f"历史最佳 Acc={best_acc:.4f}，目标 {config.epochs} 轮")

    for epoch in range(start_epoch, config.epochs):
        start_time = time.time()

        train_loss, train_acc = train_one_epoch(
            model, train_loader, criterion, optimizer, device, epoch
        )
        val_loss, val_acc = validate(model, val_loader, criterion, device)
        scheduler.step()

        elapsed = time.time() - start_time
        lr = optimizer.param_groups[0]["lr"]

        print(f"Epoch {epoch + 1}/{config.epochs} ({elapsed:.1f}s)")
        print(f"  Train: Loss={train_loss:.4f} Acc={train_acc:.4f}")
        print(f"  Val:   Loss={val_loss:.4f} Acc={val_acc:.4f}")
        print(f"  LR={lr:.6f}")

        history.append({
            "epoch": epoch + 1,
            "train_loss": train_loss, "train_acc": train_acc,
            "val_loss": val_loss, "val_acc": val_acc,
            "lr": lr,
        })

        # 保存最佳模型
        if val_acc > best_acc:
            best_acc = val_acc
            torch.save(model.state_dict(), os.path.join(config.output_dir, "best_model.pth"))
            # 不要用 emoji：Windows 控制台默认 GBK，打印 ✅ 会抛 UnicodeEncodeError
            # 直接中断训练，导致 labels.json / history.json 都写不出来
            print(f"  [best] 最佳模型已保存 (Acc={best_acc:.4f})")

        # 定期保存 checkpoint（带 best_acc，续训时才知道历史最佳，不会覆盖掉更好的权重）
        if (epoch + 1) % config.save_every == 0:
            torch.save({
                "epoch": epoch + 1,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_acc": val_acc,
                "best_acc": best_acc,
            }, os.path.join(config.output_dir, f"checkpoint_epoch{epoch + 1}.pth"))

        # 每轮都落盘历史，中途被杀也不会丢进度（原先只在训练全部跑完才写）
        with open(os.path.join(config.output_dir, "history.json"), "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

    print(f"\n训练完成! 最佳验证准确率: {best_acc:.4f}")
    print(f"模型保存在: {config.output_dir}")


if __name__ == "__main__":
    main()
