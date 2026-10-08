#!/usr/bin/env python3
"""
HAM10000 + BCN20000 混训数据集构建

设计目标：
  · 让 train_resnet50.py 【零改动】就能用（输出标准 {root}/{split}/{class}/*.jpg 结构）
  · 测试集【保持 HAM 原测试集不变】→ 与历史实验可比（这是加分关键！）
  · 额外导出 BCN 测试子集 → 用于跨域验证（证明泛化能力）

三种测试集策略（--test-mode）：
  ham     : 测试集 = HAM 原 213 张（与历史实验可比）★默认
  ham+bcn : 测试集 = HAM 213 + BCN 抽样（综合评估）
  bcn     : 测试集 = 纯 BCN（纯跨域）

关键设计：
  · BCN 训练池【排除】BCN 测试病灶（防泄漏）
  · HAM 测试集锁定复用 v1/v2 的 split_info → 历史可比
  · 硬链接落盘（几乎不占额外空间）
  · 内置双重泄漏自检

用法:
  python3 prepare_dataset_mixed.py \
      --ham dataset/processed_v2_full \
      --bcn-images dataset/BCN20000_raw \
      --bcn-meta /tmp/bcn20000_metadata_2024-01-25.csv \
      --out dataset/processed_mixed \
      --test-mode ham
"""
import os
import sys
import csv
import json
import random
import shutil
import argparse
from collections import defaultdict

DX_TO_BINARY = {
    "melanoma": "malignant",
    "basal cell carcinoma": "malignant",
    "squamous cell carcinoma": "malignant",
    "actinic keratosis": "malignant",
    "nevus": "benign",
    "seborrheic keratosis": "benign",
    "solar lentigo": "benign",
    "dermatofibroma": "benign",
    "vascular lesion": "benign",
}


def log(m, fh=None):
    print(m)
    if fh:
        fh.write(m + "\n")


def link_or_copy(src, dst):
    try:
        os.link(src, dst)
        return "link"
    except (OSError, NotImplementedError):
        shutil.copy2(src, dst)
        return "copy"


