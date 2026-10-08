#!/usr/bin/env python3
"""
从训练池切出验证集（val）—— 【严格按病灶级 lesion_id 切分】

⚠️ 血泪教训：之前用 split_val.py 按【文件名】切，导致同一病灶的照片
   被切到 train 和 val 两边 → 严重数据泄漏（777 个病灶重叠！）
   val 成绩虚高到 93%（真实只有 ~80%）

本脚本的正确做法：
   1. 读元数据建立 图片 → lesion_id 映射
   2. 按 lesion_id 分组，整组一起切（同病灶绝不跨集）
   3. 切完自检：病灶级交集必须为 0

用法:
  python3 split_val_by_lesion.py --data dataset/processed_v2_full \
      --meta dataset/HAM10000_raw/HAM10000_metadata.csv --ratio 0.1
"""
import os
import csv
import json
import random
import shutil
import argparse
from collections import defaultdict


def link_or_copy(s, d):
    try:
        os.link(s, d)
    except OSError:
        shutil.copy2(s, d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="数据集目录（含 train/，会新建 val/）")
    ap.add_argument("--meta", required=True, help="元数据 CSV（需含 image_id + lesion_id）")
    ap.add_argument("--ratio", type=float, default=0.1, help="验证集占比（按病灶数）")
    ap.add_argument("--seed", type=int, default=123)
    ap.add_argument("--balance", action="store_true",
                    help="val 良恶性按 1:1 平衡切（每类切相同病灶数），避免分布失配")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = args.data
    train_dir = os.path.join(root, "train")
    val_dir = os.path.join(root, "val")
    if not os.path.isdir(train_dir):
        print(f"❌ 找不到 {train_dir}")
        return

    print("=" * 84)
    print("按【病灶级】切分验证集（防泄漏）")
    print("=" * 84)

    # ---- 元数据: image_id → lesion_id ----
    id2les = {}
    for r in csv.DictReader(open(args.meta, encoding="utf-8-sig")):
        iid = (r.get("image_id") or "").strip()
        lid = (r.get("lesion_id") or "").strip()
        if iid:
            id2les[iid] = lid or f"SOLO_{iid}"
    print(f"元数据: {len(id2les)} 条 映射")

    # ---- 收集训练池文件，按 病灶+类别 分组 ----
    file2les = {}
    les2files = defaultdict(list)
    les_label = {}
    for lab in ("benign", "malignant"):
        d = os.path.join(train_dir, lab)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            iid = os.path.splitext(fn)[0]
            lid = id2les.get(iid, f"SOLO_{iid}")
            file2les[fn] = lid
            les2files[lid].append((fn, lab))
            les_label[lid] = lab

    n_files = sum(len(v) for v in les2files.values())
    print(f"训练池: {n_files} 张 / {len(les2files)} 个病灶")
    print(f"平均每病灶 {n_files/max(1,len(les2files)):.2f} 张")
    print()

    # ---- 按病灶切分（同一病灶整组走）----
    by_label = defaultdict(list)
    for lid, lab in les_label.items():
        by_label[lab].append(lid)

    rng = random.Random(args.seed)
    val_les = set()
    print("[切分] 每个类别内部按病灶切")

    if args.balance:
        # 平衡切：以【最少类别】的病灶数为基准，两类切相同数量
        min_n = min(len(v) for v in by_label.values())
        n_val_each = max(1, int(round(min_n * args.ratio)))
        for lab, les in sorted(by_label.items()):
            ls = sorted(les)
            rng.shuffle(ls)
            val_les.update(ls[:n_val_each])
            n_imgs = sum(len(les2files[l]) for l in ls[:n_val_each])
            print(f"  {lab:<12} 病灶 {len(ls):>5} → val {n_val_each:>4} 个病灶 ({n_imgs} 张, 平衡模式) / train {len(ls)-n_val_each:>5} 个")
    else:
        for lab, les in sorted(by_label.items()):
            ls = sorted(les)
            rng.shuffle(ls)
            n_val = max(1, int(round(len(ls) * args.ratio)))
            val_les.update(ls[:n_val])
            n_imgs = sum(len(les2files[l]) for l in ls[:n_val])
            print(f"  {lab:<12} 病灶 {len(ls):>5} → val {n_val:>4} 个病灶 ({n_imgs} 张) / train {len(ls)-n_val:>5} 个")

    # ---- 落盘 ----
    moved = 0
    if not args.dry_run:
        for lid in val_les:
            for fn, lab in les2files[lid]:
                src = os.path.join(train_dir, lab, fn)
                dst = os.path.join(val_dir, lab, fn)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if not os.path.exists(dst):
                    link_or_copy(src, dst)
                if os.path.exists(src):
                    os.remove(src)      # 从 train 移除
                moved += 1
        print(f"\n[落盘] val {moved} 张，已从 train 移除对应文件")
    else:
        print("\n(dry-run，未落盘)")

    # ---- 自检 ----
    print()
    print("[自检] 病灶级隔离")
    tr_les, va_les, te_les = set(), set(), set()
    for split, bag in (("train", tr_les), ("val", va_les), ("test", te_les)):
        d = os.path.join(root, split)
        if not os.path.isdir(d):
            continue
        for lab in ("benign", "malignant"):
            dd = os.path.join(d, lab)
            if not os.path.isdir(dd):
                continue
            for fn in os.listdir(dd):
                if not fn.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue
                iid = os.path.splitext(fn)[0]
                bag.add(id2les.get(iid, f"SOLO_{iid}"))

    ok = True
    for a, b, sa, sb in (("train", "val", tr_les, va_les),
                         ("train", "test", tr_les, te_les),
                         ("val", "test", va_les, te_les)):
        inter = sa.intersection(sb)
        flag = "✅" if not inter else f"❌ {len(inter)} 个病灶重叠!"
        if inter:
            ok = False
        print(f"  {a} ∩ {b}: {len(inter)}  {flag}")

    print()
    print("[统计]")
    for split in ("train", "val", "test"):
        d = os.path.join(root, split)
        if not os.path.isdir(d):
            continue
        nb = len([f for f in os.listdir(os.path.join(d, "benign"))
                  if f.lower().endswith(".jpg")]) if os.path.isdir(os.path.join(d, "benign")) else 0
        nm = len([f for f in os.listdir(os.path.join(d, "malignant"))
                  if f.lower().endswith(".jpg")]) if os.path.isdir(os.path.join(d, "malignant")) else 0
        print(f"  {split:<6} 良性 {nb:>5} / 恶性 {nm:>5} = {nb+nm:>5} 张")

    info = {"ratio": args.ratio, "seed": args.seed,
            "train_lesions": len(tr_les), "val_lesions": len(va_les),
            "test_lesions": len(te_les), "isolation_ok": ok,
            "method": "lesion-level split (防止同一病灶跨集泄漏)"}
    json.dump(info, open(os.path.join(root, "split_info_val.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n已保存: {os.path.join(root, 'split_info_val.json')}")
    print("隔离性:", "✅ 通过" if ok else "❌ 失败")


if __name__ == "__main__":
    main()
