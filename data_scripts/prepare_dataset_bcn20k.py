#!/usr/bin/env python3
"""
BCN20000 → 项目二分类数据集 转换脚本

输入:
  · BCN20000 zip 解压后的图片目录（BCN_20k_test/... 或扁平 jpg）
  · 官方元数据 CSV: bcn20000_metadata_2024-01-25.csv

输出:
  dataset/processed_bcn20k/{train,test}/{benign,malignant}/*.jpg
  + dataset/processed_bcn20k/dataset_report_bcn.txt
  + dataset/processed_bcn20k/split_info_bcn.json

关键设计:
  1. 从 diagnosis 推断 benign_malignant（43% 空标签靠这个补全）
  2. 按 lesion_id 病灶级划分（防泄漏，同病灶不同图不跨集）
  3. 硬链接（不额外占盘，跨盘自动降级 copy2）
  4. 测试集锁定为固定比例 + 固定种子，保证可复现

用法:
  python3 prepare_dataset_bcn20k.py --images <解压目录> --meta <csv> --out <输出目录>
  python3 prepare_dataset_bcn20k.py --images ... --meta ... --test-ratio 0.2 --seed 42
"""
import os
import sys
import csv
import json
import random
import shutil
import argparse
from collections import defaultdict

# ==================== 配置 ====================
# diagnosis → 二分类映射（BCN20000 的 9 个类别）
DX_TO_BINARY = {
    # ---- 恶性 ----
    "melanoma": "malignant",
    "basal cell carcinoma": "malignant",
    "squamous cell carcinoma": "malignant",
    "actinic keratosis": "malignant",          # 光化性角化 = 原位鳞癌/癌前
    # ---- 良性 ----
    "nevus": "benign",
    "seborrheic keratosis": "benign",
    "solar lentigo": "benign",
    "dermatofibroma": "benign",
    "vascular lesion": "benign",
}
# 优先用元数据里的 benign_malignant 列；空的话用 DX_TO_BINARY 推断
DX_CN = {
    "melanoma": "黑色素瘤",
    "basal cell carcinoma": "基底细胞癌",
    "squamous cell carcinoma": "鳞状细胞癌",
    "actinic keratosis": "光化性角化(原位鳞癌)",
    "nevus": "黑色素细胞痣",
    "seborrheic keratosis": "脂溢性角化",
    "solar lentigo": "日光性黑子",
    "dermatofibroma": "皮肤纤维瘤",
    "vascular lesion": "血管性病变",
}


def log(msg, fh=None):
    print(msg)
    if fh:
        fh.write(msg + "\n")


def find_images(root):
    """递归找出所有 jpg/png，返回 {isic_id: path}"""
    found = {}
    n = 0
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith((".jpg", ".jpeg", ".png")):
                # BCN_0000000123.jpg → ISIC_0000000123? 不，BCN 文件名就是 BCN_xxx
                stem = os.path.splitext(fn)[0]
                found[stem] = os.path.join(dirpath, fn)
                n += 1
    return found, n


def resolve_label(row):
    """返回 'benign' / 'malignant' / None"""
    bm = (row.get("benign_malignant") or "").strip().lower()
    if bm in ("benign", "malignant"):
        return bm
    dx = (row.get("diagnosis") or "").strip().lower()
    return DX_TO_BINARY.get(dx)