def resolve_bcn_label(row):
    bm = (row.get("benign_malignant") or "").strip().lower()
    if bm in ("benign", "malignant"):
        return bm
    return DX_TO_BINARY.get((row.get("diagnosis") or "").strip().lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ham", required=True, help="HAM 已处理数据集（含 train/test）")
    ap.add_argument("--bcn-images", required=True, help="BCN 图片目录")
    ap.add_argument("--bcn-meta", required=True, help="BCN 元数据 CSV")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--test-mode", default="ham", choices=["ham", "ham+bcn", "bcn"])
    ap.add_argument("--bcn-test-lesions", type=int, default=0,
                    help="BCN 测试集病灶数（0=按 test-ratio 自动）")
    ap.add_argument("--test-ratio", type=float, default=0.2,
                    help="BCN 测试病灶占比（test-mode=ham+bcn/bcn 时生效）")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-train-bcn", type=int, default=0,
                    help="BCN 训练集最多用多少张（0=全部，用于控制磁盘/时间）")
    ap.add_argument("--confirm-only", action="store_true",
                    help="只保留组织病理确诊(histopathology)的 BCN 样本（标签最可靠，9548张）")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rp = os.path.join(args.out, "dataset_report_mixed.txt")
    rf = open(rp, "w", encoding="utf-8")

    log("=" * 78, rf)
    log("HAM10000 + BCN20000 混训数据集构建", rf)
    log("=" * 78, rf)
    log(f"HAM 源 : {args.ham}", rf)
    log(f"BCN 图 : {args.bcn_images}", rf)
    log(f"BCN 元 : {args.bcn_meta}", rf)
    log(f"输出   : {args.out}", rf)
    log(f"测试模式: {args.test_mode}   seed={args.seed}", rf)
    log("", rf)

    stats = defaultdict(lambda: {"images": 0, "lesions": set()})
    lk = {"link": 0, "copy": 0}

    # ==================== 1. HAM 训练集 ====================
    log("[1] 复制 HAM 训练集", rf)
    ham_train_n = 0
    for lab in ("benign", "malignant"):
        d = os.path.join(args.ham, "train", lab)
        if not os.path.isdir(d):
            continue
        outdir = os.path.join(args.out, "train", lab)
        os.makedirs(outdir, exist_ok=True)
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            dst = os.path.join(outdir, fn)
            if os.path.exists(dst):
                continue
            mode = link_or_copy(os.path.join(d, fn), dst)
            lk[mode] += 1
            stats[f"train/{lab}"]["images"] += 1
            ham_train_n += 1
        stats[f"train/{lab}"]["lesions"].add("HAM:" + lab)   # 标记用

    log(f"    HAM 训练: {stats['train/malignant']['images']} 恶性 + "
        f"{stats['train/benign']['images']} 良性 = {ham_train_n} 张", rf)
    log("", rf)

    # ==================== 2. HAM 测试集 ====================
    ham_test_lesions = set()
    ham_test_n = 0
    log("[2] 复制 HAM 测试集（锁定，与历史可比）", rf)
    for lab in ("benign", "malignant"):
        d = os.path.join(args.ham, "test", lab)
        if not os.path.isdir(d):
            continue
        outdir = os.path.join(args.out, "test", lab)
        os.makedirs(outdir, exist_ok=True)
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            dst = os.path.join(outdir, fn)
            if not os.path.exists(dst):
                mode = link_or_copy(os.path.join(d, fn), dst)
                lk[mode] += 1
            stats[f"test/{lab}"]["images"] += 1
            ham_test_n += 1
            ham_test_lesions.add("H:" + os.path.splitext(fn)[0])
    log(f"    HAM 测试: {ham_test_n} 张", rf)
    log("", rf)

    # ==================== 3. BCN 读元数据 + 匹配图 ====================
    log("[3] 处理 BCN20000", rf)
    rows = list(csv.DictReader(open(args.bcn_meta, encoding="utf-8-sig")))
    bcn = []            # (path, label, lesion_id, isic_id)
    missing = unlabeled = filtered = 0
    for r in rows:
        iid = (r.get("isic_id") or "").strip()
        if not iid:
            continue
        # 可选：只保留组织病理确诊（标签最可靠）
        if args.confirm_only:
            ct = (r.get("diagnosis_confirm_type") or "").strip().lower()
            if ct != "histopathology":
                filtered += 1
                continue
        p = os.path.join(args.bcn_images, f"{iid}.jpg")
        if not os.path.exists(p):
            missing += 1
            continue
        lab = resolve_bcn_label(r)
        if lab is None:
            unlabeled += 1
            continue
        lid = (r.get("lesion_id") or "").strip() or f"SOLO_{iid}"
        bcn.append((p, lab, lid, iid))
    log(f"    元数据 {len(rows)} 条 → 可用图片 {len(bcn)} 张"
        f"（缺图 {missing}, 无标签 {unlabeled}, 被confirm-only过滤 {filtered}）", rf)
    if not bcn:
        log("❌ BCN 可用图片为 0！检查 --bcn-images 路径与下载是否完成", rf)
        rf.close()
        sys.exit(1)

    n_b = sum(1 for x in bcn if x[1] == "benign")
    n_m = sum(1 for x in bcn if x[1] == "malignant")
    log(f"    BCN 良恶性: 良性 {n_b} / 恶性 {n_m}  (比例 {n_b/max(1,n_m):.2f}:1)", rf)

    # ==================== 4. BCN 病灶级划分 ====================
    by_lab_lesion = defaultdict(set)
    for _, lab, lid, _ in bcn:
        by_lab_lesion[lab].add(lid)
    rng = random.Random(args.seed)
    bcn_test_lesions = set()
    if args.test_mode in ("ham+bcn", "bcn"):
        for lab, les in by_lab_lesion.items():
            ls = sorted(les)
            rng.shuffle(ls)
            if args.bcn_test_lesions > 0:
                n_test = min(args.bcn_test_lesions // 2, len(ls) // 5)  # 每类一半
            else:
                n_test = max(1, int(round(len(ls) * args.test_ratio)))
            bcn_test_lesions.update(ls[:n_test])
    log(f"    BCN 测试病灶: {len(bcn_test_lesions)} 个（其余进训练池）", rf)
    log("", rf)

    # ==================== 5. BCN 训练集（排除测试病灶）====================
    bcn_train = [(p, lab, lid, iid) for p, lab, lid, iid in bcn
                 if lid not in bcn_test_lesions]
    if args.max_train_bcn > 0 and len(bcn_train) > args.max_train_bcn:
        rng.shuffle(bcn_train)
        bcn_train = bcn_train[:args.max_train_bcn]
    log(f"[4] BCN 训练集: {len(bcn_train)} 张", rf)
    for p, lab, lid, iid in bcn_train:
        outdir = os.path.join(args.out, "train", lab)
        os.makedirs(outdir, exist_ok=True)
        # 加 bcn_ 前缀避免与 HAM 重名
        dst = os.path.join(outdir, f"bcn_{iid}.jpg")
        if os.path.exists(dst):
            continue
        mode = link_or_copy(p, dst)
        lk[mode] += 1
        stats[f"train/{lab}"]["images"] += 1
        stats[f"train/{lab}"]["lesions"].add("BCN:" + lid)
    log("", rf)

    # ==================== 6. BCN 测试集 ====================
    bcn_test = [(p, lab, lid, iid) for p, lab, lid, iid in bcn
                if lid in bcn_test_lesions]
    if args.test_mode in ("ham+bcn", "bcn") and bcn_test:
        subdir = "test" if args.test_mode == "ham+bcn" else "test"
        log(f"[5] BCN 测试集: {len(bcn_test)} 张", rf)
        for p, lab, lid, iid in bcn_test:
            outdir = os.path.join(args.out, subdir, lab)
            os.makedirs(outdir, exist_ok=True)
            dst = os.path.join(outdir, f"bcn_{iid}.jpg")
            if not os.path.exists(dst):
                mode = link_or_copy(p, dst)
                lk[mode] += 1
            stats[f"{subdir}/{lab}"]["images"] += 1
            stats[f"{subdir}/{lab}"]["lesions"].add("BCN:" + lid)
        log("", rf)

    # 额外导出一份「纯 BCN 测试清单」用于跨域验证
    bcn_only_dir = os.path.join(args.out, "_bcn_only_test")
    if bcn_test:
        log(f"[6] 额外导出 BCN-only 测试清单（跨域验证用）→ {bcn_only_dir}", rf)
        for p, lab, lid, iid in bcn_test:
            outdir = os.path.join(bcn_only_dir, lab)
            os.makedirs(outdir, exist_ok=True)
            dst = os.path.join(outdir, f"bcn_{iid}.jpg")
            if not os.path.exists(dst):
                link_or_copy(p, dst)
        log(f"    {len(bcn_test)} 张", rf)
    log("", rf)

    # ==================== 7. 统计 ====================
    log("[7] 输出统计", rf)
    for k in ["train/malignant", "train/benign", "test/malignant", "test/benign"]:
        s = stats.get(k, {"images": 0, "lesions": set()})
        log(f"    {k:<18} {s['images']:>6} 张", rf)
    log(f"    硬链接 {lk['link']} / 复制 {lk['copy']}", rf)
    total = sum(s["images"] for s in stats.values())
    log(f"    合计 {total} 张", rf)
    log("", rf)

    # ==================== 8. 泄漏自检 ====================
    log("[8] 数据泄漏自检", rf)
    tr_imgs, te_imgs = set(), set()
    for split, bag in (("train", tr_imgs), ("test", te_imgs)):
        for lab in ("benign", "malignant"):
            d = os.path.join(args.out, split, lab)
            if os.path.isdir(d):
                bag.update(os.listdir(d))
    leak = tr_imgs & te_imgs
    log(f"    图片级交集: {len(leak)}  {'✅ 通过' if not leak else '❌ 失败'}", rf)

    # BCN 病灶级
    tr_les = set()
    te_les = set()
    for p, lab, lid, iid in bcn_train:
        tr_les.add(lid)
    for p, lab, lid, iid in bcn_test:
        te_les.add(lid)
    bcn_leak = tr_les & te_les
    log(f"    BCN 病灶级交集: {len(bcn_leak)}  {'✅ 通过' if not bcn_leak else '❌ 失败'}", rf)
    log("", rf)

    info = {
        "version": "mixed_ham_bcn",
        "ham_source": args.ham,
        "bcn_source": "BCN20000 via ISIC S3",
        "test_mode": args.test_mode,
        "seed": args.seed,
        "stats": {k: v["images"] for k, v in stats.items()},
        "total_images": total,
        "ham_test_locked": ham_test_n,
        "bcn_train_images": len(bcn_train),
        "bcn_test_images": len(bcn_test),
        "leakage_check": {"image": len(leak), "bcn_lesion": len(bcn_leak)},
    }
    json.dump(info, open(os.path.join(args.out, "split_info_mixed.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"已保存: {os.path.join(args.out, 'split_info_mixed.json')}", rf)
    log(f"已保存: {rp}", rf)
    rf.close()


if __name__ == "__main__":
    main()
