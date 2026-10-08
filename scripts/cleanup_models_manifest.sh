#!/usr/bin/env bash
# ============================================================
#  模型产物清理（B 方案）—— 删除 7 个无用目录 + 所有 last.pt
#  执行前自动生成回滚清单
# ============================================================
set -uo pipefail
P="/mnt/d/Project/JXprojiect/Hermes-project/project/皮肤癌图像系统"
cd "$P" || exit 1

MANIFEST="/tmp/model_cleanup_manifest.txt"
echo "=============================================================="
echo "  清理回滚清单（$(date '+%F %T')）"
echo "==============================================================" | tee "$MANIFEST"

# ---------- 待删目录 ----------
DIRS=(
  models_convnext_t288
  models_vD_warmup
  models_mixed_v1
  models_mixed_v2
  models_multimodal_v1
  models_multimodal_v2
  models_bcn_expert
)

echo "" | tee -a "$MANIFEST"
echo "【一、完整删除的目录】" | tee -a "$MANIFEST"
for d in "${DIRS[@]}"; do
  if [ -d "$d" ]; then
    sz=$(du -sm "$d" | cut -f1)
    n=$(find "$d" -type f | wc -l)
    printf "  %-26s %6s MB  %3s 个文件\n" "$d" "$sz" "$n" | tee -a "$MANIFEST"
  else
    printf "  %-26s (不存在)\n" "$d" | tee -a "$MANIFEST"
  fi
done

echo "" | tee -a "$MANIFEST"
echo "【二、删除的 last.pt（best.pt 与记录文件保留）】" | tee -a "$MANIFEST"
for f in models_*/last.pt; do
  [ -f "$f" ] || continue
  sz=$(du -sm "$f" | cut -f1)
  printf "  %-40s %6s MB\n" "$f" "$sz" | tee -a "$MANIFEST"
done

echo "" | tee -a "$MANIFEST"
echo "【三、保留的关键文件（不可删）】" | tee -a "$MANIFEST"
for f in models_vE_r101_288/best.pt models_mix_cutmix_long/best.pt \
         models_compressed/model_int8.onnx models_compressed_7class/model_int8.onnx \
         models_7class_r50/best.pt models_v2_full/best.pt; do
  [ -f "$f" ] && printf "  ✔ %s\n" "$f" | tee -a "$MANIFEST"
done

echo "" | tee -a "$MANIFEST"
echo "【四、回滚方式】从这几处可恢复：" | tee -a "$MANIFEST"
echo "  · last.pt：重新训练即可（或用 best.pt 作为起点 resume）" | tee -a "$MANIFEST"
echo "  · 完整目录：scripts/ 内有对应训练脚本，重新训练" | tee -a "$MANIFEST"
echo "  · 训练超参数见 models_*/final_metrics.json 与 docs/ 记录" | tee -a "$MANIFEST"

echo ""
echo "=============================================================="
echo "  清单已保存: $MANIFEST"
echo "=============================================================="
