#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="$ROOT/.run"

for service in ai java; do
  PID_FILE="$RUN_DIR/$service.pid"
  if [ -f "$PID_FILE" ]; then
    PID="$(cat "$PID_FILE")"
    if kill -0 "$PID" 2>/dev/null; then
      kill "$PID"
      echo "已停止 $service 服务。"
    fi
    rm -f "$PID_FILE"
  fi
done
