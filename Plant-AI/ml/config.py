"""模型训练配置"""

from dataclasses import dataclass, field
from pathlib import Path

# 项目根 = 本文件所在 ml/ 的上一级。用相对定位而非硬编码绝对路径，
# 这样整个 plant-ai 目录被移动/改名后训练脚本不会静默扫到空目录。
ROOT = Path(__file__).resolve().parent.parent


@dataclass
class TrainConfig:
    """训练超参数配置"""

    # 数据
    data_dir: str = str(ROOT / "data" / "plants")
    image_size: int = 224
    num_workers: int = 4
    train_split: float = 0.8
    # 固定划分随机种子，保证每次训练的训练/验证集切分一致，指标可比
    seed: int = 42

    # 模型
    model_name: str = "mobilenet_v3_large"
    pretrained: bool = True
    num_classes: int = 6  # 与 plant_db.plant_knowledge 的 6 个品种对齐

    # 训练
    batch_size: int = 32
    epochs: int = 50
    learning_rate: float = 0.001
    weight_decay: float = 1e-4
    warmup_epochs: int = 5
    label_smoothing: float = 0.1

    # 学习率调度
    scheduler: str = "cosine"  # cosine | step
    min_lr: float = 1e-6

    # 数据增强
    random_crop_scale: tuple = (0.7, 1.0)
    color_jitter: tuple = (0.3, 0.3, 0.3, 0.1)
    random_erasing: float = 0.2

    # 输出
    output_dir: str = str(ROOT / "output")
    save_every: int = 5  # 每 N 个 epoch 保存一次
    # 下面两个由 __post_init__ 按 output_dir 推导：训练传了 --output_dir 时，
    # 模型和 labels.json 必须落在同一个目录，否则推理服务找不到标签。
    onnx_path: str = ""
    labels_path: str = ""
    # 品种名 → plant_knowledge.knowledge_id 的映射，导出 labels.json 时带上 knowledge_id
    species_ids_path: str = str(ROOT / "data" / "species_ids.json")

    def __post_init__(self):
        self.onnx_path = str(Path(self.output_dir) / "plant_model.onnx")
        self.labels_path = str(Path(self.output_dir) / "labels.json")


@dataclass
class EvalConfig:
    """评估配置"""
    model_path: str = str(ROOT / "output" / "best_model.pth")
    data_dir: str = str(ROOT / "data" / "plants")
    output_dir: str = str(ROOT / "output")
    image_size: int = 224
    batch_size: int = 64
    num_workers: int = 4
