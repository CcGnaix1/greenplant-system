#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AI_ROOT="$PROJECT_ROOT/Plant-AI"
VENV_DIR="$AI_ROOT/.venv"
# 必须与 Java 端 app.upload-dir 保持一致：识别时 Java 先把图片落盘到这里，
# Python 侧只接受该目录下的 image_path。绝不能指向小程序项目目录内部
# （否则微信开发者工具会因文件变化重新编译，小程序重启回到首页）。
UPLOAD_ROOT="${UPLOAD_DIR:-$PROJECT_ROOT/uploads}"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "首次运行：正在创建本地 AI 环境……"
  python3 -m venv "$VENV_DIR"
fi

if ! "$VENV_DIR/bin/python" -c "import fastapi, uvicorn, onnxruntime, albumentations" >/dev/null 2>&1; then
  echo "正在安装本地 AI 依赖……"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$VENV_DIR/bin/python" -m pip install -r "$AI_ROOT/service/requirements.txt"
fi

export PLANT_UPLOAD_ROOT="$UPLOAD_ROOT"
export NO_ALBUMENTATIONS_UPDATE=1

cd "$AI_ROOT/service"
echo "本地 AI 正在启动：http://127.0.0.1:5001"
echo "保持此窗口运行；按 Ctrl+C 停止。"
exec "$VENV_DIR/bin/python" -m uvicorn main:app --host 127.0.0.1 --port 5001
