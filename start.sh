#!/usr/bin/env bash
# ============================================================
#  皮肤癌图像检测系统 — 一键启动脚本 (start.sh)
# ------------------------------------------------------------
#  用法：
#    bash start.sh              启动服务（自动检查环境/端口/模型）
#    bash start.sh --reload     开发模式（代码改动自动重载）
#    bash start.sh --port 8080  指定端口
#    bash start.sh --no-check   跳过模型文件预检（更快）
#    bash start.sh --bg         后台运行（关终端不退出）
#    bash start.sh --no-ollama  跳过 Ollama 检查（不启医疗问答）
#    bash start.sh --mysql      用 MySQL 数据库（默认 SQLite）
#    bash start.sh --sqlite     用 SQLite 数据库（默认）
#
#  说明：脚本会自动检查/启动 Ollama（医疗问答用的 qwen3.5-med3 与
#        qwen2.5vl 模型）。未安装 Ollama 时仅警告，检测功能不受影响。
#
#        第 8 步会自动拉起 Cloudflare 公网隧道（复用医小喵那条隧道），
#        公网地址 https://skin.osanu.dpdns.org/app/  。可用环境变量
#        SKIN_CF_TOKEN=<token文件路径> 指定其它隧道凭据；文件不存在时跳过。
#
#  停止：bash stop.sh
# ============================================================
set -uo pipefail

# ---------- 路径 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ_DIR="$SCRIPT_DIR"
BACKEND_DIR="$PROJ_DIR/backend"
FRONTEND_DIR="$PROJ_DIR/frontend"
LOG_DIR="$PROJ_DIR/logs"
PID_FILE="$LOG_DIR/skin_backend.pid"
LOG_FILE="$LOG_DIR/backend.log"

# ---------- 默认参数 ----------
PORT=8000
HOST=0.0.0.0
RELOAD=""
BACKGROUND=0
CHECK=1
VENV_PY="${SKIN_VENV_PY:-$HOME/shixun-venv/bin/python}"
DB_BACKEND="${SKIN_DB_BACKEND:-sqlite}"   # sqlite（默认）/ mysql
CHECK_OLLAMA=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)      PORT="$2"; shift 2 ;;
    --host)      HOST="$2"; shift 2 ;;
    --reload)    RELOAD="--reload"; shift ;;
    --no-check)  CHECK=0; shift ;;
    --no-ollama) CHECK_OLLAMA=0; shift ;;
    --bg)        BACKGROUND=1; shift ;;
    --mysql)     DB_BACKEND="mysql"; shift ;;
    --sqlite)    DB_BACKEND="sqlite"; shift ;;
    -h|--help)   sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "[警告] 未知参数：$1（忽略）"; shift ;;
  esac
done

# ---------- 颜色 ----------
if [[ -t 1 ]]; then
  G="\033[32m"; Y="\033[33m"; R="\033[31m"; B="\033[36m"; N="\033[0m"; BOLD="\033[1m"
else
  G=""; Y=""; R=""; B=""; N=""; BOLD=""
fi
ok()   { echo -e "  ${G}✔${N} $1"; }
warn() { echo -e "  ${Y}!${N} $1"; }
bad()  { echo -e "  ${R}✘${N} $1"; }
hdr()  { echo -e "\n${BOLD}${B}[$1]${N} $2"; }

echo -e "${BOLD}${B}"
echo "  ============================================================"
echo "   皮肤癌图像检测系统 — 启动中"
echo "  ============================================================"
echo -e "${N}"

# ---------- 1. 项目结构 ----------
hdr 1/8 "检查项目结构"
for d in backend frontend; do
  if [[ -d "$PROJ_DIR/$d" ]]; then ok "$d/ 存在"; else bad "$d/ 缺失 — 请确认在项目根目录运行"; exit 1; fi
done

# ---------- 2. Python 环境 ----------
hdr 2/8 "检查 Python 环境"
if [[ ! -x "$VENV_PY" ]]; then
  warn "未找到 venv：$VENV_PY"
  echo "     可用环境变量指定：SKIN_VENV_PY=/path/to/python bash start.sh"
  echo -n "     尝试回退到系统 python3 … "
  if command -v python3 >/dev/null 2>&1; then VENV_PY="$(command -v python3)"; echo "使用 $VENV_PY"; else bad "系统也没有 python3"; exit 1; fi
