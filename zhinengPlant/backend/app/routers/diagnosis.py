"""routers/diagnosis.py —— 品种识别 / 健康诊断 / 反馈"""
import json
from fastapi import APIRouter, Header, UploadFile, File, Form
from ..db import get_conn
from ..auth import current_user_id
from ..mock_ai import recognize as mock_recognize, diagnose as mock_diagnose

router = APIRouter(tags=["识别与诊断"])


@router.post("/species/recognize")
async def recognize(image: UploadFile = File(...), authorization: str = Header(default="")):
    """
    品种识别：接收 multipart 图片（字段名 image），返回候选品种。
    当前为 mock；真实实现加载品种分类模型（见 app/mock_ai.py）。
    """
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    if not image:
        return {"code": 4001, "msg": "缺少图片", "data": None}
    data = mock_recognize()
    top = data["candidates"][0]
    if top["confidence"] < 0.5:   # 阈值兜底：置信度过低
        return {"code": 6001, "msg": "无法确认植物品种，请手动选择或换一张更清晰的照片", "data": data}
    return {"code": 0, "msg": "ok", "data": data}


@router.post("/diagnosis")
async def diagnosis(image: UploadFile = File(...), plantId: int = Form(default=0),
                    authorization: str = Header(default="")):
    """
    健康诊断：multipart 图片字段 image，可选 plantId。
    返回症状多标签 + 诊断报告（mock；真实实现见 app/mock_ai.py 的模型推理）。
    """
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    if not image:
        return {"code": 4001, "msg": "缺少图片", "data": None}
    data = mock_diagnose()
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO diagnosis_record (plant_id, user_id, symptoms, report) VALUES (?,?,?,?)",
            (plantId or 0, uid, json.dumps(data["symptoms"], ensure_ascii=False),
             json.dumps(data["report"], ensure_ascii=False)))
        conn.commit()
        data["diagnosisId"] = cur.lastrowid
        return {"code": 0, "msg": "ok", "data": data}
    finally:
        conn.close()


@router.get("/diagnosis/{diag_id}")
def diagnosis_detail(diag_id: int, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM diagnosis_record WHERE id=?", (diag_id,)).fetchone()
        if not row:
            return {"code": 4040, "msg": "诊断记录不存在", "data": None}
        return {"code": 0, "msg": "ok",
                "data": {"diagnosisId": row["id"],
                         "symptoms": json.loads(row["symptoms"]),
                         "report": json.loads(row["report"]),
                         "createdAt": row["created_at"]}}
    finally:
        conn.close()


@router.post("/diagnosis/{diag_id}/feedback")
def feedback(diag_id: int, authorization: str = Header(default="")):
    """用户反馈（回流再训练标记）"""
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        conn.execute("UPDATE diagnosis_record SET feedback=1 WHERE id=?", (diag_id,))
        conn.commit()
        return {"code": 0, "msg": "ok", "data": {"diagnosisId": diag_id, "feedback": True}}
    finally:
        conn.close()
