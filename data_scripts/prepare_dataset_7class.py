#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建 7 类分类数据集（复用现有 HAM10000 原始数据）
================================================================
与二分类数据集的区别：
  二分类: mel/bcc/akiec → 恶性, nv/bkl/vasc/df → 良性
  7 分类: 保留原始 dx 字段的 7 个类别

设计要点：
  1. 硬链接复用原始图片，不额外占用磁盘
  2. 病灶级划分（防数据泄漏），与二分类实验保持一致的划分逻辑
  3. 训练集不分层抽样（用全量），测试集从病灶中抽取
  4. 输出类别权重，供训练脚本处理不平衡
"""
import argparse
import csv
import json
import os
import random
import sys
from collections import Counter, defaultdict

# ============ 配置 ============
RAW_DIR = "dataset/HAM10000_raw"
OUT_DIR = "dataset/processed_7class"

# 7 类映射（HAM10000 原始 dx 字段）
CLASSES = ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"]
CLASS_CN = {
    "akiec": "光化性角化/原位鳞癌",
    "bcc": "基底细胞癌",
    "bkl": "良性角化",
    "df": "皮肤纤维瘤",
    "mel": "黑色素瘤",
    "nv": "黑色素细胞痣",
    "vasc": "血管性病变",
}
# 医学性质（用于前端展示）
CLASS_GROUP = {
    "akiec": "malignant", "bcc": "malignant", "mel": "malignant",
    "bkl": "benign", "df": "benign", "nv": "benign", "vasc": "benign",
}

# 测试集病灶数（与二分类保持一致：140 个病灶）
TEST_LESIONS = 140


def main():
    ap = argparse.ArgumentParser(description="构建 7 类分类数据集")
    ap.add_argument("--seed", type=int, default=42, help="随机种子")
    ap.add_argument("--n-test-lesions", type=int, default=TEST_LESIONS,
                    help="测试集病灶数")
    ap.add_argument("--out", default=OUT_DIR, help="输出目录")
    ap.add_argument("--link", default="hard", choices=["hard", "copy", "symlink"],
                    help="文件链接方式（hard 不占额外磁盘）")
    args = ap.parse_args()

    rng = random.Random(args.seed)

    # ---------- 1. 读取元数据 ----------
    meta_path = os.path.join(RAW_DIR, "HAM10000_metadata.csv")
    rows = list(csv.DictReader(open(meta_path, encoding="utf-8")))
    print(f"[1/6] 读取元数据: {len(rows)} 条")

    # 建立 病灶 → 类别 / 病灶 → 图片列表
    lesion_cls = {}
    lesion_images = defaultdict(list)
    img_path_map = {}
    for r in rows:
        lid, iid, dx = r["lesion_id"], r["image_id"], r["dx"]
        lesion_cls[lid] = dx
        lesion_images[lid].append(iid)
        img_path_map[iid] = f"{iid}.jpg"

    # 找图片真实路径（原始数据分 part_1 / part_2）
    img_files = {}
    for root, _, files in os.walk(RAW_DIR):
        for f in files:
            if f.endswith(".jpg"):
                img_files[f[:-4]] = os.path.join(root, f)
    print(f"      找到图片文件: {len(img_files)}")

    # ---------- 2. 按类别统计病灶 ----------
    by_cls_lesions = defaultdict(list)
    for lid, dx in lesion_cls.items():
        by_cls_lesions[dx].append(lid)

    print(f"\n[2/6] 病灶分布（共 {len(lesion_cls)} 个病灶）")
    for c in CLASSES:
        n_les = len(by_cls_lesions[c])
        n_img = sum(len(lesion_images[l]) for l in by_cls_lesions[c])
        print(f"      {c:8s} 病灶 {n_les:>5}  图片 {n_img:>5}")

    # ---------- 3. 按类别分层抽取测试病灶 ----------
    # 按各类别病灶数比例分配测试病灶（保证测试集类别覆盖）
    total_les = len(lesion_cls)
    ratio = args.n_test_lesions / total_les

    test_les, train_les = [], []
    for c in CLASSES:
        les = sorted(by_cls_lesions[c])
        rng.shuffle(les)
        # 每类至少留 1 个测试病灶（若样本够）
        n_test = max(1, int(round(len(les) * ratio))) if len(les) >= 5 else 0
        n_test = min(n_test, max(0, len(les) - 1))     # 至少留 1 个训练
        test_les.extend(les[:n_test])
        train_les.extend(les[n_test:])

    test_les = sorted(test_les)
    train_les = sorted(train_les)

    # ---------- 4. 校验无泄漏 ----------
    leak = set(train_les) & set(test_les)
    assert len(leak) == 0, f"数据泄漏！交集 {len(leak)}"
    print(f"\n[3/6] 病灶级划分校验")
    print(f"      训练病灶: {len(train_les)}")
    print(f"      测试病灶: {len(test_les)}")
    print(f"      病灶交集: {len(leak)} ✅")

    # ---------- 5. 硬链接图片 ----------
    print(f"\n[4/6] 链接图片（方式: {args.link}）")
    if os.path.exists(args.out):
        import shutil
        shutil.rmtree(args.out)

    def do_link(src, dst):
        if args.link == "hard":
            os.link(src, dst)
        elif args.link == "symlink":
            os.symlink(os.path.abspath(src), dst)
        else:
            import shutil
            shutil.copy2(src, dst)

    stats = defaultdict(lambda: defaultdict(int))
    missing = []
    for split, lesions in [("train", train_les), ("test", test_les)]:
        for lid in lesions:
            c = lesion_cls[lid]
            for iid in lesion_images[lid]:
                src = img_files.get(iid)
                if not src:
                    missing.append(iid)
                    continue
                d = os.path.join(args.out, split, c)
                os.makedirs(d, exist_ok=True)
                do_link(src, os.path.join(d, img_path_map[iid]))
                stats[split][c] += 1

    if missing:
        print(f"      ⚠️ 缺失图片 {len(missing)} 张（已跳过）")

    # ---------- 6. 类别权重 ----------
    tr_counts = [stats["train"][c] for c in CLASSES]
    n_total = sum(tr_counts)
    weights = [n_total / (len(CLASSES) * cnt) if cnt > 0 else 0.0 for cnt in tr_counts]

    print(f"\n[5/6] 训练集类别分布与权重")
    print(f"      {'类别':<10} {'图片数':>7} {'占比':>8} {'权重':>8}")
    for c, cnt, w in zip(CLASSES, tr_counts, weights):
        print(f"      {c:<10} {cnt:>7} {cnt/n_total*100:>7.1f}% {w:>8.4f}")

    # ---------- 7. 保存元信息 ----------
    info = {
        "seed": args.seed,
        "classes": CLASSES,
        "class_cn": CLASS_CN,
        "class_group": CLASS_GROUP,
        "class_weights": {c: round(w, 6) for c, w in zip(CLASSES, weights)},
        "train_lesions": train_les,
        "test_lesions": test_les,
        "stats": {s: dict(stats[s]) for s in ("train", "test")},
        "n_train": sum(stats["train"].values()),
        "n_test": sum(stats["test"].values()),
    }
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "split_info_7class.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    # 可读报告
    lines = [
        "7 类分类数据集报告",
        "=" * 60,
        f"随机种子     : {args.seed}",
        f"链接方式     : {args.link}",
        f"训练集图片   : {info['n_train']}",
        f"测试集图片   : {info['n_test']}",
        f"训练集病灶   : {len(train_les)}",
        f"测试集病灶   : {len(test_les)}",
        f"病灶级交集   : {len(leak)} (应为0)",
        "",
        "训练集类别分布:",
    ]
    for c, cnt in zip(CLASSES, tr_counts):
        lines.append(f"  {c:8s} ({CLASS_CN[c]:16s}) {cnt:>6} 张 {cnt/n_total*100:>6.1f}%  权重={info['class_weights'][c]:.4f}")
    lines += ["", "测试集类别分布:"]
    for c in CLASSES:
        lines.append(f"  {c:8s} ({CLASS_CN[c]:16s}) {stats['test'][c]:>6} 张")
    lines += [
        "",
        "数据泄漏校验:",
        f"  病灶级交集 = {len(leak)} ✅",
        "",
        "说明:",
        "  1. 图片使用硬链接，不额外占用磁盘",
        "  2. 病灶级划分，同一 lesion_id 的图片不跨集",
        "  3. 类别权重用于 CrossEntropyLoss 处理不平衡",
    ]
    with open(os.path.join(args.out, "dataset_report_7class.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n[6/6] 完成")
    print(f"      输出目录: {args.out}")
    print(f"      训练集: {info['n_train']} 张 | 测试集: {info['n_test']} 张")
    print(f"      病灶交集: {len(leak)} ✅")
    print(f"\n类别权重（供训练使用）:")
    print(f"      {[round(w,4) for w in weights]}")


if __name__ == "__main__":
    main()
