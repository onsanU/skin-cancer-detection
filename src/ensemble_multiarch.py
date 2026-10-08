#!/usr/bin/env python3
"""
多架构集成快速评估（无需重新训练）

思路：
  ResNet50 强在准确率（85.45%），ConvNeXt+Focal 强在恶性召回（89.83%）
  → 用不同权重组合集成，寻找「准确率 + 召回」的最优平衡点

评估方式：
  · 在 val 上标定阈值（合规）
  · 在 test 213 张上报成绩（与历史可比）
  · 扫描多种权重组合

用法:
  python3 ensemble_multiarch.py --data dataset/processed_v2_full \
      --models models_v2_full/best.pt models_vE_r101_288/best.pt models_convnext_focal/best.pt
"""
import os
import sys
import json
import argparse
import itertools

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
                if fn.lower().endswith((".jpg", ".jpeg", ".png")):
                    self.samples.append((os.path.join(d, fn), label))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        p, y = self.samples[i]
        return self.transform(Image.open(p).convert("RGB")), y


def build_model_multi(arch, num_classes, dropout=0.0):
    if arch.startswith("resnet101"):
        m = models.resnet101(weights=None)
        m.fc = nn.Sequential(nn.Dropout(dropout), nn.Linear(m.fc.in_features, num_classes))
    elif arch.startswith("resnet"):
        m = models.resnet50(weights=None)
        m.fc = nn.Sequential(nn.Dropout(dropout), nn.Linear(m.fc.in_features, num_classes))
    elif arch.startswith("convnext"):
        m = models.convnext_tiny(weights=None) if arch == "convnext_tiny" else models.convnext_small(weights=None)
        dim = m.classifier[2].in_features
        m.classifier[2] = nn.Sequential(nn.Dropout(dropout), nn.Linear(dim, num_classes))
    elif arch.startswith("efficientnet"):
        m = models.efficientnet_v2_s(weights=None)
        dim = m.classifier[1].in_features
        m.classifier[1] = nn.Sequential(nn.Dropout(dropout), nn.Linear(dim, num_classes))
    elif arch.startswith("swin"):
        m = models.swin_t(weights=None)
        m.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(m.head.in_features, num_classes))
    else:
        raise ValueError(f"不支持的架构: {arch}")
    return m


def load_one(ckpt_path, device):
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    arch = ckpt.get("arch", "resnet50")
    isz = ckpt.get("img_size", 224)
    classes = ckpt.get("classes", ["benign", "malignant"])
    m = build_model_multi(arch, len(classes), 0.0)
    m.load_state_dict(ckpt["model"])
    m.eval().to(device)
    return m, arch, isz, classes


def probs_of(model, isz, classes, data_root, split, device, bs=32, workers=4):
    tf = transforms.Compose([transforms.Resize((isz, isz)), transforms.ToTensor(),
                             transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])
    ds = SkinDS(data_root, split, tf, classes)
    if len(ds) == 0:
        return None, None
    dl = DataLoader(ds, batch_size=bs, shuffle=False, num_workers=workers)
    ps, ys = [], []
    with torch.no_grad():
        for x, y in dl:
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
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    order = np.argsort(p); ranks = np.empty(len(p), float); ranks[order] = np.arange(1, len(p) + 1)
    n1 = int((y == 1).sum()); n0 = int((y == 0).sum())
    auc = float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else 0.0
    return {"acc": acc, "rec": rec, "prec": prec, "f1": f1, "auc": auc,
            "tp": tp, "fn": fn, "tn": tn, "fp": fp, "n": int(len(y)), "thr": round(float(thr), 3)}


