"""routers/export.py —— 数据导出（PDF / Excel）
开发期：返回 JSON 摘要 + 占位下载提示；真实实现用 reportlab（PDF）/ openpyxl（Excel）
生成文件并返回下载 URL（前端 wx.downloadFile + wx.openDocument）。
"""
from datetime import datetime
from fastapi import APIRouter, Header
from ..db import get_conn
from ..auth import current_user_id

router = APIRouter(prefix="/export", tags=["数据导出"])


@router.get("/plant/{plant_id}")
def export_plant(plant_id: int, format: str = "pdf", authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        p = conn.execute("SELECT * FROM plant_profile WHERE id=?", (plant_id,)).fetchone()
        if not p:
            return {"code": 4040, "msg": "植物不存在", "data": None}
        records = conn.execute(
            "SELECT * FROM care_record WHERE plant_id=? ORDER BY created_at DESC", (plant_id,)).fetchall()
        data = {
            "plant": {"name": p["name"], "heightCm": p["height_cm"], "potMaterial": p["pot_material"],
                      "emotionTag": p["emotion_tag"], "createdAt": p["created_at"]},
            "recordCount": len(records),
            "records": [{"type": r["type"], "note": r["note"], "time": r["created_at"]} for r in records],
            "fileUrl": None,   # 真实实现：生成 PDF/Excel 后返回可下载 URL
        }
        return {"code": 0, "msg": "ok", "data": data}
    finally:
        conn.close()


@router.get("/records")
def export_records(format: str = "excel", start: str = "", end: str = "",
                   authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        sql = "SELECT * FROM care_record WHERE user_id=?"
        args = [uid]
        if start:
            sql += " AND created_at >= ?"
            args.append(start)
        if end:
            sql += " AND created_at <= ?"
            args.append(end)
        rows = conn.execute(sql + " ORDER BY created_at DESC", args).fetchall()
        return {"code": 0, "msg": "ok",
                "data": {"count": len(rows),
                         "rows": [{"plantId": r["plant_id"], "type": r["type"], "note": r["note"],
                                   "time": r["created_at"]} for r in rows],
                         "fileUrl": None}}
    finally:
        conn.close()
