"""routers/family.py —— 家庭组 / 成员 / 任务"""
from fastapi import APIRouter, Header
from ..db import get_conn
from ..auth import current_user_id
from ..schemas import FamilyCreateIn, MemberAddIn, TaskAssignIn

router = APIRouter(prefix="/family", tags=["家庭协作"])


@router.post("")
def create_family(body: FamilyCreateIn, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        cur = conn.execute("INSERT INTO family_groups (name, owner_id, invite_code) VALUES (?,?,?)",
                           (body.name, uid, "invite_" + str(uid)))
        fid = cur.lastrowid
        conn.execute("INSERT INTO family_members (family_id, user_id, role) VALUES (?,?,?)", (fid, uid, "owner"))
        conn.execute("UPDATE users SET family_id=?, role='owner' WHERE id=?", (fid, uid))
        conn.commit()
        return {"code": 0, "msg": "ok", "data": {"familyId": fid, "inviteCode": "invite_" + str(uid)}}
    finally:
        conn.close()


@router.post("/{fid}/invite")
def invite(fid: int, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM family_groups WHERE id=?", (fid,)).fetchone()
        if not row:
            return {"code": 4040, "msg": "家庭组不存在", "data": None}
        code = row["invite_code"] or ("invite_" + str(fid))
        return {"code": 0, "msg": "ok", "data": {"inviteCode": code}}
    finally:
        conn.close()


@router.post("/{fid}/members")
def add_member(fid: int, body: MemberAddIn, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        conn.execute("INSERT INTO family_members (family_id, user_id, role, duty) VALUES (?,?,?,?)",
                     (fid, body.userId, body.role, body.duty))
        conn.execute("UPDATE users SET family_id=?, role=? WHERE id=?", (fid, body.role, body.userId))
        conn.commit()
        return {"code": 0, "msg": "ok", "data": {"userId": body.userId}}
    finally:
        conn.close()


@router.get("/{fid}/members")
def member_list(fid: int, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT fm.id, fm.role, fm.duty, u.nickname FROM family_members fm "
            "JOIN users u ON u.id=fm.user_id WHERE fm.family_id=? ORDER BY fm.id", (fid,)).fetchall()
        return {"code": 0, "msg": "ok",
                "data": [{"id": r["id"], "name": r["nickname"], "role": r["role"], "duty": r["duty"]} for r in rows]}
    finally:
        conn.close()


@router.post("/{fid}/tasks")
def assign_task(fid: int, body: TaskAssignIn, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO family_task (family_id, plant_id, title, assignee_id, due) VALUES (?,?,?,?,?)",
            (fid, body.plantId, body.title, body.assigneeId, body.due))
        conn.commit()
        return {"code": 0, "msg": "ok", "data": {"taskId": cur.lastrowid}}
    finally:
        conn.close()


@router.get("/{fid}/tasks")
def task_list(fid: int, status: str = "all", authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        sql = "SELECT t.*, u.nickname, p.name AS plant_name FROM family_task t " \
              "LEFT JOIN users u ON u.id=t.assignee_id LEFT JOIN plant_profile p ON p.id=t.plant_id " \
              "WHERE t.family_id=? "
        args = [fid]
        if status == "todo":
            sql += "AND t.done=0 "
        sql += "ORDER BY t.id DESC"
        rows = conn.execute(sql, args).fetchall()
        return {"code": 0, "msg": "ok",
                "data": [{"id": r["id"], "title": r["title"], "plant": r["plant_name"],
                          "assignee": r["nickname"], "due": r["due"], "done": bool(r["done"])} for r in rows]}
    finally:
        conn.close()


@router.patch("/tasks/{task_id}/done")
def task_done(task_id: int, authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录", "data": None}
    conn = get_conn()
    try:
        conn.execute("UPDATE family_task SET done = 1 - done WHERE id=?", (task_id,))
        conn.commit()
        return {"code": 0, "msg": "ok", "data": {"taskId": task_id}}
    finally:
        conn.close()