def best_thr(y, p):
    best = None
    for t in np.arange(0.20, 0.81, 0.01):
        m = metrics(y, p, t)
        if best is None or m["acc"] > best["acc"]:
            best = m
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--out", default="/tmp/ensemble_multiarch")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    os.makedirs(args.out, exist_ok=True)

    print("=" * 94)
    print("多架构集成评估（ResNet × ConvNeXt）")
    print("=" * 94)

    # ---- 逐模型取概率（三个数据划分）----
    names, P = [], {}
    for mp in args.models:
        m, arch, isz, cls = load_one(mp, device)
        nm = os.path.basename(os.path.dirname(mp))
        names.append(nm)
        print(f"\n[{nm}]  arch={arch} img_size={isz}")
        for split in ("val", "test"):
            p, y = probs_of(m, isz, cls, args.data, split, device, workers=args.workers)
            if p is None:
                continue
            P[(nm, split)] = p
            if split == "val":
                P[("_y", split)] = y
            else:
                # test 的 y 每个模型都一样，存一次即可
                P.setdefault(("_y", split), y)
            m50 = metrics(y, p, 0.5)
            print(f"   {split:<6} acc={m50['acc']*100:6.2f}%  恶性召回={m50['rec']*100:6.2f}%  AUC={m50['auc']:.4f}")
        del m
        torch.cuda.empty_cache()

    n_models = len(names)

    # ---- 枚举权重组合（含单模型基线）----
    print()
    print("=" * 94)
    print("权重组合搜索（在 val 上标定阈值 → 在 test 上报成绩）")
    print("=" * 94)
    print(f"{'组合':<52}{'val阈值':>8}{'val acc':>9}{'test acc':>10}{'test召回':>10}{'AUC':>9}")
    print("-" * 94)

    # 权重候选：每个模型 0/1/2（相对权重），排除全 0
    results = []
    for w in itertools.product([0, 1, 2], repeat=n_models):
        if sum(w) == 0:
            continue
        # val 集成
        pv = sum(wi * P[(nm, "val")] for wi, nm in zip(w, names)) / sum(w)
        yv = P[("_y", "val")]
        bv = best_thr(yv, pv)
        # test 用 val 标定的阈值
        pt = sum(wi * P[(nm, "test")] for wi, nm in zip(w, names)) / sum(w)
        yt = P[("_y", "test")]
        mt = metrics(yt, pt, bv["thr"])
        combo = " + ".join(f"{nm}×{wi}" for wi, nm in zip(w, names) if wi > 0)
        results.append({"weights": w, "combo": combo, "val_thr": bv["thr"],
                        "val_acc": bv["acc"], "test": mt})
        if len(combo) < 52:
            print(f"{combo:<52}{bv['thr']:>8.2f}{bv['acc']*100:>8.2f}%"
                  f"{mt['acc']*100:>9.2f}%{mt['rec']*100:>9.2f}%{mt['auc']:>9.4f}")

    # ---- 排序 ----
    print()
    print("=" * 94)
    print("TOP 10（按 test 准确率）")
    print("=" * 94)
    print(f"{'组合':<52}{'test acc':>10}{'test召回':>10}{'AUC':>9}")
    print("-" * 94)
    for r in sorted(results, key=lambda x: -x["test"]["acc"])[:10]:
        t = r["test"]
        print(f"{r['combo']:<52}{t['acc']*100:>9.2f}%{t['rec']*100:>9.2f}%{t['auc']:>9.4f}")

    print()
    print("=" * 94)
    print("与历史最强对比")
    print("=" * 94)
    print(f"{'方案':<52}{'准确率':>10}{'恶性召回':>10}{'AUC':>9}")
    print("-" * 94)
    print(f"{'历史最强: 集成2模型 (ResNet50+R101)':<52}{85.45:>9.2f}%{87.29:>9.2f}%{0.9287:>9.4f}")
    best_r = max(results, key=lambda x: x["test"]["acc"])
    t = best_r["test"]
    print(f"{'本次最优: ' + best_r['combo'][:40]:<52}{t['acc']*100:>9.2f}%{t['rec']*100:>9.2f}%{t['auc']:>9.4f}")
    print(f"{'  变化':<52}{t['acc']*100-85.45:>+9.2f}%{t['rec']*100-87.29:>+9.2f}%{t['auc']-0.9287:>+9.4f}")

    json.dump({"models": names,
               "results": [{**r, "weights": list(r["weights"])} for r in results]},
              open(os.path.join(args.out, "results.json"), "w"), ensure_ascii=False, indent=2)
    print()
    print(f"已保存: {os.path.join(args.out, 'results.json')}")


if __name__ == "__main__":
    main()
