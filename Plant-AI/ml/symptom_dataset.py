"""症状数据集 —— 从索引 CSV 读，而不是 ImageFolder 目录。

为什么不复用 dataset.py 的 PlantDataset
--------------------------------------
重标后的数据仍指向 PlantVillage 的原图（用索引而非复制，省 ~2GB 与一份易失同步的副本），
而 PlantDataset 是按目录扫盘的。这里读 prepare_symptom_data.py 产出的 CSV。

类别顺序刻意用 taxonomy 声明顺序的 sorted()，与训练/推理两侧保持一致：
labels.json 按同一顺序落盘，推理服务把 argmax 下标直接映射回症状名。
"""

import csv
import json
import os
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset

ML_DIR = Path(__file__).resolve().parent
ROOT = ML_DIR.parent
TAXONOMY = ML_DIR / "symptom_taxonomy.json"
INDEX = ROOT / "data" / "symptoms_index.csv"


def load_classes(taxonomy_path: Path = TAXONOMY) -> list[str]:
    """症状类名，按 sorted() —— 必须与 PlantDataset/推理侧一致的确定性顺序。"""
    tax = json.loads(Path(taxonomy_path).read_text(encoding="utf-8"))
    return sorted(tax["symptoms"])


def load_meta(taxonomy_path: Path = TAXONOMY) -> dict:
    return json.loads(Path(taxonomy_path).read_text(encoding="utf-8"))


class SymptomDataset(Dataset):
    """按索引 CSV + split 名构建；transform 复用 dataset.py 的那套。"""

    def __init__(self, csv_path: str | Path = INDEX, split: str = "train",
                 classes: list[str] | None = None, transform=None,
                 taxonomy_path: Path = TAXONOMY):
        self.transform = transform
        self.classes = classes or load_classes(taxonomy_path)
        self.class_to_idx = {c: i for i, c in enumerate(self.classes)}
        self.samples: list[tuple[str, int]] = []

        csv_path = Path(csv_path)
        if not csv_path.is_file():
            raise FileNotFoundError(
                f"索引不存在: {csv_path}\n先跑 python prepare_symptom_data.py"
            )

        unknown = set()
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row["split"] != split:
                    continue
                sym = row["symptom"]
                if sym not in self.class_to_idx:
                    unknown.add(sym)
                    continue
                path = row["path"]
                if not os.path.isfile(path):
                    continue
                self.samples.append((path, self.class_to_idx[sym]))

        if unknown:
            raise SystemExit(f"[错误] 索引里有 taxonomy 未声明的症状类: {sorted(unknown)}")
        if not self.samples:
            raise SystemExit(f"[错误] split={split} 没有任何样本（索引为空或路径全失效）")

        present = {self.classes[i] for _, i in self.samples}
        missing = set(self.classes) - present
        if missing:
            raise SystemExit(f"[错误] split={split} 缺少这些症状类: {sorted(missing)}")

    def counts(self) -> dict[str, int]:
        c = {name: 0 for name in self.classes}
        for _, i in self.samples:
            c[self.classes[i]] += 1
        return c

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        path, label = self.samples[idx]
        image = np.array(Image.open(path).convert("RGB"))
        if self.transform:
            image = self.transform(image=image)["image"]
        return image, label


def make_class_weights(counts: dict[str, int], classes: list[str],
                       power: float = 0.5) -> torch.Tensor:
    """按样本数给交叉熵权重。

    用 power=0.5（而不是完全倒数）是本数据的折中：最大类(leaf_spot)与最小类(rust/pest)
    相差约 13 倍，纯倒数会把小类放大 13 倍、容易过拟合到小类的少数样本；
    开方后约 3.6 倍，既让小类不被淹没，又不至于把小类的噪声当成主要信号。
    """
    n = sum(counts.values())
    k = len(classes)
    w = []
    for c in classes:
        cnt = max(counts.get(c, 0), 1)
        w.append((n / (k * cnt)) ** power)
    t = torch.tensor(w, dtype=torch.float32)
    return t / t.mean()
