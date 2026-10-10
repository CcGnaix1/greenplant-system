"""植物品种识别推理器 —— ONNX Runtime 推理，模型缺失时降级为确定性 mock。

模型文件不存在时不报错，而是返回一组带 is_mock 标记的稳定结果，
保证前后端链路可以先跑通；训练完成后把 plant_model.onnx 放进 output/ 即可
切换为真实推理，代码无需改动。

预处理必须与 ml/dataset.py 的验证集变换严格一致，否则精度会莫名下降。
"""

import hashlib
import json
import logging
import os
import random
from pathlib import Path

import numpy as np
from albumentations import CenterCrop, Compose, Normalize, Resize
from PIL import Image

logger = logging.getLogger(__name__)

# 与 ml/dataset.py 的 IMAGENET_MEAN / IMAGENET_STD 必须一致
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

# 项目根 = 本文件所在 service/ 的上一级
ROOT = Path(__file__).resolve().parent.parent

MODEL_PATH = Path(os.environ.get("PLANT_MODEL_PATH", str(ROOT / "output" / "plant_model.onnx")))
LABELS_PATH = Path(os.environ.get("PLANT_LABELS_PATH", str(ROOT / "output" / "labels.json")))
SPECIES_IDS_PATH = Path(os.environ.get("PLANT_SPECIES_IDS", str(ROOT / "data" / "species_ids.json")))
# 只允许推理上传根目录下的文件，避免 image_path 被利用成任意文件读取
UPLOAD_ROOT = Path(os.environ.get("PLANT_UPLOAD_ROOT", "C:/Plant/upload")).resolve()

DEFAULT_TOP_K = 3

# 品种模型的输入分辨率 —— 必须与训练/导出时一致。
# 30 类模型在 320 上训练（实测室内测试集 0.8899 → 0.9170，+2.7 点）；
# 320 训练出的模型喂 224 输入会掉到 0.8591，所以推理侧**必须**按 320 预处理。
# 用环境变量可覆盖，便于 A/B 或回退。
#
# 注意：症状模型（symptom.py）是 224 训练的，也复用 build_val_transform ——
# 所以这里不能去改 build_val_transform 的默认值，只能单独给品种模型指定。
SPECIES_IMAGE_SIZE = int(os.environ.get("PLANT_MODEL_IMAGE_SIZE", "320"))

# ---------- 测试时增强（TTA）----------
# 实测（tests/eval_tta.py，室内测试集 1072 张）：单视角 0.9170 → 这三个视角平均 0.9235（+0.65 点）。
# 视角选「基准/缩小/放大」三种尺度而**不含水平翻转** —— 实测翻转单独看就略微有害（0.9123），
# 混进来会把增益从 +0.65 拉回 +0.37。
# 代价：输入 batch 变成 3，ONNX 的 batch 维是动态的，所以是**一次推理**而非三次调用，
# 实际耗时约 2~3 倍单视角（不是 3 倍）。
TTA_ENABLED = os.environ.get("PLANT_TTA", "1") != "0"
TTA_SCALES = (1.0, 0.88, 1.12)   # 相对 build_val_transform 的 resize 尺寸（基准 364）


def build_val_transform(image_size: int = 224) -> Compose:
    """与 ml/dataset.py 的 get_val_transforms 保持一致。

    注意不要把这里换成 PIL 的 Image.resize：A.Resize 底层是 cv2.resize，
    且 CenterCrop 的偏移量取 (r - size) // 2（255-224 → 15），
    与 torchvision 的 round(15.5)=16 不同。手写极易产生肉眼不可见但影响精度的漂移。
    """
    r = int(image_size * 1.14)  # 224 -> 255
    return build_val_transform_from_r(r, image_size)


