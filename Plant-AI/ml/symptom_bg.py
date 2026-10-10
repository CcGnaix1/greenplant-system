"""背景合成数据管线 —— 治「模型靠背景判病」这个根因。

问题（2026-09-29 实测）
----------------------
第一版症状模型在 PlantVillage 官方测试集上 0.9986，但拿真实整株照片一测：
只有 29.6% 判为健康，**66.2% 判成叶斑病**。抽查健康琴叶榕的照片，模型给
「叶斑病 0.82」—— 图里叶子是翠绿的，模型看的是**背景里的枯叶和泥土**。

根因：PlantVillage 全是「单叶居中 + 纯灰背景」。模型学到的最省力特征是
「画面里有没有不规则深色区域」——在实验室照上等价于「病斑」，在真实照片上
等价于「土壤/落叶/阴影/别的植株」。所以它对真实照片一律报病。

治法
----
1) **背景合成**：用 segmented 变体（叶片抠在黑底上）把病叶贴到真实照片背景上，
   标签不变。模型要正确就不能再看背景，只能看叶片本身的花纹。
2) **真实整株照当健康样本**：手上 30 个品种的栽培照（iNat captive/cultivated）
   基本都是健康的整株盆栽，正是「真实背景 + 无病」的样本，补上这一域。

数据划分（避免自欺）
------------------
plants_indoor 按文件名的稳定哈希三分，互斥：
    train(60%)  作为「健康」训练样本
    bg(20%)     仅当背景贴图，不参与任何评估
    test(20%)   跨域测试集，训练时完全不可见 —— 用它的误报率衡量「手机拍照能不能用」
背景池与测试集必须互斥，否则等于拿测试图当训练背景。
"""

import hashlib
import json
import random
from pathlib import Path

import numpy as np
from PIL import Image
from torch.utils.data import Dataset

ML_DIR = Path(__file__).resolve().parent
ROOT = ML_DIR.parent

PV_ROOT = ROOT / "data" / "raw" / "plantvillage" / "extracted"
INDOOR = ROOT / "data" / "plants_indoor"
HEALTHY_LABEL = "healthy"


# ---------------------------------------------------------------- 划分

def _bucket(name: str) -> int:
    """按文件名稳定分桶（同一台机器上可复现，且不依赖目录顺序）。"""
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 100


def split_indoor(indoor: Path = INDOOR, train_pct: int = 60, bg_pct: int = 20):
    """把真实栽培照按 60/20/20 分成 训练(健康样本) / 背景池 / 跨域测试。

    返回 (train_paths, bg_paths, test_paths)。
    """
    train, bg, test = [], [], []
    for d in sorted(p for p in indoor.iterdir() if p.is_dir()):
        for f in sorted(d.iterdir()):
            if f.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                continue
            b = _bucket(f"{d.name}/{f.name}")
            if b < train_pct:
                train.append(str(f))
            elif b < train_pct + bg_pct:
                bg.append(str(f))
            else:
                test.append(str(f))
    return train, bg, test


# ---------------------------------------------------------------- 合成

def _leaf_mask(seg_rgb: np.ndarray) -> np.ndarray:
    """segmented 变体是「叶片在黑底上」，黑底即背景。

    用「任一通道明显>阈值」判叶片，比只看亮度稳：叶片阴影处可能整体偏暗，
    但通常仍有颜色分量高于纯黑背景。
    """
    return seg_rgb.max(axis=2) > 16


