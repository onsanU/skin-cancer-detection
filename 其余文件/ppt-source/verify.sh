#!/bin/bash
# 一键复验：生成 + 几何QA + 内容QA
set -euo pipefail
cd "$(dirname "$0")"

OUT_DIR=/tmp/skin-ppt/verify_out
DECK="$OUT_DIR/verify_deck.pptx"
mkdir -p "$OUT_DIR"

echo "=== 1/3 生成到临时路径（不碰交付件）==="
OUT_FILE="$DECK" node gen.js

echo ""
echo "=== 2/3 几何 QA（越界检查）==="
# 注意：不能加管道（会吞 exit code），直接重定向到文件
python3 qa_geom.py "$DECK" > /tmp/skin-ppt/geom.txt 2>&1 || {
  echo "❌ qa_geom 执行失败："; tail -12 /tmp/skin-ppt/geom.txt; exit 1
}
if grep -q "无越界问题" /tmp/skin-ppt/geom.txt; then
  echo "✅ 无越界问题"
else
  echo "❌ 发现越界问题："
  grep -A10 "越界问题汇总" /tmp/skin-ppt/geom.txt || tail -20 /tmp/skin-ppt/geom.txt
  exit 1
fi

echo ""
echo "=== 3/3 内容 QA（脏数据 + 页数 + 画布）==="
python3 -m markitdown "$DECK" > /tmp/skin-ppt/verify_dump.txt 2>/dev/null || {
  echo "❌ markitdown 执行失败"; exit 1
}
if grep -qiE "object Object|TODO|占位|undefined|NaN|lorem" /tmp/skin-ppt/verify_dump.txt; then
  echo "❌ 发现脏数据："
  grep -inE "object Object|TODO|占位|undefined|NaN|lorem" /tmp/skin-ppt/verify_dump.txt | head -5
  exit 1
fi
echo "✅ 无脏数据（object Object / TODO / 占位 / undefined / NaN）"

python3 - "$DECK" <<'PY'
import sys
from pptx import Presentation
p = Presentation(sys.argv[1])
n = len(p.slides)
w = p.slide_width.inches
h = p.slide_height.inches
assert n == 19, f"页数应为 19，实际 {n}"
assert abs(w - 10.0) < 0.01 and abs(h - 5.625) < 0.01, f"画布应为 10x5.625，实际 {w}x{h}"
print(f"✅ 页数 {n}，画布 {w}x{h} inch")
PY

echo ""
echo "============================================"
echo "  ✅ 全部验证通过（生成 / 几何 / 内容）"
echo "============================================"
