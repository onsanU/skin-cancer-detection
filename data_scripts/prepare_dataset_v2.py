#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HAM10000 数据预处理 v2：训练集全量扩容 + 测试集保持不变
================================================================
核心思路（响应"数据量不足"诊断）:
  测试集  : 完全沿用 v1(processed/) 的 140 个病灶、213 张图  → 保证结果可对比
  训练集  : 使用 v1 训练集(560病灶) + 剩余所有未使用病灶  → 最大化利用数据
  防泄漏  : 严格排除测试集病灶，一个都不许混进训练集

对比:
  v1: train 792 张 (560病灶) / test 213 张 (140病灶)
  v2: train 全量剩余         / test 213 张 (与v1完全相同)

输出:
  dataset/processed_v2_full/
    ├── train/{benign,malignant}/*.jpg
    ├── test/{benign,malignant}/*.jpg   ← 与 v1 完全一致
    └── split_info_v2.json

用法:
  python3 prepare_dataset_v2.py
"""

import argparse
import csv
import json
import os
import shutil
import sys
from collections import Counter, defaultdict

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
                    help="v1 输出目录（提供测试集划分）")
    ap.add_argument("--out-dir", default=os.path.join(PROJ_ROOT, "dataset", "processed_v2_full"))
    ap.add_argument("--copy", action="store_true", help="复制而非硬链接")
    args = ap.parse_args()

    raw, v1, out = os.path.abspath(args.raw_dir), os.path.abspath(args.v1_dir), os.path.abspath(args.out_dir)

    # ---- 读取 v1 的划分（测试集必须保持一致）----
    v1_info_path = os.path.join(v1, "split_info.json")
    if not os.path.isfile(v1_info_path):
        print(f"[ERROR] 找不到 v1 的 split_info.json: {v1_info_path}", file=sys.stderr)
        print("        请先运行 prepare_dataset.py", file=sys.stderr)
        sys.exit(1)
    v1_info = json.load(open(v1_info_path, encoding="utf-8"))
    test_lesions = set(v1_info["split"]["test"]["malignant"]) | set(v1_info["split"]["test"]["benign"])

    os.makedirs(out, exist_ok=True)
    report = open(os.path.join(out, "dataset_report_v2.txt"), "w", encoding="utf-8")

    log("=" * 72, report)
    log("HAM10000 数据预处理 v2：训练集全量扩容", report)
    log("=" * 72, report)
    log(f"测试集来源: {v1_info_path}", report)
    log(f"测试集病灶数(锁定): {len(test_lesions)}", report)

    # ---- 读 metadata & 建索引 ----
    meta_path = os.path.join(raw, "HAM10000_metadata.csv")
    with open(meta_path, encoding="utf-8") as f:
        sample = f.readline(); f.seek(0)
        delim = "\t" if sample.count("\t") > sample.count(",") else ","
        rows = list(csv.DictReader(f, delimiter=delim))

    img_index = build_image_index([
        os.path.join(raw, "HAM10000_images_part_1"),
        os.path.join(raw, "HAM10000_images_part_2"),
        raw,
    ])
    log(f"\nmetadata {len(rows)} 条 | 图片 {len(img_index)} 张", report)

    # ---- 聚合到病灶 ----
    lesion_cls, lesion_dx = {}, {}
    lesion_images = defaultdict(list)
    for r in rows:
        lid, iid, dx = r["lesion_id"], r["image_id"], r["dx"]
        if iid not in img_index:
            continue
        cls = "malignant" if dx in MALIGNANT else ("benign" if dx in BENIGN else None)
        if cls is None:
            continue
        lesion_cls[lid] = cls
        lesion_dx[lid] = dx
        lesion_images[lid].append(iid)

    # ---- 关键：测试集病灶从训练池中彻底剔除 ----
    all_lesions = set(lesion_cls.keys())
    train_lesions = all_lesions - test_lesions

    leak = train_lesions & test_lesions
    log(f"\n[防泄漏] 训练池 {len(train_lesions)} 病灶 | 测试集 {len(test_lesions)} 病灶 | 交集 {len(leak)} {'✅' if not leak else '❌ 严重错误!'}", report)

    train_mal = sorted([l for l in train_lesions if lesion_cls[l] == "malignant"])
    train_ben = sorted([l for l in train_lesions if lesion_cls[l] == "benign"])
    test_mal = sorted([l for l in test_lesions if lesion_cls[l] == "malignant"])
    test_ben = sorted([l for l in test_lesions if lesion_cls[l] == "benign"])

    log(f"\n[划分]", report)
    log(f"  训练: 恶性 {len(train_mal)} 病灶 / 良性 {len(train_ben)} 病灶", report)
    log(f"  测试: 恶性 {len(test_mal)} 病灶 / 良性 {len(test_ben)} 病灶 (与v1一致)", report)

    # ---- 输出 ----
    for sub in ("train", "test"):
        p = os.path.join(out, sub)
        if os.path.isdir(p):
            shutil.rmtree(p)

    def place(src, dst):
        if not args.copy:
            try:
                os.link(src, dst)
                return
            except OSError:
                pass
        shutil.copy2(src, dst)

    stats = {}
    for split, mal, ben in [("train", train_mal, train_ben), ("test", test_mal, test_ben)]:
        for cls, lesions in [("malignant", mal), ("benign", ben)]:
            d = os.path.join(out, split, cls)
            os.makedirs(d, exist_ok=True)
            n = 0
            for lid in lesions:
                for iid in lesion_images[lid]:
                    dst = os.path.join(d, f"{iid}.jpg")
                    if not os.path.exists(dst):
                        place(img_index[iid], dst)
                        n += 1
            stats[f"{split}/{cls}"] = {"lesions": len(lesions), "images": n}

    log(f"\n[输出]", report)
    total = 0
    for k in sorted(stats):
        s = stats[k]
        total += s["images"]
        log(f"  {k:18s} 病灶 {s['lesions']:4d} 个 -> 图片 {s['images']:5d} 张", report)
    log(f"  合计 {total} 张", report)

    # ---- 校验 ----
    tr_imgs, te_imgs = set(), set()
    for l in train_lesions: tr_imgs.update(lesion_images[l])
    for l in test_lesions: te_imgs.update(lesion_images[l])
    log(f"\n[校验]", report)
    log(f"  病灶级交集: {len(train_lesions & test_lesions)}", report)
    log(f"  图片级交集: {len(tr_imgs & te_imgs)}", report)

    info = {
        "version": "v2_full",
        "note": "训练集使用全部剩余数据；测试集与 v1 完全一致，保证可比性",
        "source": raw,
        "test_from": v1_info_path,
        "class_mapping": {"malignant": sorted(MALIGNANT), "benign": sorted(BENIGN)},
        "dx_cn": DX_CN,
        "split": {
            "train": {"malignant": train_mal, "benign": train_ben},
            "test": {"malignant": test_mal, "benign": test_ben},
        },
        "lesion_images": {l: sorted(lesion_images[l]) for l in sorted(all_lesions)},
        "lesion_dx": {l: lesion_dx[l] for l in sorted(all_lesions)},
        "stats": stats,
        "total_images": total,
        "leakage_check": {"lesion": len(train_lesions & test_lesions), "image": len(tr_imgs & te_imgs)},
    }
    with open(os.path.join(out, "split_info_v2.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    log(f"\n已保存: {os.path.join(out, 'split_info_v2.json')}", report)
    report.close()
    print(f"\n输出: {out}")


if __name__ == "__main__":
    main()