def composite_leaf(seg_path: str, bg_path: str, rng: random.Random,
                   out_size: int = 224) -> np.ndarray:
    """把抠出的叶片贴到真实背景上，返回 RGB uint8。

    叶片的缩放与位置随机化：位置/大小不随机，模型可能靠「叶片总在正中」这一
    无关特征偷懒；随机化后它必须真正看叶片内容。
    """
    seg = np.array(Image.open(seg_path).convert("RGB"))
    mask = _leaf_mask(seg)
    if mask.sum() < 50:  # 分割失败（全黑）时退回原图，不制造垃圾样本
        return np.array(Image.open(bg_path).convert("RGB").resize((out_size, out_size)))

    ys, xs = np.where(mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    leaf = seg[y0:y1, x0:x1]
    leaf_m = mask[y0:y1, x0:x1]

    bg = Image.open(bg_path).convert("RGB")
    bg = bg.resize((out_size, out_size))
    canvas = np.array(bg)

    # 目标边长：让叶片占画布 35%~80%
    target = int(out_size * rng.uniform(0.35, 0.80))
    lh, lw = leaf.shape[:2]
    scale = target / max(lh, lw)
    nh, nw = max(1, int(lh * scale)), max(1, int(lw * scale))

    leaf_img = Image.fromarray(leaf).resize((nw, nh))
    leaf_arr = np.array(leaf_img)
    mask_img = Image.fromarray((leaf_m * 255).astype(np.uint8)).resize((nw, nh))
    m2 = np.array(mask_img) > 127

    # 随机位置（保证完全落在画布内）
    ty = rng.randint(0, max(0, out_size - nh))
    tx = rng.randint(0, max(0, out_size - nw))
    region = canvas[ty:ty + nh, tx:tx + nw]
    region[m2] = leaf_arr[m2]
    return canvas


# ---------------------------------------------------------------- 数据集

class SymptomBgDataset(Dataset):
    """训练集：PlantVillage（可合成到真实背景）+ 真实整株照（健康）。

    参数
    ----
    index_csv : prepare_symptom_data.py 产出的索引
    split     : 'train' 时启用合成与真实样本；'test' 时只用 PlantVillage 原图（域内基线）
    composite_prob : PlantVillage 样本按此概率合成到真实背景（其余走原图，
        保留一部分「实验室照」分布，避免模型完全没见过原域）
    real_healthy_frac : 每个 batch 中约多大比例来自真实整株照。
        实现方式是按此比例**重复采样** PlantVillage 索引（不是丢样本），
        这样总样本数与类别计数仍可控。
    """

    def __init__(self, index_csv, bg_paths, real_healthy_paths, classes,
                 transform=None, split: str = "train",
                 composite_prob: float = 0.7, real_healthy_frac: float = 0.25,
                 seed: int = 42, pv_root: Path = PV_ROOT):
        self.transform = transform
        self.classes = classes
        self.class_to_idx = {c: i for i, c in enumerate(classes)}
        self.split = split
        self.composite_prob = composite_prob if split == "train" else 0.0
        self.bg_paths = list(bg_paths)
        self.seed = seed
        self.pv_root = Path(pv_root)
        self._epoch = 0

        self.samples = []   # (kind, payload, label)
        self.real_count = 0
        self._load_pv(Path(index_csv))
        if split == "train" and real_healthy_paths:
            self._load_real(real_healthy_paths, real_healthy_frac)

        if not self.samples:
            raise SystemExit(f"[错误] split={split} 没有样本")

    # ---- 装载 ----

    def _load_pv(self, csv_path: Path):
        missing_seg = 0
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("path,"):
                    continue
                path, sym, split = line.rsplit(",", 2)
                if split != self.split:
                    continue
                path = path.strip('"')
                if not Path(path).is_file():
                    continue
                label = self.class_to_idx[sym]

                # 对应的 segmented 路径。注意**不能只换目录**：segmented 的文件名
                # 与 color 不同 —— 多了 _final_masked 后缀、扩展名也变成小写 .jpg
                # （实测 color 目录与 segmented 目录的同名交集为 0）。
                # 例：<uuid>___FREC_Scab 3335.JPG → <uuid>___FREC_Scab 3335_final_masked.jpg
                seg = None
                parts = Path(path).parts
                if "color" in parts:
                    i = parts.index("color")
                    src = Path(path)
                    cand = Path(*parts[:i], "segmented", *parts[i + 1:-1]) / \
                        (src.stem + "_final_masked.jpg")
                    if cand.is_file():
                        seg = str(cand)
                    else:
                        missing_seg += 1
                self.samples.append(("pv", (path, seg), label))
        if missing_seg:
            print(f"[警告] {missing_seg} 张 PlantVillage 图找不到 segmented 对应文件，"
                  f"这些样本将不做背景合成")

    def _load_real(self, paths, frac: float):
        """把真实整株照作为「健康」样本。

        frac=0.25 表示让真实照占最终样本的约 25%：按 pv 数量反推需要多少张，
        不够就按整份重复采样（真实照只有约 4300 张，pv 有 4 万多张）。
        """
        hi = self.class_to_idx[HEALTHY_LABEL]
        n_pv = len(self.samples)
        want = int(n_pv * frac / max(1e-6, (1 - frac)))
        pool = [str(p) for p in paths if Path(p).is_file()]
        if not pool:
            return
        reps = max(1, want // len(pool))
        for _ in range(reps):
            for p in pool:
                self.samples.append(("real", p, hi))
        self.real_count = reps * len(pool)

    # ---- 取数 ----

    def set_epoch(self, epoch: int):
        """每轮换随机种子，让合成背景与位置在轮间变化（等价于增广多样性）。"""
        self._epoch = epoch

    def counts(self) -> dict:
        c = {n: 0 for n in self.classes}
        for kind, _, lab in self.samples:
            c[self.classes[lab]] += 1
        return c

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        kind, payload, label = self.samples[idx]
        # 确定性种子：不要用 tuple.__hash__()，它受 PYTHONHASHSEED 影响，
        # 同一份数据两次跑会得到不同的合成图，排障时无法复现
        rng = random.Random(self.seed * 1000003 + self._epoch * 10007 + idx)

        if kind == "pv":
            color_path, seg_path = payload
            if seg_path and self.bg_paths and rng.random() < self.composite_prob:
                bg = self.bg_paths[rng.randrange(len(self.bg_paths))]
                try:
                    img = composite_leaf(seg_path, bg, rng)
                except Exception:
                    img = np.array(Image.open(color_path).convert("RGB"))
            else:
                img = np.array(Image.open(color_path).convert("RGB"))
        else:
            img = np.array(Image.open(payload).convert("RGB"))

        if self.transform:
            img = self.transform(image=img)["image"]
        return img, label


class RealPhotoEval(Dataset):
    """跨域评估集：真实整株照，全部标为 healthy。

    严格说这些图**没有健康标注**，iNat 的 captive/cultivated 只说明是栽培个体。
    所以这不是「准确率」，而是**误报率**：一株看起来正常的盆栽被报成病害的比例。
    这是本功能能否上线的主要判据。
    """

    def __init__(self, paths, classes, transform=None):
        self.classes = classes
        self.transform = transform
        hi = classes.index(HEALTHY_LABEL)
        self.samples = [(str(p), hi) for p in paths if Path(p).is_file()]

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]
        img = np.array(Image.open(path).convert("RGB"))
        if self.transform:
            img = self.transform(image=img)["image"]
        return img, label
