#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证三档阈值设计：screening 0.20 / balanced 0.33 / accurate 0.48

流程同 threshold_calibrate_v3，但三档点由人工确定（基于 val 扫描曲线的形状），
只在 val 上读指标确认合理性，再在 test 上报成绩。
"""
import os, sys, json, argparse
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from threshold_calibrate_v3 import load_one, probs_of, metrics, auc_of  # noqa


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="dataset/processed_v2_full")
    ap.add_argument("--models", nargs="+",
                    default=["models_vE_r101_288/best.pt", "models_mix_cutmix_long/best.pt"])
    ap.add_argument("--weights", nargs="+", type=float, default=[1.0, 1.0])
    ap.add_argument("--presets", nargs="+", type=float, default=[0.20, 0.33, 0.48])
    ap.add_argument("--out", default="docs/threshold_v3_mix.json")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    names = ["screening", "balanced", "accurate"]

    loaded, classes, isz = [], None, None
    for pth, w in zip(args.models, args.weights):
        m, arch, cls, s = load_one(pth, device)
        loaded.append((m, w)); classes, isz = cls, s
        print(f"  加载 {pth}  arch={arch} img={s} w={w}")

    vp = tp = None
    for m, w in loaded:
        p, vy = probs_of(m, isz, classes, args.data, "val", device, workers=args.workers)
        vp = p * w if vp is None else vp + p * w
    vp = vp / sum(args.weights)
    for m, w in loaded:
        p, ty = probs_of(m, isz, classes, args.data, "test", device, workers=args.workers)
        tp = p * w if tp is None else tp + p * w
    tp = tp / sum(args.weights)

    print()
    print("=" * 78)
    print("三档验证  screening=%.2f  balanced=%.2f  accurate=%.2f" % tuple(args.presets))
    print("=" * 78)
    print("【val 326 张】")
    val_metrics = {}
    for nm, t in zip(names, args.presets):
        m = metrics(vy, vp, t)
        val_metrics[nm] = m
        print("  %-10s thr=%.2f  acc=%.4f  召回=%.4f  漏诊率=%.4f" %
              (nm, t, m["acc"], m["rec"], 1 - m["rec"]))
    print()
    print("【test 213 张】")
    test_metrics = {}
    for nm, t in zip(names, args.presets):
        m = metrics(ty, tp, t); test_metrics[nm] = m
        print("  %-10s thr=%.2f  acc=%.4f (%.2f%%)  召回=%.4f  精确=%.4f  F1=%.4f" %
              (nm, t, m["acc"], m["acc"] * 100, m["rec"], m["prec"], m["f1"]))
        print("              混淆矩阵 TN=%d FP=%d FN=%d TP=%d" % (m["tn"], m["fp"], m["fn"], m["tp"]))

    v_auc, t_auc = auc_of(vy, vp), auc_of(ty, tp)
    print()
    print("  AUC  val=%.4f  test=%.4f" % (v_auc, t_auc))

    # 单调性检查
    mono_thr = all(args.presets[i] < args.presets[i + 1] for i in range(len(args.presets) - 1))
    mono_rec = all(test_metrics[names[i]]["rec"] > test_metrics[names[i + 1]]["rec"]
                   for i in range(len(names) - 1))
    mono_acc = all(test_metrics[names[i]]["acc"] < test_metrics[names[i + 1]]["acc"]
                   for i in range(len(names) - 1))
    print()
    print("  单调性: 阈值递增=%s  召回递减=%s  准确率递增=%s" %
          ("✔" if mono_thr else "✘", "✔" if mono_rec else "✘", "✔" if mono_acc else "✘"))

    out = {
        "models": list(zip(args.models, args.weights)),
        "val_thresholds": dict(zip(names, args.presets)),
        "val_metrics": {k: {kk: float(vv) for kk, vv in v.items()} for k, v in val_metrics.items()},
        "test_metrics": {k: {kk: float(vv) for kk, vv in v.items()} for k, v in test_metrics.items()},
        "auc": {"val": float(v_auc), "test": float(t_auc)},
        "monotonic": {"thr": bool(mono_thr), "rec": bool(mono_rec), "acc": bool(mono_acc)},
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print()
    print("已保存:", args.out)


if __name__ == "__main__":
    main()
