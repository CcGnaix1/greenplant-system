"""植物数据集加载 — 支持 ImageFolder 格式

数据目录结构:
    data/plants/
        绿萝/
            img001.jpg
            img002.jpg
        多肉植物/
            img001.jpg
            ...
"""

import json
import os

import albumentations as A
from albumentations.pytorch import ToTensorV2
from torch.utils.data import Dataset
from PIL import Image
import numpy as np


# ImageNet 标准化参数
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def get_train_transforms(image_size: int = 224):
    """训练集数据增强"""
    return A.Compose([
        A.RandomResizedCrop(image_size, image_size, scale=(0.7, 1.0)),
        A.HorizontalFlip(p=0.5),
        A.VerticalFlip(p=0.2),
        A.RandomRotate90(p=0.3),
        A.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.1, p=0.5),
        A.GaussianBlur(blur_limit=(3, 5), p=0.2),
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ToTensorV2(),
    ])


def get_val_transforms(image_size: int = 224):
    """验证集数据变换"""
    return A.Compose([
        A.Resize(int(image_size * 1.14), int(image_size * 1.14)),
        A.CenterCrop(image_size, image_size),
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ToTensorV2(),
    ])


class PlantDataset(Dataset):
    """植物图片数据集"""

    def __init__(self, root_dir: str, transform=None):
        self.root_dir = root_dir
        self.transform = transform
        self.samples = []  # [(image_path, label_idx), ...]
        self.classes = []  # 类名列表
        self.class_to_idx = {}

        self._scan_directory()

    def _scan_directory(self):
        """扫描目录，构建样本列表"""
        classes = sorted([
            d for d in os.listdir(self.root_dir)
            if os.path.isdir(os.path.join(self.root_dir, d))
        ])
        self.classes = classes
        self.class_to_idx = {cls: idx for idx, cls in enumerate(classes)}

        for cls_name in classes:
            cls_dir = os.path.join(self.root_dir, cls_name)
            # 必须 sorted：train.py 用 random_split 的下标划分训练/验证集，而验证集会
            # 重建一次 PlantDataset 重新扫盘。两次 os.listdir 顺序若不同，下标就指向
            # 不同文件 —— 训练图混进验证集，val_acc 虚高，从而选错 best_model。
            for fname in sorted(os.listdir(cls_dir)):
                if fname.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    path = os.path.join(cls_dir, fname)
                    self.samples.append((path, self.class_to_idx[cls_name]))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]
        image = np.array(Image.open(path).convert("RGB"))

        if self.transform:
            augmented = self.transform(image=image)
            image = augmented["image"]

        return image, label

    def save_labels(self, output_path: str, species_ids_path: str | None = None):
        """保存标签映射文件

        类别序号由 sorted() 决定，与数据库 knowledge_id 顺序不同，必须靠
        species_ids.json 显式映射，否则模型输出索引会对错品种。
        """
        name_to_kid = {}
        if species_ids_path and os.path.exists(species_ids_path):
            with open(species_ids_path, "r", encoding="utf-8") as f:
                name_to_kid = json.load(f)
        else:
            print(f"警告: 未找到品种 id 映射 {species_ids_path}，knowledge_id 将留空")

        labels = [
            {"name": cls_name, "id": idx, "knowledge_id": name_to_kid.get(cls_name)}
            for idx, cls_name in enumerate(self.classes)
        ]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(labels, f, ensure_ascii=False, indent=2)
        mapped = sum(1 for x in labels if x["knowledge_id"] is not None)
        print(f"标签文件已保存: {output_path} ({len(labels)} 类，{mapped} 类已映射 id)")
        if mapped != len(labels):
            print("警告: 有类别未能映射到 knowledge_id，请检查 species_ids.json 与目录名是否一致")
