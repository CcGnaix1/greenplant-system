"""routers/plants.py —— 植物档案 + 养护记录 + 时光轴 + 统计"""
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Header, UploadFile, File
from ..db import get_conn
from ..auth import current_user_id
from ..schemas import PlantCreateIn, PlantUpdateIn, CareRecordIn, WateringIn, GrowthIn

router = APIRouter(prefix="/plants", tags=["植物档案"])


def _env_of_species(conn, species_id: int) -> dict:
    row = conn.execute("SELECT env_snapshot FROM plant_species WHERE id=?", (species_id,)).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["env_snapshot"])
    except Exception:
        return {}


def _plant_card(row) -> dict:
    return {
        "id": row["id"], "name": row["name"], "species": "", "familyName": "",
        "tag": "茁壮成长", "status": row["status"], "cover": row["name"][:1],
        "heightCm": row["height_cm"], "recordCount": 0, "nextDue": "",
        "env": {}, "photoUrl": row["photo_url"],
    }


@router.post("")
def create_plant(body: PlantCreateIn, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    if not body.name or not body.speciesId:
        return {"code": 4001, "msg": "名称和品种必填", "data": None}
    conn = get_conn()
    try:
        env = _env_of_species(conn, body.speciesId)
        cur = conn.execute(
            "INSERT INTO plant_profile (family_id, user_id, species_id, name, purchase_date,"
            " pot_material, init_height_cm, emotion_tag, photo_url, height_cm, water_interval_days)"
            " VALUES (0,?,?,?,?,?,?,?,?,?,?)",
            (uid, body.speciesId, body.name, body.purchaseDate, body.potMaterial,
             body.initHeightCm, body.emotionTag, body.photoUrl,
             body.initHeightCm or 0, env.get("waterIntervalDays", 7)))
        pid = cur.lastrowid
        # 自动创建默认养护计划项（浇水）
        conn.execute("INSERT INTO care_plan_item (plant_id, task_type, due_date) VALUES (?,?,?)",
                     (pid, "watering", (datetime.now() + timedelta(days=env.get("waterIntervalDays", 7))).strftime("%Y-%m-%d")))
        conn.commit()
        return {"code": 0, "msg": "ok",
                "data": {"id": pid, "env": env, "message": "建档成功，已生成默认养护计划"}}
    finally:
        conn.close()


@router.get("")
def list_plants(keyword: str = "", page: int = 1, size: int = 20,
                authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        sql = "SELECT * FROM plant_profile WHERE archived=0 AND user_id=? "
        args = [uid]
        if keyword:
            sql += "AND name LIKE ? "
            args.append(f"%{keyword}%")
        sql += "ORDER BY id DESC LIMIT ? OFFSET ?"
        args += [size, (page - 1) * size]
        rows = conn.execute(sql, args).fetchall()
        data = []
        for r in rows:
            card = _plant_card(r)
            sp = conn.execute("SELECT name FROM plant_species WHERE id=?", (r["species_id"],)).fetchone()
            card["species"] = sp["name"] if sp else ""
            cnt = conn.execute("SELECT COUNT(*) c FROM care_record WHERE plant_id=?", (r["id"],)).fetchone()["c"]
            card["recordCount"] = cnt
            data.append(card)
        return {"code": 0, "msg": "ok", "data": data}
    finally:
        conn.close()


@router.get("/{plant_id}")
def plant_detail(plant_id: int, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM plant_profile WHERE id=? AND archived=0", (plant_id,)).fetchone()
        if not r:
            return {"code": 4040, "msg": "植物不存在", "data": None}
        card = _plant_card(r)
        sp = conn.execute("SELECT * FROM plant_species WHERE id=?", (r["species_id"],)).fetchone()
        card["species"] = sp["name"] if sp else ""
        card["env"] = _env_of_species(conn, r["species_id"])
        return {"code": 0, "msg": "ok", "data": card}
    finally:
        conn.close()


@router.patch("/{plant_id}")
def update_plant(plant_id: int, body: PlantUpdateIn, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM plant_profile WHERE id=?", (plant_id,)).fetchone()
        if not r:
            return {"code": 4040, "msg": "植物不存在", "data": None}
        conn.execute("UPDATE plant_profile SET name=COALESCE(?,name), pot_material=COALESCE(?,pot_material),"
                     " emotion_tag=COALESCE(?,emotion_tag) WHERE id=?",
                     (body.name, body.potMaterial, body.emotionTag, plant_id))
        conn.commit()
        return {"code": 0, "msg": "ok", "data": {"id": plant_id}}
    finally:
        conn.close()


@router.post("/{plant_id}/photo")
async def upload_photo(plant_id: int, image: UploadFile = File(...),
                       authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    # 真实实现：保存到本地/OSS，返回可访问 URL。开发期存本地 uploads/ 目录。
    content = await image.read()
    import os
    uploads = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
    os.makedirs(uploads, exist_ok=True)
    fname = f"plant_{plant_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
    with open(os.path.join(uploads, fname), "wb") as f:
        f.write(content)
    conn = get_conn()
    try:
        conn.execute("UPDATE plant_profile SET photo_url=? WHERE id=?", (f"/uploads/{fname}", plant_id))
        conn.commit()
        return {"code": 0, "msg": "ok", "data": {"photoUrl": f"/uploads/{fname}"}}
    finally:
        conn.close()


@router.delete("/{plant_id}")
def archive_plant(plant_id: int, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        conn.execute("UPDATE plant_profile SET archived=1 WHERE id=?", (plant_id,))
        conn.commit()
        return {"code": 0, "msg": "ok", "data": {"id": plant_id}}
    finally:
        conn.close()


# ---------- 养护记录 ----------

@router.post("/{plant_id}/care-records")
def add_record(plant_id: int, body: CareRecordIn, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO care_record (plant_id, user_id, type, amount, note) VALUES (?,?,?,?,?)",
            (plant_id, uid, body.type, body.amount, body.note))
        conn.commit()
        return {"code": 0, "msg": "ok", "data": {"careRecordId": cur.lastrowid,
                                                 "opTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}}
    finally:
        conn.close()


@router.post("/{plant_id}/watering")
def one_key_watering(plant_id: int, body: WateringIn, authorization: str = Header(default="")):
    """一键浇水：默认记录当前时间为本次浇水时间"""
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    now = datetime.now()
    conn = get_conn()
    try:
        r = conn.execute("SELECT water_interval_days FROM plant_profile WHERE id=?", (plant_id,)).fetchone()
        if not r:
            return {"code": 4040, "msg": "植物不存在", "data": None}
        cur = conn.execute(
            "INSERT INTO care_record (plant_id, user_id, type, amount, note) VALUES (?,?,?,?,?)",
            (plant_id, uid, "water", None, body.note or "一键浇水"))
        conn.execute("UPDATE plant_profile SET last_water_at=?, status='ok' WHERE id=?", (now.strftime("%Y-%m-%d %H:%M:%S"), plant_id))
        conn.commit()
        next_due = (now + timedelta(days=r["water_interval_days"])).strftime("%Y-%m-%d")
        return {"code": 0, "msg": "ok",
                "data": {"careRecordId": cur.lastrowid,
                         "opTime": now.strftime("%Y-%m-%d %H:%M:%S"),
                         "nextDueDate": next_due}}
    finally:
        conn.close()


@router.get("/{plant_id}/timeline")
def timeline(plant_id: int, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM care_record WHERE plant_id=? ORDER BY created_at DESC LIMIT 100",
            (plant_id,)).fetchall()
        TYPE_LABEL = {"water": "浇水", "fertilize": "施肥", "prune": "修剪", "repot": "换盆",
                      "loosen": "松土", "medicate": "喷药", "clean": "擦叶"}
        data = [{"id": r["id"], "type": r["type"], "text": (TYPE_LABEL.get(r["type"], r["type"]) + (f" {r['amount']}" if r["amount"] else "")),
                 "note": r["note"], "member": "我", "time": r["created_at"]} for r in rows]
        return {"code": 0, "msg": "ok", "data": data}
    finally:
        conn.close()


@router.get("/{plant_id}/stats")
def stats(plant_id: int, authorization: str = Header(default="")):
    """浇水频率 + 株高变化（开发期从记录聚合，数据为空时返回示例结构）"""
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        # 近30天浇水次数按天
        rows = conn.execute(
            "SELECT date(created_at) d, COUNT(*) c FROM care_record WHERE plant_id=? AND type='water'"
            " AND created_at >= datetime('now','-30 days') GROUP BY d", (plant_id,)).fetchall()
        growth = conn.execute(
            "SELECT height_cm, measured_at FROM growth_metric WHERE plant_id=? ORDER BY measured_at",
            (plant_id,)).fetchall()
        return {"code": 0, "msg": "ok",
                "data": {"waterByDay": [{"date": r["d"], "count": r["c"]} for r in rows],
                         "heightTrend": [{"heightCm": g["height_cm"], "measuredAt": g["measured_at"]} for g in growth]}}
    finally:
        conn.close()


@router.post("/{plant_id}/growth")
def add_growth(plant_id: int, body: GrowthIn, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        conn.execute("INSERT INTO growth_metric (plant_id, height_cm) VALUES (?,?)", (plant_id, body.heightCm))
        conn.execute("UPDATE plant_profile SET height_cm=? WHERE id=?", (body.heightCm, plant_id))
        conn.commit()
        return {"code": 0, "msg": "ok", "data": {"id": 1, "measuredAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}}
    finally:
        conn.close()
