"""
auth.py —— 简易登录态
开发期：登录成功后生成随机 token，保存在内存 dict（服务重启即失效，够课设演示）。
生产建议：换 pyjwt 签发 JWT；密码哈希建议换 bcrypt（当前用 pbkdf2 标准库，非明文）。
"""
import hashlib
import os
import uuid

# token -> user_id（内存态；如需跨重启持久化可挪到 SQLite）
TOKENS = {}


def hash_password(pwd: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", pwd.encode(), bytes.fromhex(salt), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(pwd: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pwd.encode(), bytes.fromhex(salt), 100_000).hex()
        return calc == digest
    except Exception:
        return False


def create_token(user_id: int) -> str:
    token = uuid.uuid4().hex
    TOKENS[token] = user_id
    return token


def resolve_user(token: str):
    """返回 user_id 或 None"""
    return TOKENS.get(token)


def current_user_id(authorization: str = "") -> int:
    """从 Authorization: Bearer <token> 解析当前用户 id；无 token 返回 0"""
    if not authorization.startswith("Bearer "):
        return 0
    token = authorization[7:].strip()
    uid = resolve_user(token)
    return uid or 0
