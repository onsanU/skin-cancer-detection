#!/usr/bin/env bash
# ============================================================
#  皮肤癌图像检测系统 — 停止脚本 (stop.sh)
#  用法：bash stop.sh
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/logs/skin_backend.pid"
PORT="${1:-8000}"

G="\033[32m"; Y="\033[33m"; R="\033[31m"; N="\033[0m"
STOPPED=0

# 1. 按 pid 文件
if [[ -f "$PID_FILE" ]]; then
  PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null && echo -e "${G}✔${N} 已停止 pid=$PID (来自 pid 文件)"
    STOPPED=1
    for _ in $(seq 1 20); do sleep 0.5; kill -0 "$PID" 2>/dev/null || break; done
    kill -0 "$PID" 2>/dev/null && { kill -9 "$PID" 2>/dev/null; echo -e "${Y}!${N} 已强制结束 pid=$PID"; }
  fi
  rm -f "$PID_FILE"
fi

# 2. 按端口兜底（找本项目 uvicorn）
PORT_PIDS=$(ss -ltnp 2>/dev/null | grep ":$PORT " | grep -oP 'pid=\K[0-9]+' | sort -u)
for P in $PORT_PIDS; do
  if grep -qa "uvicorn" /proc/"$P"/cmdline 2>/dev/null; then
    kill "$P" 2>/dev/null && echo -e "${G}✔${N} 已停止端口 $PORT 上的服务 pid=$P"
    STOPPED=1
  else
    echo -e "${Y}!${N} 端口 $PORT 被非本项目进程占用 (pid=$P)，未处理"
  fi
done

# 3. 清理可能残留的 uvicorn 主进程
LEFTOVER=$(pgrep -f "uvicorn app.main:app" 2>/dev/null || true)
if [[ -n "$LEFTOVER" ]]; then
  echo -e "${Y}!${N} 残留进程：$LEFTOVER → 结束"
  pkill -f "uvicorn app.main:app" 2>/dev/null
  sleep 1
  STOPPED=1
fi

if [[ $STOPPED -eq 0 ]]; then
  echo "没有运行中的服务（端口 $PORT 空闲）"
else
  echo "服务已停止。日志保留在：$SCRIPT_DIR/logs/backend.log"
fi
