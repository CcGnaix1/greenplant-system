"""routers/auth.py —— 注册 / 登录 / 微信登录 / 家庭成员"""
import json
from fastapi import APIRouter, Header
from pydantic import BaseModel
from ..db import get_conn
from ..auth import hash_password, verify_password, create_token, current_user_id
from ..schemas import RegisterIn, LoginIn, WechatLoginIn

router = APIRouter(prefix="/auth", tags=["认证"])


def _public_user(row) -> dict:
    return {"id": row["id"], "nickname": row["nickname"], "familyId": row["family_id"], "role": row["role"]}


@router.post("/register")
def register(body: RegisterIn):
    if not body.phone or len(body.password) < 6:
        return {"code": 4001, "msg": "手机号或密码不合法（密码至少6位）", "data": None}
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO users (phone, password_hash, nickname) VALUES (?,?,?)",
            (body.phone, hash_password(body.password), body.nickname))
        conn.commit()
        uid = cur.lastrowid
        token = create_token(uid)
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return {"code": 0, "msg": "ok", "data": {"token": token, "user": _public_user(row)}}
    except Exception:
        return {"code": 4001, "msg": "手机号已注册", "data": None}
    finally:
        conn.close()


@router.post("/login")
def login(body: LoginIn):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE phone=?", (body.phone,)).fetchone()
        if not row or not verify_password(body.password, row["password_hash"]):
            return {"code": 4010, "msg": "账号或密码错误", "data": None}
        token = create_token(row["id"])
        return {"code": 0, "msg": "ok", "data": {"token": token, "user": _public_user(row)}}
    finally:
        conn.close()


@router.post("/wechat")
def wechat_login(body: WechatLoginIn):
    """
    微信登录：小程序 wx.login 拿到 code 后调用。
    真实实现：用 appid+secret+code 调微信 code2session 换 openid，
    再按 openid 查/建用户并签发 token。当前为开发期占位：任意 code 直接建游客用户。
    """
    conn = get_conn()
    try:
        openid = "mock_openid_" + body.code[:16]
        row = conn.execute("SELECT * FROM users WHERE openid=?", (openid,)).fetchone()
        if not row:
            cur = conn.execute(
                "INSERT INTO users (openid, nickname, role) VALUES (?,?,?)",
                (openid, "绿植主人", "owner"))
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
        token = create_token(row["id"])
        return {"code": 0, "msg": "ok", "data": {"token": token, "user": _public_user(row), "isNew": False}}
    finally:
        conn.close()


@router.get("/me")
def me(authorization: str = Header(default="")):
    uid = current_user_id(authorization)
    if not uid:
        return {"code": 4010, "msg": "未登录或token失效", "data": None}
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return {"code": 0, "msg": "ok", "data": _public_user(row)}
    finally:
        conn.close()
