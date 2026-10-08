#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新集成组合（R101 + CutMix）三档阈值标定 + test 报成绩

流程（严格遵循「val 标定 / test 只报成绩」）：
  ① 在 val（326 张，从未参与训练）上扫描阈值，找三档操作点
  ② 用标定好的阈值在 test（213 张）上报最终成绩

用法:
  python3 threshold_calibrate_v3.py --data dataset/processed_v2_full \
      --out docs/threshold_v3_mix.json
"""
import os
import sys
import json
import argparse

import numpy as np
import torch
import torch.nn as nn
from torchvision import transforms, models
from torch.utils.data import Dataset, DataLoader
from PIL import Image

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


class SkinDS(Dataset):
    def __init__(self, root, split, transform, classes):
        self.transform = transform
        self.samples = []
        for label, cls in enumerate(classes):
            d = os.path.join(root, split, cls)
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                if fn.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                    self.samples.append((os.path.join(d, fn), label))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        p, y = self.samples[i]
        return self.transform(Image.open(p).convert("RGB")), y


def build_model(arch, num_classes, dropout=0.0):
    if arch == "resnet50":
        m = models.resnet50(weights=None)
        m.fc = nn.Sequential(nn.Dropout(dropout), nn.Linear(m.fc.in_features, num_classes))
    elif arch == "resnet101":
        m = models.resnet101(weights=None)
        m.fc = nn.Sequential(nn.Dropout(dropout), nn.Linear(m.fc.in_features, num_classes))
    elif arch.startswith("convnext"):
        m = models.convnext_tiny(weights=None) if arch == "convnext_tiny" else models.convnext_small(weights=None)
        m.classifier[2] = nn.Sequential(nn.Dropout(dropout),
                                        nn.Linear(m.classifier[2].in_features, num_classes))
    elif arch.startswith("efficientnet"):
        m = models.efficientnet_v2_s(weights=None)
        m.classifier[1] = nn.Sequential(nn.Dropout(dropout),
                                        nn.Linear(m.classifier[1].in_features, num_classes))
    elif arch.startswith("swin"):
        m = models.swin_t(weights=None)
        m.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(m.head.in_features, num_classes))
    else:
        raise ValueError(f"不支持的架构: {arch}")
    return m


def load_one(ckpt_path, device):
    ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    arch = ck.get("arch", "resnet50")
    classes = ck.get("classes", ["benign", "malignant"])
    isz = ck.get("img_size", 224)
    model = build_model(arch, len(classes))
    sd = ck["model"] if "model" in ck else ck
    model.load_state_dict(sd)
    model.to(device).eval()
    return model, arch, classes, isz


@torch.no_grad()
def probs_of(model, isz, classes, root, split, device, bs=32, workers=4):
    tf = transforms.Compose([
        transforms.Resize((isz, isz)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    ds = SkinDS(root, split, tf, classes)
    dl = DataLoader(ds, batch_size=bs, shuffle=False, num_workers=workers, pin_memory=True)
    ps, ys = [], []
    for x, y in dl:
        x = x.to(device, non_blocking=True)
        p = torch.softmax(model(x).float(), 1)[:, 1]
        ps.append(p.cpu().numpy())
        ys.append(y.numpy())
    return np.concatenate(ps), np.concatenate(ys)


def metrics(y, p, thr):
    pred = (p >= thr).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    n = len(y)
    acc = (tp + tn) / n
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    b_rec = tn / (tn + fp) if (tn + fp) else 0.0
    return {"acc": acc, "rec": rec, "prec": prec, "f1": f1, "benign_rec": b_rec,
            "tp": tp, "fn": fn, "tn": tn, "fp": fp, "n": n, "thr": float(thr)}


def scan(val_p, val_y, grid):
    return [(thr, metrics(val_y, val_p, thr)) for thr in grid]


def auc_of(y, p):
    """ROC-AUC（与阈值无关），用秩和公式计算"""
    idx = np.argsort(p)
    y = y[idx]
    n1, n0 = int(y.sum()), int((1 - y).sum())
    if n1 == 0 or n0 == 0:
        return 0.5
    r = np.arange(1, len(y) + 1)
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--models", nargs="+",
                    default=["models_vE_r101_288/best.pt", "models_mix_cutmix_long/best.pt"])
    ap.add_argument("--weights", nargs="+", type=float, default=None)
    ap.add_argument("--out", default="docs/threshold_v3_mix.json")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    device = torch.device(args.device)
    weights = args.weights or [1.0] * len(args.models)

    print("=" * 78)
    print("新集成组合三档阈值标定")
    print("=" * 78)
    print(f"设备  : {device}")
    print(f"成员  : {list(zip(args.models, weights))}")
    print()

    loaded = []
    classes = isz = None
    for pth, w in zip(args.models, weights):
        m, arch, cls, s = load_one(pth, device)
        loaded.append((m, w))
        print(f"  加载 {pth}  arch={arch} img={s} w={w}")
        classes, isz = cls, s
    print()

    # ---- ① val 上求概率（不标定，只算概率）----
    print("① 推理 val（326 张，仅用于标定）...")
    vp_acc, vy = None, None
    for m, w in loaded:
        p, y = probs_of(m, isz, classes, args.data, "val", device, workers=args.workers)
        vp_acc = p * w if vp_acc is None else vp_acc + p * w
        vy = y
    vp = vp_acc / sum(weights)
    n_val = len(vy)
    print(f"   val 样本 {n_val}  malignant={int(vy.sum())}")

    # ---- ② test 概率 ----
    print("② 推理 test（213 张，仅用于报成绩）...")
    tp_acc, ty = None, None
    for m, w in loaded:
        p, y = probs_of(m, isz, classes, args.data, "test", device, workers=args.workers)
        tp_acc = p * w if tp_acc is None else tp_acc + p * w
        ty = y
    tp = tp_acc / sum(weights)
    print(f"   test 样本 {len(ty)}  malignant={int(ty.sum())}")
    print()

    grid = np.arange(0.05, 0.96, 0.01)

    # ---- ① val 扫描：求三档操作点 ----
    val_rows = scan(vp, vy, grid)
    best_acc_thr, best_acc_m = max(val_rows, key=lambda t: t[1]["acc"])
    # 最高召回（在 val 上）
    best_rec_thr, best_rec_m = max(val_rows, key=lambda t: (t[1]["rec"], -t[0]))
    # 综合分：召回 + macro_f1 近似（医疗平衡点）
    def score(m):
        return 0.5 * m["rec"] + 0.5 * m["f1"]
    best_bal_thr, best_bal_m = max(val_rows, key=lambda t: score(t[1]))

    print("=" * 78)
    print("val 标定结果（阈值只在 val 上定）")
    print("=" * 78)
    print(f"  最高准确率阈值 {best_acc_thr:.2f}  → val acc {best_acc_m['acc']:.4f}  召回 {best_acc_m['rec']:.4f}")
    print(f"  最高召回阈值   {best_rec_thr:.2f}  → val acc {best_rec_m['acc']:.4f}  召回 {best_rec_m['rec']:.4f}")
    print(f"  综合最优阈值   {best_bal_thr:.2f}  → val acc {best_bal_m['acc']:.4f}  召回 {best_bal_m['rec']:.4f}")
    print()

    # 三档设计：筛查(召回优先) / 平衡(综合) / 精确(准确率优先)
    def first_thr_at_rec(target):
        """找达到目标召回的最高阈值（阈值越高越保守，取满足召回的边界）"""
        cand = [(t, m) for t, m in val_rows if m["rec"] >= target]
        return max(cand, key=lambda x: x[0]) if cand else (best_rec_thr, best_rec_m)

    scr_thr, scr_m = first_thr_at_rec(0.96)
    bal_thr, bal_m = best_bal_thr, best_bal_m
    acc_thr, acc_m = best_acc_thr, best_acc_m

    # 保证单调递增
    if not (scr_thr < bal_thr < acc_thr):
        print("  ⚠️ 三档非严格单调，调整中...")
        vals = sorted([scr_thr, bal_thr, acc_thr])
        scr_thr, bal_thr, acc_thr = vals
        scr_m = dict(val_rows[[t for t, _ in val_rows].index(scr_thr)][1])
        bal_m = dict(val_rows[[t for t, _ in val_rows].index(bal_thr)][1])
        acc_m = dict(val_rows[[t for t, _ in val_rows].index(acc_thr)][1])

    presets = {"screening": scr_thr, "balanced": bal_thr, "accurate": acc_thr}
    print("=" * 78)
    print("三档阈值（val 标定）")
    print("=" * 78)
    for k, t in presets.items():
        m = dict(val_rows[[x for x, _ in val_rows].index(t)][1])
        print(f"  {k:11s} thr={t:.2f}  val acc={m['acc']:.4f}  召回={m['rec']:.4f}  漏诊率={1-m['rec']:.4f}")
    print()

    # ---- ② 用 val 标定的阈值在 test 上报成绩 ----
    print("=" * 78)
    print("test 最终成绩（用 val 标定的阈值，test 全程不参与调参）")
    print("=" * 78)
    report = {}
    for k, t in presets.items():
        m = metrics(ty, tp, t)
        report[k] = m
        print(f"  {k:11s} thr={t:.2f}  acc={m['acc']:.4f} ({m['acc']*100:.2f}%)  召回={m['rec']:.4f}  "
              f"精确={m['prec']:.4f}  F1={m['f1']:.4f}")
        print(f"               混淆矩阵 TN={m['tn']} FP={m['fp']} FN={m['fn']} TP={m['tp']}")

    # AUC（与阈值无关）
    test_auc = auc_of(ty, tp)
    val_auc = auc_of(vy, vp)
    print()
    print(f"  AUC           val={val_auc:.4f}   test={test_auc:.4f}")
    print()

    out = {
        "models": list(zip(args.models, weights)),
        "val_thresholds": {k: float(v) for k, v in presets.items()},
        "val_metrics": {k: {kk: float(vv) for kk, vv in dict(val_rows[[x for x, _ in val_rows].index(v)][1]).items()}
                        for k, v in presets.items()},
        "test_metrics": {k: {kk: (float(vv) if isinstance(vv, (int, float, np.floating)) else vv)
                             for kk, vv in m.items()} for k, m in report.items()},
        "auc": {"val": float(val_auc), "test": float(test_auc)},
        "val_scan_top10": [{"thr": float(t), "acc": float(m["acc"]), "rec": float(m["rec"])}
                           for t, m in sorted(val_rows, key=lambda x: -x[1]["acc"])[:10]],
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"已保存: {args.out}")


if __name__ == "__main__":
    main()
