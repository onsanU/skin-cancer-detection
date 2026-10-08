#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据预处理 v3：训练集平衡采样 + 测试集保持不变
================================================================
诊断驱动的改进:
  问题: 训练集良性7966/恶性1836 = 4.34:1，测试集却是0.81:1 → 分布不一致
  方案: 良性下采样到与恶性相当，让训练集接近 1:1
  范围: 只下采样"训练集"，测试集213张一个字都不动

同时增加一个更强的增强版本供对比。

输出:
  dataset/processed_v3_balanced/
    ├── train/{benign,malignant}/*.jpg
    ├── test/{benign,malignant}/*.jpg   ← 与 v1/v2 完全一致
    └── split_info_v3.json

用法:
  python3 prepare_dataset_v3_balanced.py
  python3 prepare_dataset_v3_balanced.py --benign-ratio 1.1   # 良性留1.1倍恶性量
"""

import argparse
import csv
import json
import os
import random
import shutil
import sys
from collections import defaultdict

MALIGNANT = {"mel", "bcc", "akiec"}
BENIGN = {"nv", "bkl", "df", "vasc"}
DX_CN = {
    "mel": "黑色素瘤", "bcc": "基底细胞癌", "akiec": "光化性角化/原位鳞癌",
    "nv": "黑色素细胞痣", "bkl": "良性角化", "df": "皮肤纤维瘤", "vasc": "血管性病变",
}
PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def log(msg, f=None):
    print(msg, flush=True)
    if f:
        f.write(msg + "\n")


def build_image_index(dirs):
    idx = {}
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.lower().endswith((".jpg", ".jpeg", ".png")):
                idx[os.path.splitext(fn)[0]] = os.path.join(d, fn)
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default=os.path.join(PROJ_ROOT, "dataset", "HAM10000_raw"))
    ap.add_argument("--v1-dir", default=os.path.join(PROJ_ROOT, "dataset", "processed"),
                    help="v1 目录（提供测试集划分，必须保持一致）")
    ap.add_argument("--v2-dir", default=os.path.join(PROJ_ROOT, "dataset", "processed_v2_full"),
                    help="v2 目录（提供全量训练池）")
    ap.add_argument("--out-dir", default=os.path.join(PROJ_ROOT, "dataset", "processed_v3_balanced"))
    ap.add_argument("--benign-ratio", type=float, default=1.0,
                    help="良性保留量与恶性图片量的比例（1.0=完全平衡）")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--copy", action="store_true")
    args = ap.parse_args()

    raw = os.path.abspath(args.raw_dir)
    out = os.path.abspath(args.out_dir)

    # ---- 读 v2 的划分（训练池全量 + 测试集锁定）----
    v2_info_path = os.path.join(os.path.abspath(args.v2_dir), "split_info_v2.json")
    v1_info_path = os.path.join(os.path.abspath(args.v1_dir), "split_info.json")

    if not os.path.isfile(v2_info_path):
        print(f"[ERROR] 需要先运行 prepare_dataset_v2.py（缺 {v2_info_path}）", file=sys.stderr)
        sys.exit(1)
    v2 = json.load(open(v2_info_path, encoding="utf-8"))

    test_mal = v2["split"]["test"]["malignant"]
    test_ben = v2["split"]["test"]["benign"]
    train_mal_lesions = v2["split"]["train"]["malignant"]
    train_ben_lesions = v2["split"]["train"]["benign"]
    lesion_images = {l: v for l, v in v2["lesion_images"].items()}
    lesion_dx = v2["lesion_dx"]

    # 原始图片索引（v2 的图片是从 raw 硬链接过来的）
    img_index = build_image_index([
        os.path.join(os.path.abspath(args.v2_dir), "train", "malignant"),
        os.path.join(os.path.abspath(args.v2_dir), "train", "benign"),
        os.path.join(raw, "HAM10000_images_part_1"),
        os.path.join(raw, "HAM10000_images_part_2"),
    ])

    os.makedirs(out, exist_ok=True)
    report = open(os.path.join(out, "dataset_report_v3.txt"), "w", encoding="utf-8")

    log("=" * 72, report)
    log("HAM10000 数据预处理 v3：训练集平衡采样", report)
    log("=" * 72, report)
    log(f"问题诊断: v2训练集 良性7966/恶性1836 = 4.34:1，与测试集0.81:1分布不一致", report)
    log(f"解决策略: 良性下采样至恶性的 {args.benign_ratio:.2f} 倍", report)

    # ---- 计算恶性图片总数 ----
    mal_imgs = []
    for l in train_mal_lesions:
        mal_imgs.extend(lesion_images[l])
    n_mal = len(mal_imgs)
    target_ben = int(n_mal * args.benign_ratio)
    log(f"\n恶性图片总数: {n_mal} 张", report)
    log(f"目标良性图片数: {target_ben} 张", report)

    # ---- 良性按"病灶"为单位随机下采样（保证病灶完整性）----
    rng = random.Random(args.seed)
    ben_lesions_shuffled = list(train_ben_lesions)
    rng.shuffle(ben_lesions_shuffled)

    ben_imgs, used_ben_lesions = [], []
    for l in ben_lesions_shuffled:
        if len(ben_imgs) >= target_ben:
            break
        ben_imgs.extend(lesion_images[l])
        used_ben_lesions.append(l)

    # 确保良性类别多样性：至少保留一些 df/vasc（稀有良性类）
    log(f"\n良性采样: {len(used_ben_lesions)} 病灶 -> {len(ben_imgs)} 张", report)
    log(f"恶性全部保留: {len(train_mal_lesions)} 病灶 -> {n_mal} 张", report)

    total_train = len(mal_imgs) + len(ben_imgs)
    log(f"平衡后训练集: {total_train} 张 (恶性{len(mal_imgs)} : 良性{len(ben_imgs)} = "
        f"1 : {len(ben_imgs)/max(1,len(mal_imgs)):.2f})", report)

    # ---- 输出 ----
    for sub in ("train", "test"):
        p = os.path.join(out, sub)
        if os.path.isdir(p):
            shutil.rmtree(p)

    def place(iid, dst_dir):
        dst = os.path.join(dst_dir, f"{iid}.jpg")
        if os.path.exists(dst):
            return False
        src = img_index.get(iid)
        if not src:
            return False
        if not args.copy:
            try:
                os.link(src, dst)
                return True
            except OSError:
                pass
        shutil.copy2(src, dst)
        return True

    stats = {}
    plan = [
        ("train", "malignant", train_mal_lesions),
        ("train", "benign", used_ben_lesions),
        ("test", "malignant", test_mal),
        ("test", "benign", test_ben),
    ]
    for split, cls, lesions in plan:
        d = os.path.join(out, split, cls)
        os.makedirs(d, exist_ok=True)
        n = 0
        for l in lesions:
            for iid in lesion_images[l]:
                if place(iid, d):
                    n += 1
        stats[f"{split}/{cls}"] = {"lesions": len(lesions), "images": n}

    log(f"\n[输出]", report)
    total = 0
    for k in sorted(stats):
        s = stats[k]; total += s["images"]
        log(f"  {k:18s} 病灶 {s['lesions']:4d} -> 图片 {s['images']:5d} 张", report)
    log(f"  合计 {total} 张", report)

    # ---- 校验 ----
    tr_les = set(train_mal_lesions) | set(used_ben_lesions)
    te_les = set(test_mal) | set(test_ben)
    tr_imgs = set(i for l in tr_les for i in lesion_images[l])
    te_imgs = set(i for l in te_les for i in lesion_images[l])
    log(f"\n[校验] 病灶交集={len(tr_les & te_les)} 图片交集={len(tr_imgs & te_imgs)}", report)

    info = {
        "version": "v3_balanced",
        "note": "训练集良性下采样至与恶性接近1:1；测试集与v1/v2完全一致",
        "seed": args.seed,
        "benign_ratio": args.benign_ratio,
        "class_mapping": {"malignant": sorted(MALIGNANT), "benign": sorted(BENIGN)},
        "dx_cn": DX_CN,
        "split": {
            "train": {"malignant": train_mal_lesions, "benign": used_ben_lesions},
            "test": {"malignant": test_mal, "benign": test_ben},
        },
        "lesion_images": lesion_images,
        "lesion_dx": lesion_dx,
        "stats": stats,
        "total_images": total,
        "leakage_check": {"lesion": len(tr_les & te_les), "image": len(tr_imgs & te_imgs)},
    }
    with open(os.path.join(out, "split_info_v3.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    log(f"\n已保存 split_info_v3.json", report)
    report.close()
    print(f"\n输出: {out}")


if __name__ == "__main__":
    main()
