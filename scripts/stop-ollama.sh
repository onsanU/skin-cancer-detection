#!/usr/bin/env bash
# 精确关闭 Ollama（避免 pkill -f 匹配到自身命令行导致自杀）
set -uo pipefail

PIDS=$(pgrep -x ollama || true)
if [[ -z "$PIDS" ]]; then
  echo "✔ Ollama 未在运行"
else
  echo "找到 ollama 进程: $PIDS"
  for p in $PIDS; do
    kill "$p" 2>/dev/null && echo "  已发送 TERM → pid=$p"
  done
  for _ in $(seq 1 20); do
    pgrep -x ollama >/dev/null || break
    sleep 0.5
  done
  REMAIN=$(pgrep -x ollama || true)
  if [[ -n "$REMAIN" ]]; then
    for p in $REMAIN; do kill -9 "$p" 2>/dev/null && echo "  已强制结束 → pid=$p"; done
    sleep 1
  fi
fi

echo
echo "=== 最终复查 ==="
if pgrep -x ollama >/dev/null; then
  echo "✘ 仍有 ollama 进程: $(pgrep -ax ollama | tr '\n' ' ')"
else
  echo "✔ Ollama 已完全退出"
fi
PORTS=$(ss -ltn 2>/dev/null | awk '{print $4}' | grep -E ':(8000|11434)$' || true)
if [[ -z "$PORTS" ]]; then
  echo "✔ 端口 8000 / 11434 均已释放"
else
  echo "✘ 仍有端口占用: $PORTS"
fi
echo
echo "=== GPU 占用复查（应无 ollama 相关进程）==="
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv 2>/dev/null || echo "（nvidia-smi 不可用，跳过）"
