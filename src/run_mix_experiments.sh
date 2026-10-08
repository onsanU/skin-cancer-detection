#!/bin/bash
# CutMix / MixUp 对照实验 —— 三组顺序跑（GPU 串行，避免显存竞争）
# A: cutmix   B: mixup   C: none(对照,复现历史基线)
P="/mnt/d/Project/JXprojiect/Hermes-project/project/皮肤癌图像系统"
PY="/home/wpc15/shixun-venv/bin/python3"
cd "$P" || exit 1

mkdir -p logs/exp_mix
COMMON="--data dataset/processed_v2_full --arch convnext_tiny --img-size 288 \
--bs 16 --epochs 20 --patience 8 --workers 4 --aug strong --loss focal \
--eval-split test --seed 42 --warmup 1"

run_one() {
  local tag="$1"; shift
  echo ""
  echo "###############################################################################"
  echo "###  实验组: $tag     开始时间 $(date '+%F %T')"
  echo "###############################################################################"
  $PY src/train_sota.py $COMMON --out "models_mix_$tag" "$@" 2>&1 | tee "logs/exp_mix/$tag.log"
  echo "###  实验组 $tag 结束 $(date '+%F %T')"
  echo ""
}

run_one cutmix --mix cutmix --mix-prob 0.5
run_one mixup  --mix mixup  --mix-prob 0.5
run_one none   --mix none

echo ""
echo "###############################################################################"
echo "###  三组实验全部完成 $(date '+%F %T')"
echo "###############################################################################"
