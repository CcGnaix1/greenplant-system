"""绿植推理服务：品种识别 + 症状诊断。

职责刻意保持最小：图片路径进 → 标签出。不碰数据库、不做业务拼装
（品种描述、诊断文案、历史落库都由 Spring 侧补全）。

两个模型：
    /recognize  品种识别（30 类，回答「这是什么植物」）
    /diagnose   症状识别（6 类，回答「它怎么了」）
    /analyze    一次调用同时给两者，前端诊断页用这个

启动：
    C:/Plant/plant-ai/venv/Scripts/python.exe -m uvicorn main:app --host 0.0.0.0 --port 5000
不要加 --reload：Windows 下会起额外进程并重复加载模型。
"""

import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from recognizer import DEFAULT_TOP_K, PlantRecognizer
from symptom import SymptomRecognizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="绿植品种识别与症状诊断服务", version="2.0.0")

# 全局单例：模型只在启动时加载一次
recognizer = PlantRecognizer()
symptom_recognizer = SymptomRecognizer()


class ImageRequest(BaseModel):
    image_path: str = Field(..., description="服务端可访问的图片绝对路径")
    top_k: int = Field(DEFAULT_TOP_K, ge=1, le=10)


@app.get("/health")
def health():
    """暴露两个模型各自的 isMock 状态，避免把 mock 结果误当成真实识别能力。

    品种模型的字段保留在顶层（isMock/labelsCount…），症状模型信息放 symptom 子对象，
    这样既加了信息又不破坏已有的读取方。
    """
    h = recognizer.health()
    h["symptom"] = symptom_recognizer.health()
    return h


@app.post("/reload")
def reload_model():
    """热更新模型：训练出新 onnx 后调用，无需重启服务。"""
    recognizer.reload()
    symptom_recognizer.reload()
    h = recognizer.health()
    h["symptom"] = symptom_recognizer.health()
    return h


@app.post("/recognize")
def recognize(req: ImageRequest):
    """品种识别（30 类）。"""
    try:
        return recognizer.recognize(req.image_path, req.top_k)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:  # noqa: BLE001 — 交给 Spring 侧统一兜底，不要漏成裸 500 堆栈
        logger.exception("品种推理失败: %s", req.image_path)
        raise HTTPException(status_code=500, detail=f"推理失败: {e}")


@app.post("/diagnose")
def diagnose(req: ImageRequest):
    """症状识别（6 类：健康/叶斑/白粉/黄化/锈病/虫害）。"""
    try:
        return symptom_recognizer.recognize(req.image_path, req.top_k)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("症状推理失败: %s", req.image_path)
        raise HTTPException(status_code=500, detail=f"推理失败: {e}")


@app.post("/analyze")
def analyze(req: ImageRequest):
    """一次给出「品种 + 症状」，省掉前端两次往返。

    两个模型各自独立降级：任一模型缺失只影响它自己那一半，
    另一半照常返回，Spring 侧按段判断，避免一个模型没训好就整条路断掉。
    """
    out: dict = {"success": True}
    try:
        out["species"] = recognizer.recognize(req.image_path, req.top_k)
    except Exception as e:  # noqa: BLE001
        logger.exception("分析-品种部分失败: %s", req.image_path)
        out["species"] = {"success": False, "error": str(e)}
    try:
        out["symptom"] = symptom_recognizer.recognize(req.image_path, req.top_k)
    except Exception as e:  # noqa: BLE001
        logger.exception("分析-症状部分失败: %s", req.image_path)
        out["symptom"] = {"success": False, "error": str(e)}
    out["is_mock"] = bool(
        (out["species"] or {}).get("is_mock") or (out["symptom"] or {}).get("is_mock")
    )
    return out