def link_or_copy(src, dst):
    """硬链接优先，跨盘降级复制"""
    try:
        os.link(src, dst)
        return "link"
    except (OSError, NotImplementedError):
        shutil.copy2(src, dst)
        return "copy"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True, help="BCN20000 图片根目录（解压后）")
    ap.add_argument("--meta", required=True, help="官方元数据 CSV 路径")
    ap.add_argument("--out", default="dataset/processed_bcn20k", help="输出目录")
    ap.add_argument("--test-ratio", type=float, default=0.2, help="测试集病灶占比")
    ap.add_argument("--seed", type=int, default=42, help="随机种子")
    ap.add_argument("--max-per-lesion-train", type=int, default=0,
                    help="训练集每病灶最多取几张（0=不限，可用来控不平衡）")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    report_path = os.path.join(args.out, "dataset_report_bcn.txt")
    rf = open(report_path, "w", encoding="utf-8")

    log("=" * 74, rf)
    log("BCN20000 → 二分类数据集转换", rf)
    log("=" * 74, rf)
    log(f"图片目录: {args.images}", rf)
    log(f"元数据  : {args.meta}", rf)
    log(f"输出    : {args.out}", rf)
    log(f"划分    : 病灶级 {1-args.test_ratio:.0%}:{args.test_ratio:.0%}  seed={args.seed}", rf)
    log(f"训练集每病灶上限: {args.max_per_lesion_train or '不限'}", rf)
    log("", rf)

    # ---------- 1. 读元数据 ----------
    rows = list(csv.DictReader(open(args.meta, encoding="utf-8-sig")))
    log(f"[1] 元数据 {len(rows)} 条", rf)

    # ---------- 2. 建索引：isic_id / 文件名前缀 → 元数据 ----------
    by_isic = {}
    by_stem = {}
    for r in rows:
        iid = (r.get("isic_id") or "").strip()
        if iid:
            by_isic[iid] = r
            # BCN20000 官方图片名形如 BCN_0000123456.jpg，
            # 而元数据 isic_id 形如 ISIC_0053454 —— 需要靠映射。
            by_stem[iid] = r

    log(f"[2] 元数据索引: {len(by_isic)} 个 isic_id", rf)

    # ---------- 3. 扫描图片 ----------
    imgs, n_img = find_images(args.images)
    log(f"[3] 扫描到 {n_img} 张图片（唯一名 {len(imgs)}）", rf)
    if n_img == 0:
        log("❌ 没找到图片，检查 --images 路径", rf)
        rf.close()
        sys.exit(1)

    # ---------- 4. 匹配 + 打标签 ----------
    matched = []          # [(path, label, lesion_id, isic_id, dx)]
    unmatched_names = []
    unlabeled = []
    used_lesion_ids = set()

    for stem, path in sorted(imgs.items()):
        r = by_isic.get(stem) or by_stem.get(stem)
        if r is None:
            unmatched_names.append(stem)
            continue
        label = resolve_label(r)
        if label is None:
            unlabeled.append((stem, r.get("diagnosis")))
            continue
        # lesion_id 兜底：没有就用 isic_id（每图独立，保守但不会泄漏）
        lid = (r.get("lesion_id") or "").strip() or f"SOLO_{r.get('isic_id')}"
        matched.append((path, label, lid, r.get("isic_id"), (r.get("diagnosis") or "").strip()))
        used_lesion_ids.add(lid)

    log(f"[4] 成功匹配并打标签: {len(matched)} 张", rf)
    log(f"    未匹配到元数据: {len(unmatched_names)} 张", rf)
    log(f"    有元数据但无法定标签: {len(unlabeled)} 张", rf)
    if unmatched_names[:5]:
        log(f"    (未匹配示例: {unmatched_names[:5]})", rf)
    if unlabeled[:5]:
        log(f"    (无法定标签示例: {unlabeled[:5]})", rf)
    log("", rf)

    if not matched:
        log("❌ 一张都没匹配上！文件名与 isic_id 的对应关系需要人工确认。", rf)
        log("   请检查图片名与 CSV 里的 isic_id 是否同一套命名。", rf)
        rf.close()
        sys.exit(1)

    # ---------- 5. 病灶级划分 ----------
    by_label_lesion = defaultdict(set)   # label -> {lesion_id}
    for _, label, lid, _, _ in matched:
        by_label_lesion[label].add(lid)

    rng = random.Random(args.seed)
    test_lesions = set()
    train_lesions = set()
    for label, lesions in by_label_lesion.items():
        ls = sorted(lesions)
        rng.shuffle(ls)
        n_test = max(1, int(round(len(ls) * args.test_ratio)))
        test_lesions.update(ls[:n_test])
        train_lesions.update(ls[n_test:])

    log("[5] 病灶级划分", rf)
    log(f"    训练病灶 {len(train_lesions)} | 测试病灶 {len(test_lesions)}", rf)
    log(f"    ⚠️ 交集: {len(train_lesions & test_lesions)} (必须为 0)", rf)
    log("", rf)

    # ---------- 6. 落盘 ----------
    stats = defaultdict(lambda: {"lesions": set(), "images": 0})
    links = {"link": 0, "copy": 0}
    skipped_multi = 0
    per_lesion_train_count = defaultdict(int)

    for path, label, lid, isic_id, dx in matched:
        split = "test" if lid in test_lesions else "train"
        # 训练集每病灶限量（可选）
        if split == "train" and args.max_per_lesion_train > 0:
            if per_lesion_train_count[lid] >= args.max_per_lesion_train:
                skipped_multi += 1
                continue
            per_lesion_train_count[lid] += 1

        outdir = os.path.join(args.out, split, label)
        os.makedirs(outdir, exist_ok=True)
        ext = os.path.splitext(path)[1].lower()
        dst = os.path.join(outdir, f"{isic_id}{ext}")
        if os.path.exists(dst):
            continue
        mode = link_or_copy(path, dst)
        links[mode] += 1
        stats[f"{split}/{label}"]["lesions"].add(lid)
        stats[f"{split}/{label}"]["images"] += 1

    log("[6] 输出统计", rf)
    for k in ["train/malignant", "train/benign", "test/malignant", "test/benign"]:
        s = stats.get(k, {"lesions": set(), "images": 0})
        log(f"    {k:<18} 病灶 {len(s['lesions']):>5} 个 → 图片 {s['images']:>5} 张", rf)
    log(f"    硬链接 {links['link']} / 复制 {links['copy']}", rf)
    if skipped_multi:
        log(f"    (训练集因每病灶限量跳过 {skipped_multi} 张)", rf)
    log("", rf)

    total_out = sum(s["images"] for s in stats.values())
    log(f"[7] 合计 {total_out} 张", rf)

    # ---------- 7. 自检 ----------
    tr_les = set()
    te_les = set()
    for k, s in stats.items():
        (tr_les if k.startswith("train") else te_les).update(s["lesions"])
    leak = tr_les & te_les
    log("", rf)
    log("[8] 数据泄漏自检", rf)
    log(f"    病灶级交集: {len(leak)}  {'✅ 通过' if not leak else '❌ 失败！'}", rf)

    # 图片名交集（应该也不重合）
    tr_imgs, te_imgs = set(), set()
    for split, bag in (("train", tr_imgs), ("test", te_imgs)):
        d = os.path.join(args.out, split)
        for lab in ("benign", "malignant"):
            dd = os.path.join(d, lab)
            if os.path.isdir(dd):
                bag.update(os.listdir(dd))
    img_leak = tr_imgs & te_imgs
    log(f"    图片级交集: {len(img_leak)}  {'✅ 通过' if not img_leak else '❌ 失败！'}", rf)

    # ---------- 8. 保存 split_info ----------
    info = {
        "version": "bcn20k",
        "source": "BCN20000 (Kaggle: pasutchien/bcn20000)",
        "license": "CC-BY-NC (原数据集)",
        "seed": args.seed,
        "test_ratio": args.test_ratio,
        "dx_to_binary": DX_TO_BINARY,
        "dx_cn": DX_CN,
        "stats": {k: {"lesions": len(v["lesions"]), "images": v["images"]}
                  for k, v in stats.items()},
        "total_images": total_out,
        "leakage_check": {"lesion": len(leak), "image": len(img_leak)},
        "test_lesions": sorted(test_lesions),
    }
    json.dump(info, open(os.path.join(args.out, "split_info_bcn.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=2)

    log("", rf)
    log(f"已保存: {os.path.join(args.out, 'split_info_bcn.json')}", rf)
    log(f"已保存: {report_path}", rf)
    rf.close()


if __name__ == "__main__":
    main()
