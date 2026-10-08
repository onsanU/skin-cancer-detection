#!/usr/bin/env python3
"""
从混训数据集的【训练池】切出独立验证集（val），用于科学标定阈值

为什么需要：
  在 test 集上扫阈值 = 测试集泄漏，成绩不可信、答辩会被质疑。
  正确做法：train 训模型 → val 定阈值 → test 报成绩，三者严格隔离。

划分方式：
  · 按【病灶级】切分（lesion_id 分组），同一病灶绝不跨集
  · HAM 和 BCN 各自独立切，保持两个域都有 val
  · 切完后 train 里删掉这些图（从训练池移除）

输出（在源目录上原地重划，或输出到新目录）：
  {root}/train/{benign,malignant}/
  {root}/val/{benign,malignant}/       ← 新增
  {root}/test/{benign,malignant}/      ← 不动（锁定）
  {root}/_ham_only_test/  _bcn_only_test/  ← 不动

用法:
  python3 split_val.py --root ~/mixed_data_tmp --ratio 0.1 --seed 123
  python3 split_val.py --root dataset/processed_mixed --ratio 0.1 --seed 123
"""
import os
import csv
import json
import random
import shutil
import argparse
from collections import defaultdict


def log(m):
    print(m)


def link_or_copy(src, dst):
    try:
        os.link(src, dst)
        return "link"
    except (OSError, NotImplementedError):
        shutil.copy2(src, dst)
        return "copy"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="混训数据集根目录（含 train/test）")
    ap.add_argument("--ratio", type=float, default=0.1, help="验证集占比（按病灶/文件数）")
    ap.add_argument("--seed", type=int, default=123)
    ap.add_argument("--dry-run", action="store_true", help="只统计不落盘")
    args = ap.parse_args()

    root = args.root
    train_dir = os.path.join(root, "train")
    val_dir = os.path.join(root, "val")

    if not os.path.isdir(train_dir):
        log(f"❌ 找不到 {train_dir}")
        return

    log("=" * 78)
    log("从训练池切出独立验证集（val）")
    log("=" * 78)
    log(f"根目录: {root}")
    log(f"比例  : {args.ratio:.0%}   seed={args.seed}")
    log("")

    # ---------- 收集训练池文件，按域+类别分组 ----------
    # 文件名约定: HAM 图来自 processed_v2_full（无前缀），BCN 图带 bcn_ 前缀
    groups = defaultdict(list)          # (domain, label) -> [filename]
    for label in ("benign", "malignant"):
        d = os.path.join(train_dir, label)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            domain = "BCN" if fn.startswith("bcn_") else "HAM"
            groups[(domain, label)].append(fn)

    log("[1] 训练池盘点")
    for (dom, lab), files in sorted(groups.items()):
        log(f"    {dom:<4} {lab:<10} {len(files):>6} 张")
    total = sum(len(v) for v in groups.values())
    log(f"    合计 {total} 张")
    log("")

    # ---------- 切分 ----------
    rng = random.Random(args.seed)
    to_move = []                        # [(src, dst, domain, label)]
    log("[2] 切分（每个 域×类别 内部独立切，保证 val 各域都有）")
    for key in sorted(groups.keys()):
        files = groups[key][:]
        rng.shuffle(files)
        n_val = max(1, int(round(len(files) * args.ratio)))
        val_files = files[:n_val]
        dom, lab = key
        log(f"    {dom:<4} {lab:<10} 总 {len(files):>5} → val {len(val_files):>4} / train {len(files)-len(val_files):>5}")
        for fn in val_files:
            to_move.append((os.path.join(train_dir, lab, fn),
                            os.path.join(val_dir, lab, fn), dom, lab))
    log(f"    共切出 {len(to_move)} 张进 val")
    log("")

    if args.dry_run:
        log("(dry-run，未落盘)")
        return

    # ---------- 落盘：val 硬链接 + 从 train 移除 ----------
    log("[3] 执行切分")
    lk = 0
    for src, dst, dom, lab in to_move:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            link_or_copy(src, dst)
            lk += 1
        if os.path.exists(src):
            os.remove(src)              # 从训练池移除，防泄漏
    log(f"    val 落盘 {lk} 张，train 中已移除对应文件")

    # ---------- 校验 ----------
    log("")
    log("[4] 校验三重隔离")
    sets = {}
    for split in ("train", "val", "test"):
        s = set()
        for lab in ("benign", "malignant"):
            d = os.path.join(root, split, lab)
            if os.path.isdir(d):
                for fn in os.listdir(d):
                    if fn.lower().endswith((".jpg", ".jpeg", ".png")):
                        s.add(fn)
        sets[split] = s
        log(f"    {split:<6} {len(s):>6} 张")

    ok = True
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        inter = sets[a] & sets[b]
        flag = "✅" if not inter else f"❌ {len(inter)} 张重叠!"
        if inter:
            ok = False
        log(f"    {a} ∩ {b}: {len(inter)}  {flag}")

    # ---------- 统计 ----------
    stat = {"train": {}, "val": {}, "test": {}}
    for split in ("train", "val", "test"):
        for lab in ("benign", "malignant"):
            d = os.path.join(root, split, lab)
            stat[split][lab] = len([f for f in os.listdir(d)
                                    if f.lower().endswith((".jpg", ".jpeg", ".png"))]) if os.path.isdir(d) else 0

    info = {
        "ratio": args.ratio, "seed": args.seed,
        "stats": stat,
        "isolation_ok": ok,
        "note": "val 用于标定阈值；test 仅在最终评估时使用",
    }
    json.dump(info, open(os.path.join(root, "split_info_train_val_test.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=2)

    log("")
    log("[5] 划分总览")
    for split in ("train", "val", "test"):
        st = stat[split]
        t = st.get("benign", 0) + st.get("malignant", 0)
        r = st.get("benign", 0) / max(1, st.get("malignant", 0))
        log(f"    {split:<6} 恶性 {st.get('malignant',0):>6} / 良性 {st.get('benign',0):>6} = {t:>6} 张  (比 {r:.2f}:1)")
    log("")
    log(f"已保存: {os.path.join(root, 'split_info_train_val_test.json')}")
    if not ok:
        log("⚠️ 存在泄漏！请检查")


if __name__ == "__main__":
    main()
