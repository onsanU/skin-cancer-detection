#!/usr/bin/env python3
"""
阈值标定 + 最终测试（多架构版）

支持架构: resnet50/101, convnext_tiny/small, efficientnet_v2_s, swin_t

正确流程：
  ① 用 val 集标定最优阈值（val 从未参与训练，也从未用于报成绩）
  ② 用标定好的阈值 → 去 test 集报最终成绩（test 全程未参与任何调参）

用法:
  python3 threshold_calibrate_multi.py --model models_convnext_focal/best.pt --data dataset/processed_v2_full
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
                if fn.lower().endswith((".jpg", ".jpeg", ".png")):
                    self.samples.append((os.path.join(d, fn), label))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        p, y = self.samples[i]
        return self.transform(Image.open(p).convert("RGB")), y


def build_model_multi(arch, num_classes, dropout=0.0):
    """按架构名重建模型（结构与 train_sota.py 保持一致）"""
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


def load_model_multi(ckpt_path, device):
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    arch = ckpt.get("arch", "resnet50")
    img_size = ckpt.get("img_size", 224)
    classes = ckpt.get("classes", ["benign", "malignant"])
    m = build_model_multi(arch, len(classes), dropout=0.0)
    m.load_state_dict(ckpt["model"])
    m.eval().to(device)
    return m, arch, img_size, classes, ckpt


def get_probs(model, img_size, data_root, split, device, classes, bs=32, workers=4):
    tf = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
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
    spec = tn / (tn + fp) if (tn + fp) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    order = np.argsort(p); ranks = np.empty(len(p), float); ranks[order] = np.arange(1, len(p) + 1)
    n1 = int((y == 1).sum()); n0 = int((y == 0).sum())
    auc = float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else 0.0
    return {"acc": acc, "rec": rec, "prec": prec, "spec": spec, "f1": f1, "auc": auc,
            "tp": tp, "fn": fn, "tn": tn, "fp": fp, "n": int(len(y)), "thr": round(float(thr), 3)}


def scan_best(y, p):
    best = None
    rows = []
    for t in np.arange(0.20, 0.81, 0.01):
        m = metrics(y, p, t)
        rows.append(m)
        if best is None or m["acc"] > best["acc"]:
            best = m
    return best, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--splits", nargs="+", default=["val", "test",
                                                    "_ham_only_test", "_bcn_only_test"])
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    outdir = args.out or os.path.dirname(args.model)
    os.makedirs(outdir, exist_ok=True)

    print("=" * 90)
    print("阈值标定 + 最终测试（多架构版）")
    print("=" * 90)
    m, arch, isz, cls, ckpt = load_model_multi(args.model, device)
    print(f"模型    : {args.model}")
    print(f"架构    : {arch}  img_size={isz}  classes={cls}")
    if "epoch" in ckpt:
        print(f"best_ep : {ckpt.get('epoch')}  best_score={ckpt.get('best_score')}")
    print(f"数据    : {args.data}")
    print()

    splits = {}
    for sp in args.splits:
        p, y = get_probs(m, isz, args.data, sp, device, cls, workers=args.workers)
        if p is None:
            continue
        splits[sp] = (p, y)
        nb, nm = int((y == 0).sum()), int((y == 1).sum())
        print(f"  {sp:<18} {len(y):>5} 张  (良性{nb} / 恶性{nm})")
    print()

    if "val" not in splits:
        print("❌ 缺 val 集，无法标定阈值")
        return

    # ① val 标定
    pv, yv = splits["val"]
    best_val, _ = scan_best(yv, pv)
    thr = best_val["thr"]
    print("=" * 90)
    print("① VAL 标定阈值（val 未参与训练，合规）")
    print("=" * 90)
    print(f"  最优阈值 = {thr:.2f}")
    print(f"  accuracy {best_val['acc']*100:.2f}%  恶性召回 {best_val['rec']*100:.2f}%  "
          f"恶性精确 {best_val['prec']*100:.2f}%  AUC {best_val['auc']:.4f}")
    print(f"  混淆 TN={best_val['tn']} FP={best_val['fp']} FN={best_val['fn']} TP={best_val['tp']}")
    m50 = metrics(yv, pv, 0.50)
    print(f"  参考 @0.50: acc {m50['acc']*100:.2f}%  恶性召回 {m50['rec']*100:.2f}%")
    print()

    # ② test
    print("=" * 90)
    print(f"② 用【val 标定的阈值 {thr:.2f}】去 TEST 报最终成绩")
    print("=" * 90)
    final = {}
    label_map = {"test": "综合 test", "_ham_only_test": "HAM-only(源域)",
                 "_bcn_only_test": "BCN-only(跨域)"}
    for sp in ("test", "_ham_only_test", "_bcn_only_test"):
        if sp not in splits:
            continue
        p, y = splits[sp]
        mc = metrics(y, p, thr)
        m5 = metrics(y, p, 0.50)
        own, _ = scan_best(y, p)
        final[sp] = {"calibrated": mc, "at_0.50": m5, "own_best": own}
        print(f"\n★ {label_map.get(sp, sp)}  (n={len(y)})")
        print("-" * 90)
        print(f"  标定阈值 {thr:.2f}: acc {mc['acc']*100:6.2f}%  恶性召回 {mc['rec']*100:6.2f}%  "
              f"恶性精确 {mc['prec']*100:6.2f}%  F1 {mc['f1']*100:6.2f}%  AUC {mc['auc']:.4f}")
        print(f"              混淆 TN={mc['tn']} FP={mc['fp']} FN={mc['fn']} TP={mc['tp']}")
        print(f"  参考 @0.50 : acc {m5['acc']*100:6.2f}%  恶性召回 {m5['rec']*100:6.2f}%")
        print(f"  (自身最优 {own['thr']:.2f} -> {own['acc']*100:.2f}%  仅参考，不可当成绩)")

    print()
    print("=" * 90)
    print("③ 与历史对比（同一个 HAM test 213 张）")
    print("=" * 90)
    print(f"{'模型':<38}{'准确率':>9}{'恶性召回':>10}{'AUC':>9}")
    print("-" * 90)
    for n, a, r, au in [("models_v2_full (ResNet50@224, 纯HAM)", 84.98, 88.98, 0.9162),
                        ("models_vE_r101_288 (纯HAM)", 84.98, 86.44, 0.9187),
                        ("集成2模型 (纯HAM, 最强历史)", 85.45, 87.29, 0.9287)]:
        print(f"{n:<38}{a:>8.2f}%{r:>9.2f}%{au:>9.4f}")
    if "_ham_only_test" in final:
        d = final["_ham_only_test"]["calibrated"]
        print("-" * 90)
        print(f"{'★ ConvNeXt-T@288 + Focal (本次)':<38}{d['acc']*100:>8.2f}%{d['rec']*100:>9.2f}%{d['auc']:>9.4f}")
        print(f"{'  变化(vs 集成2模型)':<38}{d['acc']*100-85.45:>+8.2f}%{d['rec']*100-87.29:>+9.2f}%{d['auc']-0.9287:>+9.4f}")

    result = {"model": args.model, "arch": arch, "calibrated_threshold": float(thr),
              "val_metrics": best_val, "final": final}
    fp = os.path.join(outdir, "threshold_calibration_results.json")
    json.dump(result, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print()
    print(f"已保存: {fp}")


if __name__ == "__main__":
    main()
