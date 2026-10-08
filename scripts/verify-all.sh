#!/usr/bin/env bash
# ============================================================
#  皮肤癌图像检测系统 — 统一验证入口
# ------------------------------------------------------------
#  用法：
#    bash scripts/verify-all.sh             跑全部验证
#    bash scripts/verify-all.sh api         只跑后端接口验证
#    bash scripts/verify-all.sh ui          只跑前端/后台 UI 验证
#    bash scripts/verify-all.sh syntax      只跑语法与结构检查
#
#  前置：服务已在 8000 端口运行（bash start.sh --bg）
#  说明：
#    · 本项目【没有配 npm test】（frontend/package.json 只有 dev/build/preview），
#      所以验证靠本脚本 + scripts/system_test.py 两套。
#    · UI 验证依赖 Playwright（装在 /tmp/pwtest 的临时 node_modules，
#      若缺失会自动提示安装命令）。
# ============================================================
set -uo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="http://127.0.0.1:8000"
VENV_PY="${SKIN_VENV_PY:-$HOME/shixun-venv/bin/python}"
PW_DIR="${PW_DIR:-/tmp/pwtest}"     # Playwright 运行目录（含 node_modules）
WHAT="${1:-all}"

G="\033[32m"; R="\033[31m"; Y="\033[33m"; B="\033[36m"; N="\033[0m"; BOLD="\033[1m"
PASS=0; FAIL=0
ok()   { echo -e "  ${G}✔${N} $1"; PASS=$((PASS+1)); }
bad()  { echo -e "  ${R}✘${N} $1"; FAIL=$((FAIL+1)); }
hdr()  { echo -e "\n${BOLD}${B}=== $1 ===${N}"; }

# ---------- 0. 服务可用性 ----------
hdr "0. 服务可用性"
if curl -s -m 5 "$BASE/api/health" >/dev/null 2>&1; then
  ok "服务在线（$BASE）"
else
  bad "服务未响应 —— 先运行：bash start.sh --bg"
  echo -e "     ${Y}后续验证无法进行，已中止${N}"; exit 1
fi

# ---------- 1. 语法与结构 ----------
if [[ "$WHAT" == "all" || "$WHAT" == "syntax" ]]; then
  hdr "1. 语法与结构"
  "$VENV_PY" -m py_compile \
    "$PROJ/backend/app/database.py" \
    "$PROJ/backend/app/admin_api.py" \
    "$PROJ/backend/app/audit.py" \
    "$PROJ/backend/app/main.py" 2>/dev/null \
    && ok "后端 Python 语法（py_compile）" || bad "后端 Python 语法"

  "$VENV_PY" - "$PROJ" <<'PYEOF' && ok "后台 HTML 标签配对与关键元素" || bad "后台 HTML 结构"
import re, sys, os
proj = sys.argv[1]
bad = 0
for f in ["backend/static/admin/index.html",
          "backend/static/admin/records.html",
          "backend/static/admin/logs.html"]:
    p = os.path.join(proj, f)
    if not os.path.exists(p):
        print(f"  缺文件: {f}"); bad += 1; continue
    s = open(p, encoding="utf-8").read()
    for tag in ("div", "script", "table", "tbody", "tr", "td", "th", "select", "button"):
        o = len(re.findall(r"<" + tag + r"[ >]", s))
        c = len(re.findall(r"</" + tag + r">", s))
        if o != c:
            print(f"  {f}: <{tag}> 开{o} 闭{c} 不配对"); bad += 1
sys.exit(1 if bad else 0)
PYEOF
fi

# ---------- 2. 后端接口 ----------
if [[ "$WHAT" == "all" || "$WHAT" == "api" ]]; then
  hdr "2. 后端接口（看板/问答/权限）"
  if [[ -f "$PROJ/scripts/verify-admin-chat-api.sh" ]]; then
    OUT="$(bash "$PROJ/scripts/verify-admin-chat-api.sh" 2>&1)"
    if echo "$OUT" | grep -q "✔"; then
      ok "问答接口与统计口径："
      echo "$OUT" | sed -n '3,16p' | sed 's/^/      /'
    else
      bad "问答接口验证失败："; echo "$OUT" | tail -12 | sed 's/^/      /'
    fi
  else
    bad "缺 scripts/verify-admin-chat-api.sh"
  fi
fi

# ---------- 3. UI（Playwright）----------
if [[ "$WHAT" == "all" || "$WHAT" == "ui" ]]; then
  hdr "3. 前端与后台 UI（Playwright 真实浏览器）"
  if ! command -v node >/dev/null 2>&1; then
    bad "未安装 node，跳过 UI 验证"
  elif [[ ! -d "$PW_DIR/node_modules/playwright" ]]; then
    bad "Playwright 未就绪（$PW_DIR 缺 node_modules/playwright）"
    echo "      安装： mkdir -p $PW_DIR && cd $PW_DIR && npm init -y && npm i playwright"
  else
    for spec in verify-process.mjs verify-statcards.mjs verify-admin-dash.mjs \
                verify-admin-records-tabs.mjs verify-admin-system.mjs; do
      SRC="$PROJ/scripts/$spec"
      [[ -f "$SRC" ]] || { bad "缺 $spec"; continue; }
      cp -f "$SRC" "$PW_DIR/"
      OUT="$(cd "$PW_DIR" && node "$spec" 2>&1)"
      if echo "$OUT" | grep -q "✔ PASS"; then
        ok "$spec → PASS"
        echo "$OUT" | grep -E "^\s+(✔|y\(|week/|✘)" | head -6 | sed 's/^/      /'
      else
        bad "$spec → FAIL"
        echo "$OUT" | grep -A6 "结论" | tail -8 | sed 's/^/      /'
      fi
    done
  fi
fi

# ---------- 汇总 ----------
echo
echo -e "${BOLD}=== 汇总 ===${N}"
echo -e "  通过 ${G}${PASS}${N} 项 / 失败 ${R}${FAIL}${N} 项"
if [[ $FAIL -eq 0 ]]; then
  echo -e "  ${G}${BOLD}✔ 全部通过${N}"
else
  echo -e "  ${R}${BOLD}✘ 存在失败项，请查看上面的明细${N}"
fi
echo
echo "  提示：本项目未配置 npm test（frontend/package.json 无 test 脚本），"
echo "        完整系统测试请另外运行： $VENV_PY scripts/system_test.py"
exit $(( FAIL > 0 ? 1 : 0 ))
