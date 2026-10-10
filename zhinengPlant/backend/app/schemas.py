"""
schemas.py —— Pydantic 请求体模型（统一响应在 main.py 中定义）
"""
from pydantic import BaseModel
from typing import Optional


# ---- 认证 ----
class RegisterIn(BaseModel):
    phone: str
    password: str
    nickname: str


class LoginIn(BaseModel):
    phone: str
    password: str


class WechatLoginIn(BaseModel):
    code: str


# ---- 家庭 ----
class FamilyCreateIn(BaseModel):
    name: str


class MemberAddIn(BaseModel):
    userId: int
    role: str = "member"
    duty: str = ""


class TaskAssignIn(BaseModel):
    plantId: int
    title: str
    assigneeId: int
    due: str = "今天"


# ---- 植物档案 ----
class PlantCreateIn(BaseModel):
    name: str
    speciesId: int
    purchaseDate: Optional[str] = None
    potMaterial: Optional[str] = None
    initHeightCm: Optional[float] = None
    emotionTag: Optional[str] = None
    photoUrl: Optional[str] = None


class PlantUpdateIn(BaseModel):
    name: Optional[str] = None
    potMaterial: Optional[str] = None
    emotionTag: Optional[str] = None


# ---- 养护记录 ----
class CareRecordIn(BaseModel):
    type: str = "water"   # water/fertilize/prune/repot/loosen/medicate/clean
    amount: Optional[str] = None
    note: Optional[str] = None


class WateringIn(BaseModel):
    note: Optional[str] = None


class GrowthIn(BaseModel):
    heightCm: float


# ---- 诊断 ----
class DiagnosisFeedbackIn(BaseModel):
    helpful: Optional[bool] = True
    note: Optional[str] = None
