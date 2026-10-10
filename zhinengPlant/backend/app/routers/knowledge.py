"""routers/knowledge.py —— 知识库 / 个性化养护计划 / 提醒"""
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Header
from ..db import get_conn
from ..auth import current_user_id

router = APIRouter(tags=["知识库与提醒"])


def _parse_faq(faq_text: str):
    try:
        return json.loads(faq_text)
    except Exception:
        return []


@router.get("/knowledge/species/{species_id}")
def species_knowledge(species_id: int, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM knowledge_content WHERE species_id=?", (species_id,)).fetchone()
        if not row:
            return {"code": 4040, "msg": "暂无该品种知识", "data": None}
        return {"code": 0, "msg": "ok",
                "data": {"speciesId": species_id, "habit": row["habit"],
                         "seasons": [s.strip() for s in (row["seasons"] or "").split(";") if s.strip()],
                         "water": row["water"], "fertilize": row["fertilize"],
                         "breed": row["breed"], "faq": _parse_faq(row["faq"])}}
    finally:
        conn.close()


@router.get("/knowledge/search")
def knowledge_search(keyword: str = "", authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        sql = ("SELECT k.*, s.name FROM knowledge_content k "
               "JOIN plant_species s ON s.id=k.species_id ")
        args = []
        if keyword:
            sql += "WHERE s.name LIKE ? OR k.habit LIKE ? "
            args = [f"%{keyword}%", f"%{keyword}%"]
        rows = conn.execute(sql, args).fetchall()
        return {"code": 0, "msg": "ok",
                "data": [{"id": r["species_id"], "name": r["name"], "desc": (r["habit"] or "")[:30]} for r in rows]}
    finally:
        conn.close()


@router.get("/plants/{plant_id}/care-plan")
def care_plan(plant_id: int, authorization: str = Header(default="")):
    """个性化养护计划：动态文案要素（习惯、干燥天数、建议时间、下次日期）"""
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        p = conn.execute("SELECT * FROM plant_profile WHERE id=?", (plant_id,)).fetchone()
        if not p:
            return {"code": 4040, "msg": "植物不存在", "data": None}
        sp = conn.execute("SELECT * FROM plant_species WHERE id=?", (p["species_id"],)).fetchone()
        env = json.loads(sp["env_snapshot"]) if sp else {}
        last = p["last_water_at"]
        dry_days = 0
        if last:
            dry_days = max(0, (datetime.now() - datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).days)
        items = conn.execute("SELECT * FROM care_plan_item WHERE plant_id=? AND done=0 ORDER BY due_date LIMIT 5",
                             (plant_id,)).fetchall()
        data = []
        for it in items:
            data.append({
                "taskType": it["task_type"], "plantName": p["name"],
                "habit": env.get("light", "散射光"), "dryDays": dry_days,
                "suggestion": "建议在傍晚浇透水" if it["task_type"] == "watering" else "按计划执行",
                "lastDoneAt": last or "-", "nextDueDate": it["due_date"],
            })
        if not data:  # 无计划项时给默认
            data.append({
                "taskType": "watering", "plantName": p["name"], "habit": env.get("light", "散射光"),
                "dryDays": dry_days, "suggestion": "建议在傍晚浇透水",
                "lastDoneAt": last or "-",
                "nextDueDate": (datetime.now() + timedelta(days=p["water_interval_days"])).strftime("%Y-%m-%d"),
            })
        return {"code": 0, "msg": "ok", "data": data}
    finally:
        conn.close()


@router.get("/notifications")
def notifications(isRead: int = 0, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM notification WHERE user_id=? AND is_read=? ORDER BY created_at DESC LIMIT 50",
            (uid, isRead)).fetchall()
        return {"code": 0, "msg": "ok",
                "data": [{"id": r["id"], "title": r["title"], "time": r["created_at"], "read": bool(r["is_read"])} for r in rows]}
    finally:
        conn.close()


@router.patch("/notifications/{nid}/read")
def mark_read(nid: int, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        conn.execute("UPDATE notification SET is_read=1 WHERE id=? AND user_id=?", (nid, uid))
        conn.commit()
        return {"code": 0, "msg": "ok", "data": {"id": nid}}
    finally:
        conn.close()
