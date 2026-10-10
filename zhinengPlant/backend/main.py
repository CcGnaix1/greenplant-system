"""
main.py —— FastAPI 应用入口
启动：uvicorn main:app --reload --port 8000
调试：浏览器打开 http://127.0.0.1:8000/docs （FastAPI 自带 Swagger，可逐个调接口）
统一响应：{code, msg, data}，code=0 成功；错误码 4001/4010/4030/4040/5000/6001
"""
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import auth, plants, diagnosis, knowledge, family, export

app = FastAPI(
    title="绿植智能养护系统 API",
    description="基于图像识别的绿植智能养护系统 · 后端接口（对齐接口文档 v1）",
    version="0.1.0",
)

# 上传文件静态目录（照片/封面）
UPLOADS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOADS, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")

# 统一响应包装（错误码统一在路由层返回，这里保留兜底 5000）
@app.exception_handler(Exception)
async def unhandled_exception(request, exc):
    return {"code": 5000, "msg": "服务器异常：%s" % exc, "data": None}


@app.get("/api/health")
def health():
    return {"code": 0, "msg": "ok", "data": {"status": "running", "time": "2026"}}

# 挂载各模块路由（统一前缀 /api）
app.include_router(auth.router, prefix="/api")
app.include_router(plants.router, prefix="/api")
app.include_router(diagnosis.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(family.router, prefix="/api")
app.include_router(export.router, prefix="/api")
