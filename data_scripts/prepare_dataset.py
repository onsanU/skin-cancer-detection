#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HAM10000 数据预处理：7类 -> 2类(良性/恶性) + 病灶级抽样 + 病灶级划分
================================================================
关键设计（防数据泄漏）:
  同一 lesion_id 的所有图片，必须完整落在 train 或 test 的同一侧。
  绝不按图片随机划分，否则模型会"考前见过题"，准确率虚高。

输出:
  dataset/processed/
    ├── train/{benign,malignant}/*.jpg
    ├── test/{benign,malignant}/*.jpg
    ├── split_info.json   可复现记录（用了哪些病灶、随机种子、统计）
    └── dataset_report.txt 人类可读报告

用法:
  python3 prepare_dataset.py
  python3 prepare_dataset.py --seed 42 --n-lesions 350 --test-ratio 0.2
"""

import argparse
import csv
import json
import os
import random
import shutil
import sys
from collections import Counter, defaultdict

# ============ 7 类 -> 2 类 映射 ============
# 恶性(malignant): 黑色素瘤 / 基底细胞癌 / 光化性角化(含原位鳞癌)
MALIGNANT = {"mel", "bcc", "akiec"}
# 良性(benign): 黑色素细胞痣 / 良性角化 / 皮肤纤维瘤 / 血管性病变
BENIGN = {"nv", "bkl", "df", "vasc"}
ALL_CLASSES = MALIGNANT | BENIGN

DX_CN = {
    "mel": "黑色素瘤", "bcc": "基底细胞癌", "akiec": "光化性角化/原位鳞癌",
    "nv": "黑色素细胞痣", "bkl": "良性角化", "df": "皮肤纤维瘤", "vasc": "血管性病变",
}


def log(msg, f=None):
    print(msg, flush=True)
    if f:
        f.write(msg + "\n")


def build_image_index(search_dirs):
    """扫描图片目录，建立 image_id -> 绝对路径 的索引"""
    index = {}
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.lower().endswith((".jpg", ".jpeg", ".png")):
                image_id = os.path.splitext(fn)[0]
                index[image_id] = os.path.join(d, fn)
    return index


def main():
    ap = argparse.ArgumentParser(description="HAM10000 预处理：7类->2类 + 病灶级抽样划分")
    ap.add_argument("--raw-dir", default=os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "dataset", "HAM10000_raw"),
        help="HAM10000_raw 目录")
    ap.add_argument("--out-dir", default=os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "dataset", "processed"),
        help="输出目录")
    ap.add_argument("--seed", type=int, default=42, help="随机种子(保证可复现)")
    ap.add_argument("--n-lesions", type=int, default=350,
                    help="每类抽取的病灶数(任务书要求各350例)")
    ap.add_argument("--test-ratio", type=float, default=0.2, help="测试集比例")
    ap.add_argument("--copy", action="store_true",
                    help="复制图片(默认是硬链接，省空间；跨盘时自动降级为复制)")
    args = ap.parse_args()

    raw = os.path.abspath(args.raw_dir)
    out = os.path.abspath(args.out_dir)
    meta_path = os.path.join(raw, "HAM10000_metadata.csv")

    if not os.path.isfile(meta_path):
        print(f"[ERROR] 找不到 metadata: {meta_path}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(out, exist_ok=True)
    report = open(os.path.join(out, "dataset_report.txt"), "w", encoding="utf-8")

    log("=" * 70, report)
    log("HAM10000 数据预处理报告", report)
    log(f"源目录: {raw}", report)
    log(f"输出目录: {out}", report)
    log(f"随机种子: {args.seed} | 每类病灶数: {args.n_lesions} | 测试比例: {args.test_ratio}", report)
    log("=" * 70, report)

    # ---------- 1. 读 metadata ----------
    with open(meta_path, encoding="utf-8") as f:
        # Kaggle 版是逗号分隔，Dataverse 版是 tab；自动嗅探
        sample = f.readline()
        f.seek(0)
        delim = "\t" if sample.count("\t") > sample.count(",") else ","
        rows = list(csv.DictReader(f, delimiter=delim))

    log(f"\n[1] 读取 metadata: {len(rows)} 条记录 (分隔符='{delim}')", report)

    # ---------- 2. 建立图片索引 ----------
    img_index = build_image_index([
        os.path.join(raw, "HAM10000_images_part_1"),
        os.path.join(raw, "HAM10000_images_part_2"),
        raw,  # 兼容图片直接铺在 root 的情况
    ])
    log(f"[2] 扫描到图片: {len(img_index)} 张", report)

    missing = [r["image_id"] for r in rows if r["image_id"] not in img_index]
    if missing:
        log(f"    [WARN] metadata 中有 {len(missing)} 张图找不到文件，已跳过: {missing[:5]}...", report)

    # ---------- 3. 7类 -> 2类映射 + 按病灶聚合 ----------
    lesion_cls = {}          # lesion_id -> 'benign'/'malignant'
    lesion_dx = {}           # lesion_id -> 原始 dx
    lesion_images = defaultdict(list)   # lesion_id -> [image_id, ...]
    conflict = []

    for r in rows:
        lid, iid, dx = r["lesion_id"], r["image_id"], r["dx"]
        if iid not in img_index:
            continue
        if dx in MALIGNANT:
            cls = "malignant"
        elif dx in BENIGN:
            cls = "benign"
        else:
            continue
        if lid in lesion_cls and lesion_cls[lid] != cls:
            conflict.append(lid)   # 同一病灶标注了不同性质（极少见）
            continue
        lesion_cls[lid] = cls
        lesion_dx[lid] = dx
        lesion_images[lid].append(iid)

    log(f"[3] 7类 -> 2类 映射完成", report)
    dx_img_cnt = Counter(r["dx"] for r in rows if r["image_id"] in img_index)
    for dx, cnt in dx_img_cnt.most_common():
        tag = "恶性" if dx in MALIGNANT else "良性"
        log(f"    {dx:6s} ({DX_CN.get(dx,'?'):12s}) [{tag}]  图片 {cnt:5d}", report)
    if conflict:
        log(f"    [WARN] {len(conflict)} 个病灶存在类别冲突，已跳过", report)

    mal_lesions = sorted([l for l, c in lesion_cls.items() if c == "malignant"])
    ben_lesions = sorted([l for l, c in lesion_cls.items() if c == "benign"])
    log(f"\n    病灶级统计: 恶性 {len(mal_lesions)} 个 / 良性 {len(ben_lesions)} 个", report)

    # ---------- 4. 分层抽样 ----------
    rng = random.Random(args.seed)
    if len(mal_lesions) < args.n_lesions or len(ben_lesions) < args.n_lesions:
        log(f"[ERROR] 病灶数不足！恶性 {len(mal_lesions)} / 良性 {len(ben_lesions)}，"
            f"无法各抽 {args.n_lesions} 个", report)
        report.close()
        sys.exit(1)

    picked_mal = sorted(rng.sample(mal_lesions, args.n_lesions))
    picked_ben = sorted(rng.sample(ben_lesions, args.n_lesions))
    log(f"\n[4] 分层抽样完成 (seed={args.seed}): 恶性 {len(picked_mal)} 个 / 良性 {len(picked_ben)} 个", report)

    # ---------- 5. 病灶级划分 train/test ----------
    def split_lesions(lesions, ratio):
        s = list(lesions)
        rng.shuffle(s)
        n_test = max(1, int(round(len(s) * ratio)))
        return sorted(s[n_test:]), sorted(s[:n_test])   # train, test

    mal_train, mal_test = split_lesions(picked_mal, args.test_ratio)
    ben_train, ben_test = split_lesions(picked_ben, args.test_ratio)

    log(f"[5] 病灶级划分 (train:test = {1-args.test_ratio:.0%}:{args.test_ratio:.0%})", report)
    log(f"    恶性  训练 {len(mal_train):3d} 病灶 / 测试 {len(mal_test):3d} 病灶", report)
    log(f"    良性  训练 {len(ben_train):3d} 病灶 / 测试 {len(ben_test):3d} 病灶", report)

    # ---------- 6. 复制/硬链接图片 ----------
    splits = {
        ("train", "malignant"): mal_train,
        ("test", "malignant"): mal_test,
        ("train", "benign"): ben_train,
        ("test", "benign"): ben_test,
    }

    # 清空旧输出（只清 train/test 两个子目录）
    for sub in ("train", "test"):
        p = os.path.join(out, sub)
        if os.path.isdir(p):
            shutil.rmtree(p)

    def place(src, dst):
        """优先硬链接(省空间)，失败则复制"""
        if not args.copy:
            try:
                os.link(src, dst)
                return "link"
            except OSError:
                pass
        shutil.copy2(src, dst)
        return "copy"

    stats = {}
    total_files = 0
    method_used = set()

    for (split, cls), lesions in splits.items():
        dst_dir = os.path.join(out, split, cls)
        os.makedirs(dst_dir, exist_ok=True)
        n = 0
        for lid in lesions:
            for iid in lesion_images[lid]:
                src = img_index[iid]
                dst = os.path.join(dst_dir, f"{iid}.jpg")
                if not os.path.exists(dst):
                    method_used.add(place(src, dst))
                    n += 1
        stats[f"{split}/{cls}"] = {"lesions": len(lesions), "images": n}
        total_files += n

    log(f"\n[6] 图片输出完成 (方式: {'/'.join(sorted(method_used))})", report)
    for k in sorted(stats):
        s = stats[k]
        log(f"    {k:20s} 病灶 {s['lesions']:3d} 个 -> 图片 {s['images']:4d} 张", report)
    log(f"    合计 {total_files} 张图片", report)

    # ---------- 7. 校验：无病灶跨集泄漏 ----------
    train_les = set(mal_train) | set(ben_train)
    test_les = set(mal_test) | set(ben_test)
    leak = train_les & test_les
    log(f"\n[7] 数据泄漏校验", report)
    log(f"    训练集病灶 {len(train_les)} 个 / 测试集病灶 {len(test_les)} 个", report)
    log(f"    交集(必须为0): {len(leak)}  {'✅ 通过' if not leak else '❌ 失败!'}", report)

    # 图片级二次校验
    train_imgs, test_imgs = set(), set()
    for lid in train_les:
        train_imgs.update(lesion_images[lid])
    for lid in test_les:
        test_imgs.update(lesion_images[lid])
    img_leak = train_imgs & test_imgs
    log(f"    图片级交集(必须为0): {len(img_leak)}  {'✅ 通过' if not img_leak else '❌ 失败!'}", report)

    # ---------- 8. 保存 split_info.json ----------
    info = {
        "source": raw,
        "seed": args.seed,
        "n_lesions_per_class": args.n_lesions,
        "test_ratio": args.test_ratio,
        "class_mapping": {
            "malignant": sorted(MALIGNANT),
            "benign": sorted(BENIGN),
        },
        "dx_cn": DX_CN,
        "split": {
            "train": {"malignant": mal_train, "benign": ben_train},
            "test": {"malignant": mal_test, "benign": ben_test},
        },
        "lesion_images": {lid: sorted(lesion_images[lid]) for lid in sorted(train_les | test_les)},
        "lesion_dx": {lid: lesion_dx[lid] for lid in sorted(train_les | test_les)},
        "stats": stats,
        "total_images": total_files,
        "leakage_check": {"lesion_leak": len(leak), "image_leak": len(img_leak)},
    }
    with open(os.path.join(out, "split_info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    log(f"\n[8] 已保存 split_info.json + dataset_report.txt", report)
    log("\n完成喵！", report)
    report.close()

    print(f"\n输出目录: {out}")
    print("  train/malignant, train/benign, test/malignant, test/benign")
    print("  split_info.json, dataset_report.txt")


if __name__ == "__main__":
    main()
