# 绿植智能养护系统 · 后端（FastAPI + SQLite）

> 与同目录中的前端小程序（mock 模式）配套。接口对齐 `docs/API接口文档.md`。

## 目录结构

```
backend/
├── main.py                  # 入口：uvicorn main:app --reload --port 8000
├── requirements.txt         # 依赖
├── app/
│   ├── db.py                # SQLite 建表 + 知识库种子（12 张表）
│   ├── auth.py              # 简易 token 登录（生产可换 JWT/bcrypt）
│   ├── mock_ai.py           # 识别/诊断占位推理（换真实模型只改这里）
│   ├── schemas.py           # Pydantic 请求体
│   └── routers/
│       ├── auth.py          # /auth/* 注册/登录/微信登录
│       ├── plants.py        # /plants/* 档案+养护+时光轴+统计
│       ├── diagnosis.py     # /species/recognize、/diagnosis
│       ├── knowledge.py     # 知识库/养护计划/通知
│       ├── family.py        # 家庭组/成员/任务
│       └── export.py        # 数据导出
└── greenplant.db            # 首次运行自动生成
```

## 启动（Mac 终端 / IDEA 终端）

```bash
cd Plant/zhinengPlant/backend
python3 -m venv venv                 # 首次：建虚拟环境（可选但推荐）
source venv/bin/activate
pip install -r requirements.txt      # 首次：装依赖
uvicorn main:app --reload --port 8000
```

启动后浏览器打开 **http://127.0.0.1:8000/docs**，能看到全部接口并直接点「Try it out」调试。

## IDEA（Ultimate）打开方式

1. 打开 IDEA → `File > Open` → 选择 `Plant/zhinengPlant/backend` 目录
2. 项目 SDK 选本机 Python（`Settings > Project > Python Interpreter`）
3. 右上角 Run 配置加一个 **FastAPI/uvicorn** 运行项：`module=uvicorn`，参数 `main:app --reload --port 8000`
4. 直接点运行，或终端执行上面的 uvicorn 命令

## 快速联调流程（30 秒跑通）

```bash
curl http://127.0.0.1:8000/api/health                      # 健康检查
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"phone":"13800000000","password":"123456"}'          # 未注册会 4010
curl -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"phone":"13800000000","password":"123456","nickname":"绿植主人"}'
# 拿到 token 后带 Authorization: Bearer <token> 调 /api/plants 等
```

## 前端对接

1. `utils/request.js` 里 `MOCK = false`
2. `app.js` 的 `baseUrl` 改为 `http://127.0.0.1:8000/api`
3. 微信开发者工具 → 详情 → 本地设置 → 勾选「不校验合法域名」（本机 http 联调用）

## 常见问题

| 现象 | 解决 |
| --- | --- |
| `ModuleNotFoundError: fastapi` | `pip install -r requirements.txt` 没装 |
| 端口被占用 | 换 `--port 8001`，前端 baseUrl 同步改 |
| 想换 MySQL | 把 `app/db.py` 的 sqlite3 调用换成 pymysql（表结构已按 MySQL 语义设计），或装 SQLAlchemy |

## 待办（接真实能力）

- [ ] 品种识别模型：Colab 训练 → `models/` → 改 `mock_ai.recognize()`
- [ ] 健康诊断模型：同上，改 `mock_ai.diagnose()`
- [ ] 微信登录：`/auth/wechat` 接 code2session（需 AppID + Secret）
- [ ] 导出：reportlab（PDF）/ openpyxl（Excel）生成真实文件
- [ ] 上传：照片存 OSS/MinIO + 签名 URL（当前存本地 uploads/）
- [ ] token 换 pyjwt、密码哈希换 bcrypt（当前为课设演示版）
