#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT/.logs"
RUN_DIR="$ROOT/.run"
mkdir -p "$LOG_DIR" "$RUN_DIR"

# 【配置入口】把 .env.example 复制为 .env 后填写；.env 不应发给其他人。
if [ -f "$ROOT/.env" ]; then
  set -a
  . "$ROOT/.env"
  set +a
fi

if [ -f "$RUN_DIR/ai.pid" ] && kill -0 "$(cat "$RUN_DIR/ai.pid")" 2>/dev/null; then
  echo "AI 服务已经运行。"
else
  nohup "$ROOT/zhinengPlant/run-local-ai.sh" >"$LOG_DIR/ai.log" 2>&1 &
  echo $! >"$RUN_DIR/ai.pid"
  echo "AI 服务正在启动：http://127.0.0.1:5001"
fi

if [ -f "$RUN_DIR/java.pid" ] && kill -0 "$(cat "$RUN_DIR/java.pid")" 2>/dev/null; then
  echo "Java 服务已经运行。"
else
  # 先切换目录再启动，确保记录的是 Maven 进程 PID；stdin 重定向后退出终端也不会连带停止后端。
  pushd "$ROOT/zhinengPlant/backend-java" >/dev/null
  nohup mvn spring-boot:run </dev/null >"$LOG_DIR/java.log" 2>&1 &
  JAVA_PID=$!
  popd >/dev/null
  echo "$JAVA_PID" >"$RUN_DIR/java.pid"
  echo "Java 服务正在启动：http://127.0.0.1:8081/api"
fi

echo "日志目录：$LOG_DIR"
