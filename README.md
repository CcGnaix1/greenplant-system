# 绿植智能养护系统

本目录已经包含项目运行所需的三部分：

- `zhinengPlant/`：微信小程序前端与 Java Spring Boot 后端
- `zhinengPlant/backend-java/`：正式 Java 后端
- `Plant-AI/`：本地植物品种识别与健康诊断模型

## 运行环境

- MySQL 8，数据库名 `greenplant`
- Java 17+ 与 Maven
- Python 3.9+（AI 依赖见 `Plant-AI/service/requirements.txt`）
- 微信开发者工具

## 启动

第一次运行先创建个人配置：

```bash
cp .env.example .env
```

打开 `.env`，所有标有“必须修改”的项目都需要按接收方电脑填写。然后执行：

```bash
./start-all.sh
```

### Windows 一键启动

1. 安装 JDK 17+、Maven、MySQL 8 和 Python 3.9+，并加入系统 PATH。
2. 双击 `start-all.bat`。首次运行会自动复制 `.env.example` 为 `.env`。
3. 按提示填写 `.env` 后，再次双击 `start-all.bat`。
4. 脚本会自动创建 Windows 专用的 `.venv-win`、安装 AI 依赖，并启动 AI 和 Java 服务。

停止服务时双击 `stop-all.bat`。

注意：项目附带的 `Plant-AI/.venv` 是 macOS 环境，Windows 脚本不会使用它。

服务地址：

- Java API：`http://127.0.0.1:8081/api`
- 本地 AI：`http://127.0.0.1:5001`

然后用微信开发者工具导入 `zhinengPlant`。真机调试时，需要把
`zhinengPlant/app.js` 中的 `baseUrl` 改为运行 Java 后端电脑的局域网 IP。

停止服务：

```bash
./stop-all.sh
```

## 说明

主要配置位置：

- `.env`：MySQL、微信密钥、JWT 和 AI 服务地址
- `zhinengPlant/app.js` 顶部的 `BACKEND_BASE_URL`：小程序访问 Java 后端的地址
- `zhinengPlant/project.config.json` 的 `appid`：微信开发者工具使用的小程序 AppID
- `zhinengPlant/backend-java/src/main/resources/application.yml`：后端端口及高级配置

不要把个人 `.env` 文件发给其他人，应当只分享 `.env.example`。