def build_val_transform_from_r(r: int, image_size: int) -> Compose:
    """Resize 到 r 再中心裁剪到 image_size。

    与 build_val_transform 是同一个变换，只是把 resize 尺寸显式传进来 ——
    TTA 要在基准尺寸附近取几个尺度（更小=看整体、更大=看细节），
    裁剪后仍统一为 image_size，所以各视角可以堆成一个 batch 一次推理。
    """
    return Compose([
        Resize(r, r),
        CenterCrop(image_size, image_size),
        Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


def resolve_upload_path(image_path: str) -> Path:
    """校验并解析图片路径，拒绝越出上传根目录的路径。"""
    p = Path(image_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"图片不存在: {image_path}")
    if UPLOAD_ROOT not in p.parents:
        raise PermissionError(f"路径不在允许的上传目录内: {image_path}")
    return p


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / e.sum()


class PlantRecognizer:
    """品种识别器：ONNX 推理优先，否则确定性 mock。"""

    def __init__(self) -> None:
        self.session = None
        self.labels: list[dict] = []
        self.is_mock = True
        # 多视角预处理。TTA 关闭时就是单视角，走原有路径。
        if TTA_ENABLED:
            r = int(SPECIES_IMAGE_SIZE * 1.14)
            self._transforms = [
                build_val_transform_from_r(int(r * s), SPECIES_IMAGE_SIZE) for s in TTA_SCALES
            ]
        else:
            self._transforms = [build_val_transform(SPECIES_IMAGE_SIZE)]
        self._species_ids: dict[str, int] = {}
        self._load()

    # ---------- 加载 ----------

    def _load_species_ids(self) -> None:
        if SPECIES_IDS_PATH.is_file():
            with open(SPECIES_IDS_PATH, "r", encoding="utf-8") as f:
                self._species_ids = json.load(f)
        else:
            logger.warning("品种 id 映射不存在: %s", SPECIES_IDS_PATH)

    def _load(self) -> None:
        self._load_species_ids()
        self.session = None
        self.labels = []
        self.is_mock = True

        if not MODEL_PATH.is_file():
            logger.warning("模型文件不存在: %s，降级为 mock 模式", MODEL_PATH)
            return

        try:
            import onnxruntime as ort

            self.session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])

            if LABELS_PATH.is_file():
                # 必须显式 utf-8：Windows 默认 cp936，读中文品种名会乱码
                with open(LABELS_PATH, "r", encoding="utf-8") as f:
                    self.labels = json.load(f)
            else:
                logger.warning("标签文件不存在: %s", LABELS_PATH)

            if not self.labels:
                logger.error("标签为空，无法把模型输出映射回品种，仍走 mock")
                self.session = None
                return

            self.is_mock = False
            logger.info("模型加载成功: %s（%d 类）", MODEL_PATH, len(self.labels))
        except Exception as e:  # noqa: BLE001 — 加载失败必须降级而不是让服务起不来
            logger.error("模型加载失败: %s，降级为 mock 模式", e)
            self.session = None
            self.is_mock = True

    def reload(self) -> None:
        """热更新：训练出模型后无需重启服务。"""
        self._load()

    # ---------- 预处理 ----------

    def _preprocess(self, path: Path) -> np.ndarray:
        """返回 (视角数, 3, H, W)。单视角时第一维为 1，形状与改造前等价。"""
        img = np.array(Image.open(path).convert("RGB"))
        # Albumentations 输出 HWC numpy；直接转成 ONNX 所需 CHW，避免仅为
        # ToTensorV2 引入体积很大的 PyTorch 推理依赖。
        views = [np.transpose(tf(image=img)["image"], (2, 0, 1)) for tf in self._transforms]
        return np.stack(views).astype(np.float32)

    # ---------- 推理 ----------

    def recognize(self, image_path: str, top_k: int = DEFAULT_TOP_K) -> dict:
        path = resolve_upload_path(image_path)
        if self.is_mock:
            return self._mock_recognize(path, top_k)
        return self._onnx_recognize(path, top_k)

    def _onnx_recognize(self, path: Path, top_k: int) -> dict:
        x = self._preprocess(path)                    # (n,3,H,W)，n = 视角数
        logits = self.session.run(None, {"input": x})[0]   # (n,C)
        # 逐视角 softmax 后取平均 —— 先 softmax 再平均（而不是平均 logit），
        # 这样各视角的置信度尺度一致，是 TTA 的常规做法。
        probs = np.mean([_softmax(row) for row in logits], axis=0)

        order = np.argsort(probs)[::-1][:top_k]
        candidates = []
        for idx in order:
            idx = int(idx)  # numpy.int64 不能直接进 JSON
            label = self.labels[idx] if idx < len(self.labels) else {}
            candidates.append({
                "species": label.get("name", f"植物_{idx}"),
                # labels.json 由 dataset.save_labels 生成，带 knowledge_id；
                # 不要用 idx —— 那是字母序下标，与 plant_knowledge.knowledge_id 不同
                "knowledgeId": label.get("knowledge_id"),
                "confidence": round(float(probs[idx]), 4),
            })

        return {
            "success": True,
            "is_mock": False,
            "confidence": candidates[0]["confidence"] if candidates else 0.0,
            "candidates": candidates,
        }

    def _mock_recognize(self, path: Path, top_k: int) -> dict:
        """确定性 mock：同一张图每次结果相同。

        用参考实现那种 random.uniform 会让每次结果都变，演示时很迷惑、
        也无法判断链路是否稳定，所以这里用图片内容 hash 做种子。
        """
        species = list(self._species_ids.keys())
        if not species:
            return {"success": True, "is_mock": True, "confidence": 0.0, "candidates": []}

        seed = int(hashlib.md5(path.read_bytes()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        top1 = rng.randrange(len(species))
        order = [top1] + [i for i in range(len(species)) if i != top1]
        rng.shuffle(order[1:])

        top_conf = rng.uniform(0.82, 0.96)
        candidates = []
        for rank, i in enumerate(order[:top_k]):
            name = species[i]
            conf = top_conf if rank == 0 else max(0.01, top_conf * (0.12 ** rank))
            candidates.append({
                "species": name,
                "knowledgeId": self._species_ids.get(name),
                "confidence": round(conf, 4),
            })

        return {
            "success": True,
            "is_mock": True,
            "confidence": candidates[0]["confidence"],
            "candidates": candidates,
        }

    # ---------- 状态 ----------

    def health(self) -> dict:
        return {
            "status": "ok",
            "isMock": self.is_mock,
            "modelPath": str(MODEL_PATH),
            "labelsPath": str(LABELS_PATH),
            "labelsCount": len(self.labels),
            "imageSize": SPECIES_IMAGE_SIZE,
            "tta": TTA_ENABLED,
            "ttaScales": list(TTA_SCALES) if TTA_ENABLED else [],
            "labels": [x.get("name") for x in self.labels],
        }
