#!/usr/bin/env python3
"""
阈值标定 + 最终测试（严谨三方流程）

正确流程：
  ① 用 val 集标定最优阈值（val 从未参与训练，也从未用于报成绩）
  ② 用标定好的阈值 → 去 test 集报最终成绩（test 全程未参与任何调参）

这样得到的 test 成绩是【无泄漏、可信】的，可以直接写进答辩。

同时输出：
  · val 标定阈值 vs test 扫出的最优阈值（差距小 = 标定可靠）
  · 分域成绩：HAM-only / BCN-only / 综合
  · 与历史模型对比

用法:
  python3 threshold_calibrate.py --model models_mixed_v2/best.pt --data ~/mixed_data_tmp
"""
import os
import sys
import json
import argparse

import numpy as np
import torch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from ensemble_eval import load_model, SkinDS, IMAGENET_MEAN, IMAGENET_STD
from torchvision import transforms
from torch.utils.data import DataLoader


def get_probs(model, img_size, data_root, split, device, bs=32, workers=8):
    tf = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    ds = SkinDS(data_root, split, tf, ["benign", "malignant"])
    if len(ds) == 0:
        return None, None
    dl = DataLoader(ds, batch_size=bs, shuffle=False, num_workers=workers)
    ps, ys = [], []
    with torch.no_grad():
        for x, y, _ in dl:
            out = torch.softmax(model(x.to(device)), dim=1)
            ps.append(out[:, 1].cpu().numpy())
            ys.append(y.numpy())
    return np.concatenate(ps), np.concatenate(ys)


