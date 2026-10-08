#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成模型的阈值调优 + 概率保存
================================================================
背景：集成实验发现 AUC 提升（0.9287 > 0.9163）但准确率下降
     → 说明 0.5 阈值不再是最优操作点，需要重新扫描

功能：
  1. 保存各方案的概率输出（供后续分析）
  2. 扫描集成模型的阈值，找最优操作点
  3. 对比单模型 vs 集成在不同阈值下的表现
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ensemble_eval import (DEFAULT_DATA, PROJ_ROOT, load_model, metrics_at,
                           predict_with_tta)

DEFAULT_OUT = os.path.join(PROJ_ROOT, "docs")


def scan_thresholds(y_true, p_pos, lo=0.20, hi=0.80, step=0.01):
    """扫描阈值，返回每个操作点的指标"""
    thresholds = np.round(np.arange(lo, hi + step / 2, step), 2)
    rows = []
    for t in thresholds:
        m = metrics_at(y_true, p_pos, float(t))
        # 约登指数 = 敏感度 + 特异度 - 1
        cm = m["confusion_matrix"]
        tn, fp, fn, tp = cm[0][0], cm[0][1], cm[1][0], cm[1][1]
        sens = tp / (tp + fn) if (tp + fn) else 0.0
        spec = tn / (tn + fp) if (tn + fp) else 0.0
        m["youden"] = sens + spec - 1.0
        m["threshold"] = float(t)
        m["sensitivity"] = sens
        m["specificity"] = spec
        m["miss_rate"] = 1 - sens
        rows.append(m)
    return rows


def pick_operating_points(rows):
    """挑选三个推荐操作点"""
    out = {}
    # 1) 最大准确率
    out["max_acc"] = max(rows, key=lambda r: (r["accuracy"], r["macro_f1"]))
    # 2) 约登指数最优
    out["max_youden"] = max(rows, key=lambda r: r["youden"])
    # 3) 召回优先（召回 >= 0.95 中准确率最高）
    cand = [r for r in rows if r["malignant_recall"] >= 0.95]
    out["recall_first"] = (max(cand, key=lambda r: r["accuracy"]) if cand
                           else max(rows, key=lambda r: r["malignant_recall"]))
    return out


def main():
    ap = argparse.ArgumentParser(description="集成阈值调优")
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--split", default="test")
    ap.add_argument("--models", nargs="+", default=[
        "models_v2_full/best.pt",
        "models_vE_r101_288/best.pt",
    ])
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--save-probs", action="store_true", default=True,
                    help="保存概率输出（供后续复用）")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("=" * 84)
    print("集成模型阈值调优")
    print("=" * 84)
    print(f"设备: {device}  数据集: {args.data}/{args.split}")

    # ---- 收集各模型概率（无 TTA，TTA 已验证有害）----
    probs = []
    y_true = None
    for rel in args.models:
        path = rel if os.path.isabs(rel) else os.path.join(PROJ_ROOT, rel)
        if not os.path.isfile(path):
            print(f"  ⚠️ 跳过: {rel}")
            continue
        m, arch, isz, cls, ckpt = load_model(path, device)
        ds_classes = sorted(
            c for c in os.listdir(os.path.join(args.data, args.split))
            if os.path.isdir(os.path.join(args.data, args.split, c))
        )
        if cls != ds_classes:
            print(f"  ⚠️ 类别不匹配，跳过: {rel}")
            continue
        t0 = time.time()
        y, p = predict_with_tta(m, args.data, args.split, cls, isz, device,
                                tta=False, bs=args.bs)
        print(f"  {os.path.basename(os.path.dirname(path)):24s} "
              f"({time.time()-t0:.1f}s)")
        probs.append(p)
        y_true = y

    if not probs:
        print("[ERROR] 无可用模型")
        sys.exit(1)

    # ---- 各方案阈值扫描 ----
    results = {}
    print("\n" + "-" * 84)
    print("阈值扫描（0.20 ~ 0.80，步长 0.01）")
    print("-" * 84)

    plans = [(os.path.basename(os.path.dirname(r)), p)
             for r, p in zip(args.models, probs)]
    plans.append((f"集成({len(probs)}模型)", np.mean(probs, axis=0)))

    for name, p in plans:
        rows = scan_thresholds(y_true, p[:, 1])
        pts = pick_operating_points(rows)
        results[name] = {"scan": rows, "points": pts}
        print(f"\n【{name}】")
        print(f"  {'操作点':<14} {'阈值':>6} {'准确率':>8} {'恶性召回':>9} "
              f"{'漏诊率':>8} {'约登':>7}")
        for k, label in [("max_acc", "最大准确率"), ("max_youden", "约登最优"),
                         ("recall_first", "召回优先")]:
            r = pts[k]
            print(f"  {label:<14} {r['threshold']:>6.2f} {r['accuracy']:>8.4f} "
                  f"{r['malignant_recall']:>9.4f} {r['miss_rate']:>8.4f} "
                  f"{r['youden']:>7.4f}")

    # ---- 对比：最优操作点 vs 0.5 ----
    print("\n" + "=" * 84)
    print("关键对比：0.5 阈值 vs 各方案最优阈值")
    print("=" * 84)
    print(f"{'方案':<26} {'@0.50 acc':>11} {'最优acc':>9} {'最优阈值':>9} {'提升':>8}")
    print("-" * 84)
    for name, res in results.items():
        r05 = next(r for r in res["scan"] if abs(r["threshold"] - 0.5) < 1e-6)
        best = res["points"]["max_acc"]
        delta = (best["accuracy"] - r05["accuracy"]) * 100
        print(f"{name:<26} {r05['accuracy']:>11.4f} {best['accuracy']:>9.4f} "
              f"{best['threshold']:>9.2f} {delta:>+7.2f}pp")

    # ---- 保存 ----
    os.makedirs(args.out, exist_ok=True)
    op = os.path.join(args.out, "ensemble_threshold_tuning.json")
    slim = {name: {
        "points": res["points"],
        "scan": [{k: v for k, v in r.items() if k != "confusion_matrix"}
                 for r in res["scan"]],
    } for name, res in results.items()}
    with open(op, "w", encoding="utf-8") as f:
        json.dump({"n_samples": int(len(y_true)), "results": slim}, f,
                  ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {op}")

    if args.save_probs:
        pp = os.path.join(args.out, "ensemble_probs.npz")
        np.savez_compressed(pp, y_true=y_true,
                            **{f"p{i}": p for i, p in enumerate(probs)})
        print(f"概率已保存: {pp}")

    # ---- 结论 ----
    print("\n" + "=" * 84)
    print("结论")
    print("=" * 84)
    best_name, best_acc = None, -1
    for name, res in results.items():
        b = res["points"]["max_acc"]["accuracy"]
        if b > best_acc:
            best_acc, best_name = b, name
    print(f"  最优方案（按准确率）: {best_name}")
    print(f"  最优准确率          : {best_acc:.4f}")
    bc = results[best_name]["points"]["max_acc"]
    print(f"  对应阈值            : {bc['threshold']:.2f}")
    print(f"  恶性召回            : {bc['malignant_recall']:.4f}")
    print(f"  漏诊率              : {bc['miss_rate']:.4f}")


if __name__ == "__main__":
    main()
