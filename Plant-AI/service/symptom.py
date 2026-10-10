"""症状识别推理器 —— 输入叶片/植株照片，输出症状大类（健康/叶斑/白粉/黄化/锈病/虫害）。

与 recognizer.py（品种识别）的关系
--------------------------------
品种模型回答「是什么植物」，本模型回答「它怎么了」。两者串联才构成用户要的
「识别出是什么植物、得了什么病、给什么建议」。

预处理刻意复用 recognizer.build_val_transform：两个模型的训练/推理预处理必须一致，
各写一份极易漂移（A.Resize 是 cv2.resize、CenterCrop 偏移取 (r-size)//2，
与 torchvision 的 round(15.5)=16 不同），肉眼不可见但影响精度。

模型不存在时降级为 mock（与品种识别一致），保证链路可先跑通。
"""

import hashlib
import json
import logging
import os
import random
from pathlib import Path

import numpy as np

from recognizer import _softmax, build_val_transform, resolve_upload_path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent

MODEL_PATH = Path(os.environ.get("PLANT_SYMPTOM_MODEL", str(ROOT / "output_symptom" / "plant_symptom.onnx")))
LABELS_PATH = Path(os.environ.get("PLANT_SYMPTOM_LABELS", str(ROOT / "output_symptom" / "labels.json")))

DEFAULT_TOP_K = 3
# 低于此置信度不下结论，提示用户重拍。这是对「闭集分类会自信误判」的缓解：
# 模型永远会输出某个症状类（包括把健康叶判成病叶），必须有个说不准的出口。
LOW_CONF_THRESHOLD = 0.55
# 判为「健康」所需的最低置信度（健康误判成病会让用户白折腾买药，阈值给高一点）
HEALTHY_THRESHOLD = 0.60


class SymptomRecognizer:
    """症状识别器：ONNX 推理优先，否则确定性 mock。"""

    def __init__(self) -> None:
        self.session = None
        self.labels: list[dict] = []
        self.is_mock = True
        self._transform = build_val_transform()
        self._load()

    # ---------- 加载 ----------

    def _load(self) -> None:
        self.session = None
        self.labels = []
        self.is_mock = True

        if not MODEL_PATH.is_file():
            logger.warning("症状模型不存在: %s，降级为 mock 模式", MODEL_PATH)
            return

        try:
            import onnxruntime as ort

            self.session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
            if LABELS_PATH.is_file():
                # 必须显式 utf-8：Windows 默认 cp936，读中文会乱码
                with open(LABELS_PATH, "r", encoding="utf-8") as f:
                    self.labels = json.load(f)
            else:
                logger.warning("症状标签文件不存在: %s", LABELS_PATH)

            if not self.labels:
                logger.error("症状标签为空，无法把输出映射回症状名，仍走 mock")
                self.session = None
                return

            self.is_mock = False
            logger.info("症状模型加载成功: %s（%d 类）", MODEL_PATH, len(self.labels))
        except Exception as e:  # noqa: BLE001 — 加载失败必须降级，不能让服务起不来
            logger.error("症状模型加载失败: %s，降级为 mock 模式", e)
            self.session = None
            self.is_mock = True

    def reload(self) -> None:
        self._load()

    # ---------- 推理 ----------

    def _preprocess(self, path: Path) -> np.ndarray:
        from PIL import Image

        img = np.array(Image.open(path).convert("RGB"))
        image = self._transform(image=img)["image"]
        tensor = np.transpose(image, (2, 0, 1))
        return np.expand_dims(tensor, axis=0).astype(np.float32)

    def recognize(self, image_path: str, top_k: int = DEFAULT_TOP_K) -> dict:
        path = resolve_upload_path(image_path)
        if self.is_mock:
            return self._mock_recognize(path, top_k)
        return self._onnx_recognize(path, top_k)

    def _onnx_recognize(self, path: Path, top_k: int) -> dict:
        x = self._preprocess(path)
        logits = self.session.run(None, {"input": x})[0][0]
        probs = _softmax(logits)

        order = np.argsort(probs)[::-1][:top_k]
        candidates = []
        for idx in order:
            idx = int(idx)  # numpy.int64 不能直接进 JSON
            lab = self.labels[idx] if idx < len(self.labels) else {}
            candidates.append({
                "symptom": lab.get("name", f"symptom_{idx}"),
                "label": lab.get("label", lab.get("name", f"symptom_{idx}")),
                "dictCode": lab.get("dict_code"),
                "confidence": round(float(probs[idx]), 4),
            })

        top = candidates[0]
        healthy = top["symptom"] == "healthy"
        low_conf = top["confidence"] < (HEALTHY_THRESHOLD if healthy else LOW_CONF_THRESHOLD)

        return {
            "success": True,
            "is_mock": False,
            "symptom": top["symptom"],
            "symptomLabel": top["label"],
            "dictCode": top["dictCode"],
            # healthy 时 dictCode 为 None —— 让 Spring 侧明确「无需出病害建议」
            "healthy": healthy,
            "confidence": top["confidence"],
            "lowConfidence": low_conf,
            "candidates": candidates,
        }

    def _mock_recognize(self, path: Path, top_k: int) -> dict:
        """确定性 mock：同一张图结果稳定，便于判断链路是否稳定。"""
        if not self.labels:
            return {"success": True, "is_mock": True, "confidence": 0.0,
                    "healthy": False, "lowConfidence": True, "candidates": []}

        seed = int(hashlib.md5(path.read_bytes()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        order = list(range(len(self.labels)))
        rng.shuffle(order)

        top_conf = rng.uniform(0.55, 0.92)
        candidates = []
        for rank, i in enumerate(order[:top_k]):
            lab = self.labels[i]
            conf = top_conf if rank == 0 else max(0.01, top_conf * (0.15 ** rank))
            candidates.append({
                "symptom": lab.get("name"),
                "label": lab.get("label", lab.get("name")),
                "dictCode": lab.get("dict_code"),
                "confidence": round(conf, 4),
            })

        top = candidates[0]
        healthy = top["symptom"] == "healthy"
        return {
            "success": True,
            "is_mock": True,
            "symptom": top["symptom"],
            "symptomLabel": top["label"],
            "dictCode": top["dictCode"],
            "healthy": healthy,
            "confidence": top["confidence"],
            "lowConfidence": False,
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
            "labels": [x.get("name") for x in self.labels],
        }