def metrics(y, p, thr=0.5):
    pred = (np.asarray(p) >= thr).astype(int)
    y = np.asarray(y)
    tp = int(((pred == 1) & (y == 1)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    acc = float((pred == y).mean())
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    spec = tn / (tn + fp) if (tn + fp) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    # AUC（秩和法）
    order = np.argsort(p); ranks = np.empty(len(p), float); ranks[order] = np.arange(1, len(p) + 1)
    n1 = int((y == 1).sum()); n0 = int((y == 0).sum())
    auc = float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else 0.0
    return {"acc": acc, "rec": rec, "prec": prec, "spec": spec, "f1": f1, "auc": auc,
            "tp": tp, "fn": fn, "tn": tn, "fp": fp, "n": int(len(y)), "thr": round(float(thr), 3)}


def scan_best_threshold(y, p, metric="acc"):
    """在给定集合上扫最优阈值（仅用于 val！）"""
    best = None
    rows = []
    for t in np.arange(0.20, 0.81, 0.01):
        m = metrics(y, p, t)
        rows.append(m)
        if best is None or m[metric] > best[metric]:
            best = m
    return best, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="模型 checkpoint 路径")
    ap.add_argument("--data", required=True, help="数据集根目录（含 train/val/test）")
    ap.add_argument("--out", default=None, help="结果输出目录（默认=模型同级目录）")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    outdir = args.out or os.path.dirname(args.model)
    os.makedirs(outdir, exist_ok=True)

    print("=" * 88)
    print("阈值标定 + 最终测试（严谨流程：val 定阈值 → test 报成绩）")
    print("=" * 88)
    print(f"模型: {args.model}")
    print(f"数据: {args.data}")
    print(f"设备: {device}")
    print()

    m, arch, isz, cls, ckpt = load_model(args.model, device)
    print(f"模型信息: arch={arch} img_size={isz} classes={cls}")
    if "epoch" in ckpt:
        print(f"         best_epoch={ckpt.get('epoch')} best_score={ckpt.get('best_score')}")
    print()

    # ---------- 取概率 ----------
    splits = {}
    for sp in ("val", "test", "_ham_only_test", "_bcn_only_test"):
        p, y = get_probs(m, isz, args.data, sp, device, workers=args.workers)
        if p is None:
            print(f"  (跳过 {sp}：目录不存在或为空)")
            continue
        splits[sp] = (p, y)
        n_b = int((y == 0).sum()); n_m = int((y == 1).sum())
        print(f"  {sp:<18} {len(y):>6} 张  (良性{n_b} / 恶性{n_m})")
    print()

    if "val" not in splits:
        print("❌ 缺少 val 集！无法标定阈值。")
        return
    if "test" not in splits:
        print("❌ 缺少 test 集！")
        return

    # ---------- ① val 标定阈值 ----------
    pv, yv = splits["val"]
    best_val, val_rows = scan_best_threshold(yv, pv)
    print("=" * 88)
    print("① 用 VAL 标定阈值（val 未参与训练，合规）")
    print("=" * 88)
    print(f"  val 最优阈值 = {best_val['thr']:.2f}")
    print(f"    准确率 {best_val['acc']*100:.2f}%  恶性召回 {best_val['rec']*100:.2f}%  "
          f"恶性精确 {best_val['prec']*100:.2f}%  AUC {best_val['auc']:.4f}")
    print(f"    混淆 TN={best_val['tn']} FP={best_val['fp']} FN={best_val['fn']} TP={best_val['tp']}")
    thr_calibrated = best_val["thr"]
    # 也报告默认 0.50
    m50v = metrics(yv, pv, 0.50)
    print(f"  参考：val @0.50 准确率 {m50v['acc']*100:.2f}%  恶性召回 {m50v['rec']*100:.2f}%")
    print()

    # ---------- ② 用标定阈值测 test ----------
    print("=" * 88)
    print(f"② 用【val 标定的阈值 {thr_calibrated:.2f}】去 TEST 报最终成绩")
    print("=" * 88)

    final = {}
    for sp in ("test", "_ham_only_test", "_bcn_only_test"):
        if sp not in splits:
            continue
        p, y = splits[sp]
        m_cal = metrics(y, p, thr_calibrated)      # 用 val 标定的阈值
        m_50 = metrics(y, p, 0.50)                 # 默认阈值参考
        best_own, _ = scan_best_threshold(y, p)    # 该集自身最优（仅作参考，不可当成绩）
        final[sp] = {"thr_calibrated": m_cal, "thr_0.50": m_50, "own_best": best_own}
        label = {"test": "综合测试集", "_ham_only_test": "HAM-only（源域）",
                 "_bcn_only_test": "BCN-only（跨域）"}.get(sp, sp)
        print(f"\n★ {label}  (n={len(y)})")
        print("-" * 88)
        print(f"  用标定阈值 {thr_calibrated:.2f}: 准确率 {m_cal['acc']*100:6.2f}%  "
              f"恶性召回 {m_cal['rec']*100:6.2f}%  恶性精确 {m_cal['prec']*100:6.2f}%  "
              f"F1 {m_cal['f1']*100:6.2f}%  AUC {m_cal['auc']:.4f}")
        print(f"                 混淆 TN={m_cal['tn']} FP={m_cal['fp']} FN={m_cal['fn']} TP={m_cal['tp']}")
        print(f"  参考 阈值0.50 : 准确率 {m_50['acc']*100:6.2f}%  恶性召回 {m_50['rec']*100:6.2f}%")
        print(f"  (该集自身最优阈值 {best_own['thr']:.2f} → {best_own['acc']*100:.2f}%  "
              f"⚠️ 不可作为成绩，仅供标定可靠性参考)")

    # ---------- ③ 标定可靠性检查 ----------
    print()
    print("=" * 88)
    print("③ 标定可靠性")
    print("=" * 88)
    for sp, d in final.items():
        gap = (d["own_best"]["acc"] - d["thr_calibrated"]["acc"]) * 100
        tag = "✅ 可靠" if gap < 1.0 else ("⚠️ 有差距" if gap < 3 else "❌ 差距大")
        print(f"  {sp:<18} val标定阈值成绩 {d['thr_calibrated']['acc']*100:.2f}%  vs  "
              f"自身最优 {d['own_best']['acc']*100:.2f}%  差 {gap:+.2f}%  {tag}")

    # ---------- ④ 与历史对比 ----------
    print()
    print("=" * 88)
    print("④ 与历史模型对比（HAM10000 源域测试集 213 张）")
    print("=" * 88)
    print(f"{'模型':<34}{'准确率':>9}{'恶性召回':>10}{'AUC':>9}")
    print("-" * 88)
    hist = [
        ("models_v2_full (纯HAM)", 84.98, 88.98, 0.9162),
        ("models_vE_r101_288 (纯HAM)", 84.98, 86.44, 0.9187),
        ("集成2模型 (纯HAM)", 85.45, 87.29, 0.9287),
    ]
    for n, a, r, au in hist:
        print(f"{n:<34}{a:>8.2f}%{r:>9.2f}%{au:>9.4f}")
    if "_ham_only_test" in final:
        d = final["_ham_only_test"]["thr_calibrated"]
        print("-" * 88)
        print(f"{'★ 混训 mixed_v2 (val标定阈值)':<34}{d['acc']*100:>8.2f}%{d['rec']*100:>9.2f}%{d['auc']:>9.4f}")
        print(f"{'  变化(vs v2_full)':<34}{d['acc']*100-84.98:>+8.2f}%{d['rec']*100-88.98:>+9.2f}%{d['auc']-0.9162:>+9.4f}")

    # 保存
    result = {
        "model": args.model,
        "calibrated_threshold": float(thr_calibrated),
        "calibration_source": "val (未参与训练)",
        "val_metrics_at_calibrated_thr": best_val,
        "final": {k: {kk: vv for kk, vv in v.items()} for k, v in final.items()},
    }
    fp = os.path.join(outdir, "threshold_calibration_results.json")
    json.dump(result, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print()
    print(f"已保存: {fp}")


if __name__ == "__main__":
    main()