else
  ok "venv: $VENV_PY"
fi

"$VENV_PY" - <<'PYEOF'
import sys
mods = [("torch", None), ("fastapi", None), ("uvicorn", None), ("PIL", "Pillow"), ("sqlite3", None)]
missing = []
info = []
for mod, pkg in mods:
    try:
        m = __import__(mod)
        v = getattr(m, "__version__", "")
        info.append(f"{mod}{' ' + v if v else ''}")
    except Exception:
        missing.append(pkg or mod)
if missing:
    print("  \033[31m✘\033[0m 缺少依赖: " + ", ".join(missing))
    sys.exit(2)
print("  \033[32m✔\033[0m 核心依赖: " + " | ".join(info))
try:
    import torch
    if torch.cuda.is_available():
        print(f"  \033[32m✔\033[0m GPU: {torch.cuda.get_device_name(0)} (CUDA {torch.version.cuda})")
    else:
        print("  \033[33m!\033[0m 未检测到 CUDA，将用 CPU 推理（较慢）")
except Exception:
    pass
PYEOF
if [[ $? -eq 2 ]]; then
  echo "     安装：$VENV_PY -m pip install fastapi uvicorn pillow python-multipart email-validator"
  exit 1
fi

# ---------- 3. 端口 ----------
hdr 3/8 "检查端口 $PORT"
is_port_busy() { ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$PORT\$"; }
if is_port_busy; then
  OLD_PID=$(ss -ltnp 2>/dev/null | grep ":$PORT " | grep -oP 'pid=\K[0-9]+' | head -1)
  warn "端口 $PORT 已被占用 (pid=${OLD_PID:-未知})"
  if [[ -n "${OLD_PID:-}" ]] && grep -qa "uvicorn" /proc/"$OLD_PID"/cmdline 2>/dev/null; then
    echo -n "     这是本项目的旧服务，自动停止并重启 … "
    kill "$OLD_PID" 2>/dev/null
    for _ in $(seq 1 20); do sleep 0.5; is_port_busy || break; done
    if is_port_busy; then kill -9 "$OLD_PID" 2>/dev/null; sleep 1; fi
    if is_port_busy; then bad "停止失败，请手动处理"; exit 1; else echo -e "${G}已释放${N}"; fi
  else
    bad "占用进程不是本项目服务，请先手动处理，或用 --port 换端口"
    echo "     查看占用： ss -ltnp | grep $PORT"
    exit 1
  fi
else
  ok "端口 $PORT 空闲"
fi

# ---------- 4. 模型文件 ----------
if [[ $CHECK -eq 1 ]]; then
  hdr 4/8 "预检模型文件"
  MISSING_MODEL=0
  for rel in "models_v2_full/best.pt" "models_compressed/model_int8.onnx" \
             "models_compressed_7class/model_int8.onnx"; do
    if [[ -f "$PROJ_DIR/$rel" ]]; then
      ok "$rel ($(du -h "$PROJ_DIR/$rel" | cut -f1))"
    else
      warn "缺失 $rel — 会由其它候选回退（不影响启动）"
      MISSING_MODEL=1
    fi
  done
  if [[ $MISSING_MODEL -eq 1 ]]; then
    warn "有可选模型缺失，服务仍可启动（config.py 的候选列表会自动回退）"
  fi
else
  hdr 4/6 "预检模型文件"
  warn "已按 --no-check 跳过"
fi

# ---------- 5. 前端产物 ----------
hdr 5/8 "检查前端构建产物"
DIST_DIR=""
for cand in "$BACKEND_DIR/frontend/dist" "$FRONTEND_DIR/dist"; do
  [[ -f "$cand/index.html" ]] && DIST_DIR="$cand" && break
done
if [[ -n "$DIST_DIR" ]]; then
  ok "dist 就绪：${DIST_DIR#$PROJ_DIR/}（后端自动挂载到 /app/）"
else
  warn "未找到前端 dist，/app/ 页面将 404"
  echo "     构建命令：cd frontend && npm install && npm run build"
fi
if [[ -d "$BACKEND_DIR/static/admin" ]]; then
  ok "管理后台静态页就绪（/admin/）"
else
  warn "backend/static/admin 缺失，/admin/ 将 404"
fi

# ---------- 6. Ollama（医疗问答依赖）----------
if [[ $CHECK_OLLAMA -eq 0 ]]; then
  hdr 6/8 "医疗问答模型（已跳过）"
  echo "  --no-ollama 已指定，不检查 Ollama；问答页会提示模型未就绪"
else
hdr 6/8 "检查医疗问答模型（Ollama）"
OLLAMA_URL="http://127.0.0.1:11434"
OLLAMA_BIN="$(command -v ollama || true)"
OLLAMA_STARTED=0

if [[ -z "$OLLAMA_BIN" ]]; then
  warn "未安装 ollama，医疗问答功能不可用（其余功能不受影响）"
  echo "     安装：curl -fsSL https://ollama.com/install.sh | sh"
elif curl -s -m 2 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  ok "Ollama 已在运行（$OLLAMA_URL）"
else
  echo "  Ollama 未运行，正在后台启动..."
  mkdir -p "$LOG_DIR"
  nohup "$OLLAMA_BIN" serve > "$LOG_DIR/ollama.log" 2>&1 &
  OLLAMA_STARTED=$!
  # 等待就绪（最多 15 秒）
  for i in $(seq 1 15); do
    if curl -s -m 2 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then break; fi
    sleep 1
  done
  if curl -s -m 2 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
    ok "Ollama 已启动 (pid=$OLLAMA_STARTED，日志 logs/ollama.log)"
  else
    warn "Ollama 启动超时，医疗问答可能不可用"
  fi
fi

# 检查问答所需模型是否已拉取
if curl -s -m 3 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  MODELS_JSON="$(curl -s -m 3 "$OLLAMA_URL/api/tags" || echo '{}')"
  for m in "qwen3.5:4b-med3" "qwen2.5vl:3b"; do
    if echo "$MODELS_JSON" | grep -q "${m%%:*}"; then
      ok "问答模型就绪：$m"
    else
      warn "缺少问答模型：$m（可执行 ollama pull $m 拉取）"
    fi
  done
fi
fi

# ---------- 7. 启动 ----------
hdr 7/8 "启动服务"
mkdir -p "$LOG_DIR" "$BACKEND_DIR/uploads"
ALLOWED_ORIGINS="http://127.0.0.1:$PORT,http://localhost:$PORT"

# 清理过期 pid
[[ -f "$PID_FILE" ]] && { OLDPID=$(cat "$PID_FILE"); kill -0 "$OLDPID" 2>/dev/null || rm -f "$PID_FILE"; }

cd "$BACKEND_DIR" || exit 1
export SKIN_DB_BACKEND="$DB_BACKEND"
START_CMD=("$VENV_PY" -m uvicorn app.main:app --host "$HOST" --port "$PORT")
[[ -n "$RELOAD" ]] && START_CMD+=("$RELOAD")

echo "  数据库： $DB_BACKEND"
echo "  命令： ${START_CMD[*]}"
echo "  日志： $LOG_FILE"
echo

if [[ $BACKGROUND -eq 1 ]]; then
  nohup "${START_CMD[@]}" > "$LOG_FILE" 2>&1 &
  SVC_PID=$!
  echo "$SVC_PID" > "$PID_FILE"
  ok "后台启动 (pid=$SVC_PID)"
else
  # 前台：同时写日志（tee），Ctrl+C 停止
  "${START_CMD[@]}" 2>&1 | tee "$LOG_FILE"
  exit 0
fi

# ---------- 就绪等待（含模型加载，集成模式约 10-15 秒）----------
echo -n "  等待服务就绪（加载集成模型+7类模型，约 10-20 秒）"
READY=0
for i in $(seq 1 60); do
  sleep 1
  if curl -s -m 2 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then READY=1; break; fi
  kill -0 "$SVC_PID" 2>/dev/null || break
  (( i % 5 == 0 )) && echo -n "."
done
echo

if [[ $READY -eq 1 ]]; then
  HEALTH=$(curl -s -m 8 "http://127.0.0.1:$PORT/api/health")
  INFO=$(curl -s -m 8 "http://127.0.0.1:$PORT/api/model/info")
  echo -e "  ${G}${BOLD}✔ 服务已就绪${N}"
  echo
  echo -e "  ${BOLD}访问地址${N}"
  echo "    前台检测    http://127.0.0.1:$PORT/app/"
  echo "    管理后台    http://127.0.0.1:$PORT/admin/     (admin / <密码>)"
  echo "    API 文档    http://127.0.0.1:$PORT/docs"
  echo
  echo "  模型状态："
  HEALTH="$HEALTH" INFO="$INFO" "$VENV_PY" - <<'PYEOF'
import json, os
def load(k):
    try:
        return json.loads(os.environ.get(k) or "{}")
    except Exception:
        return {}
h, mi = load("HEALTH"), load("INFO")
m = h.get("model") or mi.get("model") or {}
if m:
    line = f"    主判定   {m.get('backend','?')} | {m.get('arch','?')} | 设备 {m.get('device','?')} | 阈值 {m.get('default_threshold','?')}"
    if m.get("ensemble"):
        line += f" | 集成 {m.get('ensemble_size')} 模型"
    print(line)
t = mi.get("type_model") or {}
if t:
    if t.get("enabled") and t.get("ready"):
        print(f"    类型参考 {t.get('backend','?')} | {t.get('num_classes',7)} 类 | 加载 {t.get('load_time_s','?')}s | ready")
    elif t.get("enabled"):
        print(f"    类型参考 已启用但未就绪 (架构 {t.get('arch','?')})")
    else:
        print("    类型参考 未启用（仅良恶性二分类）")
else:
    print("    类型参考 未启用（仅良恶性二分类）")
PYEOF
  echo "  数据库后端： $DB_BACKEND"
  if [[ "$DB_BACKEND" == "mysql" ]]; then
    echo "    （MySQL 8.0.29 @ Windows/172.30.160.1:3306/skin_cancer，独立库与医小喵隔离）"
  else
    echo "    （SQLite: backend/skin_cancer.db，零配置）"
  fi
  echo
  echo -e "  停止服务： ${BOLD}bash stop.sh${N}   或  kill $SVC_PID"
  echo "  实时日志： tail -f $LOG_FILE"

  # ---------- 8. Cloudflare 公网隧道（skin.osanu.dpdns.org）----------
  CF_TOKEN_FILE="${SKIN_CF_TOKEN:-$HOME/.cloudflared/yixiaomiao-run.token}"
  if [[ -f "$CF_TOKEN_FILE" ]]; then
    echo
    echo -e "${BOLD}${B}[8/8]${N} 公网隧道（Cloudflare Tunnel）"
    if pgrep -f "cloudflared tunnel run" >/dev/null 2>&1; then
      ok "隧道已在运行"
    else
      CF_BIN="$(command -v cloudflared || echo "$HOME/.local/bin/cloudflared")"
      if [[ -x "$CF_BIN" ]]; then
        echo -n "     启动中 … "
        # setsid 真正脱离会话（PPID→init），比 nohup 更彻底：
        # nohup 只防 SIGHUP，setsid 让进程不受终端/父进程退出影响
        setsid nohup "$CF_BIN" tunnel run --token-file "$CF_TOKEN_FILE" \
          > "$LOG_DIR/cloudflared.log" 2>&1 < /dev/null &
        disown 2>/dev/null || true
        for _ in $(seq 1 25); do
          sleep 2
          code=$(curl -s -o /dev/null -w "%{http_code}" -m 10 "https://skin.osanu.dpdns.org/api/health" 2>/dev/null)
          [[ "$code" == "200" ]] && break
        done
        if [[ "${code:-}" == "200" ]]; then echo -e "${G}就绪${N}"; else echo -e "${Y}超时（稍后自动恢复）${N}"; fi
      else
        warn "未找到 cloudflared（跳过公网隧道）"
      fi
    fi
    echo "     公网地址    https://skin.osanu.dpdns.org/app/"
  else
    echo
    echo -e "${BOLD}${B}[8/8]${N} 公网隧道"
    warn "未找到 token（$CF_TOKEN_FILE），跳过公网隧道（不影响本地使用）"
  fi
else
  bad "服务未在 60 秒内就绪"
  echo "     最后 25 行日志："
  tail -n 25 "$LOG_FILE" 2>/dev/null | sed 's/^/     /'
  echo
  echo "     排查提示：模型文件是否存在 / 显存是否被 Ollama 占用 / 端口是否冲突"
  exit 1
fi
