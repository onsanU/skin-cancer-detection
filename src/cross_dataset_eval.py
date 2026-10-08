#!/usr/bin/env python3
"""
跨数据集泛化测试：HAM10000 训练的模型 → 直接在 BCN20000 上评测

目的：回答「模型到底学到了通用病变特征，还是只记住了 HAM10000 的域特征？」

评测设置（保证公平）：
  · BCN 标签从元数据 diagnosis 推断（43% 空 benign_malignant 靠这个补）
  · 指标: accuracy / 恶性Recall / 恶性Precision / F1 / AUC / 混淆矩阵
  · 同时报告在【全量 BCN】和【平衡子集(1:1)】上的表现
    —— 因为 BCN 良性:恶性 ≈ 1.47:1，不平衡会扭曲 accuracy
  · 阈值扫描：给出 BCN 上的最优阈值（跨域时最优阈值通常会漂移）

用法:
  python3 cross_dataset_eval.py --model models_v2_full/best.pt --data dataset/BCN20000_raw --meta <csv>
  python3 cross_dataset_eval.py --ensemble models_v2_full/best.pt models_vE_r101_288/best.pt ...
"""
import os
import sys
import csv
import json
import random
import argparse
from collections import defaultdict

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from torchvision.models import resnet50, resnet101
from PIL import Image

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

# BCN20000 diagnosis → 二分类
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


def resolve_label(row):
    bm = (row.get("benign_malignant") or "").strip().lower()
    if bm in ("benign", "malignant"):
        return bm
    return DX_TO_BINARY.get((row.get("diagnosis") or "").strip().lower())


class BCNMetaDataset(Dataset):
    """BCN20000：按元数据 isic_id 找图，标签从 diagnosis 推断"""

    def __init__(self, img_dir, samples, transform):
        self.img_dir = img_dir
        self.samples = samples          # [(path, label_int, isic_id)]
        self.transform = transform

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        p, y, iid = self.samples[i]
        img = Image.open(p).convert("RGB")
        return self.transform(img), y, iid


def load_meta_samples(img_dir, meta_csv):
    """读取元数据 + 匹配磁盘上的图片"""
    rows = list(csv.DictReader(open(meta_csv, encoding="utf-8-sig")))
    samples = []
    missing = 0
    unlabeled = 0
    for r in rows:
        iid = (r.get("isic_id") or "").strip()
        if not iid:
            continue
        p = os.path.join(img_dir, f"{iid}.jpg")
        if not os.path.exists(p):
            missing += 1
            continue
        lab = resolve_label(r)
        if lab is None:
            unlabeled += 1
            continue
        samples.append((p, 0 if lab == "benign" else 1, iid))
    return samples, missing, unlabeled


def build_model(ckpt_path, device):
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    arch = ckpt.get("arch", "resnet50")
    img_size = ckpt.get("img_size", 224)
    classes = ckpt.get("classes", ["benign", "malignant"])
    n_cls = len(classes)
    # ⚠️ 必须与 src/train_sota.py 的 build_model 保持一致，
    #    否则 convnext 等架构会 fallback 成 resnet 导致权重键对不上
    if arch.startswith("resnet101"):
        m = resnet101(weights=None); dim = m.fc.in_features
        m.fc = nn.Sequential(nn.Dropout(0.0), nn.Linear(dim, n_cls))
    elif arch.startswith("resnet50"):
        m = resnet50(weights=None); dim = m.fc.in_features
        m.fc = nn.Sequential(nn.Dropout(0.0), nn.Linear(dim, n_cls))
    elif arch.startswith("convnext"):
        from torchvision.models import convnext_tiny, convnext_small
        m = convnext_tiny(weights=None) if arch == "convnext_tiny" else convnext_small(weights=None)
        dim = m.classifier[2].in_features
        m.classifier[2] = nn.Sequential(nn.Dropout(0.0), nn.Linear(dim, n_cls))
    elif arch.startswith("efficientnet"):
        from torchvision.models import efficientnet_v2_s
        m = efficientnet_v2_s(weights=None)
        dim = m.classifier[1].in_features
        m.classifier[1] = nn.Sequential(nn.Dropout(0.0), nn.Linear(dim, n_cls))
    elif arch.startswith("swin"):
        from torchvision.models import swin_t
        m = swin_t(weights=None)
        dim = m.head.in_features
        m.head = nn.Sequential(nn.Dropout(0.0), nn.Linear(dim, n_cls))
    else:
        raise ValueError(f"不支持的架构: {arch}")
    m.load_state_dict(ckpt["model"])
    m.eval().to(device)
    return m, arch, img_size, classes


@torch.no_grad()
def get_probs(model, samples, img_size, device, bs=32, workers=8):
    tf = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    ds = BCNMetaDataset(None, samples, tf)
    dl = DataLoader(ds, batch_size=bs, shuffle=False, num_workers=workers)
    ps, ys, ids = [], [], []
    for x, y, iid in dl:
        out = torch.softmax(model(x.to(device)), dim=1)
        ps.append(out[:, 1].cpu().numpy())
        ys.append(y.numpy())
        ids.extend(list(iid))
    return np.concatenate(ps), np.concatenate(ys), ids


def metrics(y_true, y_prob, thr=0.5):
    pred = (np.asarray(y_prob) >= thr).astype(int)
    y = np.asarray(y_true)
    tp = int(((pred == 1) & (y == 1)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    acc = (pred == y).mean()
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    spec = tn / (tn + fp) if (tn + fp) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    # AUC（秩和法，无需 sklearn）
    try:
        order = np.argsort(y_prob)
        ranks = np.empty(len(y_prob), float)
        ranks[order] = np.arange(1, len(y_prob) + 1)
        n1 = int((y == 1).sum()); n0 = int((y == 0).sum())
        auc = (ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0) if n1 and n0 else 0.0
    except Exception:
        auc = 0.0
    return {"acc": float(acc), "rec": float(rec), "prec": float(prec),
            "spec": float(spec), "f1": float(f1), "auc": float(auc),
            "tp": tp, "fn": fn, "tn": tn, "fp": fp, "n": int(len(y))}


def scan_threshold(y_true, y_prob):
    best, rows = None, []
    for t in np.arange(0.20, 0.81, 0.01):
        m = metrics(y_true, y_prob, t)
        m["thr"] = round(float(t), 3)
        rows.append(m)
        if best is None or m["acc"] > best["acc"]:
            best = m
    return best, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="dataset/BCN20000_raw", help="BCN 图片目录")
    ap.add_argument("--meta", required=True, help="BCN 元数据 CSV")
    ap.add_argument("--model", nargs="+", required=True, help="1个=单模型，多个=集成")
    ap.add_argument("--out", default="/tmp/cross_eval", help="输出目录")
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    os.makedirs(args.out, exist_ok=True)

    samples, missing, unlabeled = load_meta_samples(args.data, args.meta)
    n_b = sum(1 for _, y, _ in samples if y == 0)
    n_m = sum(1 for _, y, _ in samples if y == 1)
    print("=" * 80)
    print("跨数据集泛化测试：HAM10000 训练 → BCN20000 评测")
    print("=" * 80)
    print(f"BCN 可用样本: {len(samples)} 张  (良性 {n_b} / 恶性 {n_m}, 比例 {n_b/max(1,n_m):.2f}:1)")
    print(f"  缺图: {missing} 张   无法定标签: {unlabeled} 张")
    print(f"模型: {args.model}")
    print(f"设备: {device}")
    print()

    # ---- 逐模型取概率 ----
    all_probs = []
    y_true = None
    for mp in args.model:
        m, arch, isz, cls = build_model(mp, device)
        p, y, ids = get_probs(m, samples, isz, device, args.bs, args.workers)
        all_probs.append(p)
        y_true = y
        single = metrics(y, p, 0.5)
        print(f"[单模型] {os.path.dirname(mp):<24} arch={arch:<11} size={isz}")
        print(f"         acc={single['acc']*100:.2f}%  恶性Recall={single['rec']*100:.2f}%  "
              f"F1={single['f1']*100:.2f}%  AUC={single['auc']:.4f}  (阈值0.5)")
        del m
        torch.cuda.empty_cache()

    p_ens = np.mean(all_probs, axis=0)

    # ---- 两个测试集：全量 + 平衡子集 ----
    rng = random.Random(42)
    idx_b = [i for i, y in enumerate(y_true) if y == 0]
    idx_m = [i for i, y in enumerate(y_true) if y == 1]
    n_bal = min(len(idx_b), len(idx_m))
    rng.shuffle(idx_b); rng.shuffle(idx_m)
    bal_idx = idx_b[:n_bal] + idx_m[:n_bal]

    results = {}
    for tag, idx in (("bcn_full", list(range(len(y_true)))), ("bcn_balanced", bal_idx)):
        yy = y_true[idx]; pp = p_ens[idx]
        base = metrics(yy, pp, 0.5)
        best, rows = scan_threshold(yy, pp)
        results[tag] = {"n": len(idx), "at_0.50": base, "best_thr": best,
                        "scan": rows}
        print()
        print("=" * 80)
        print(f"★ 集成模型在 {tag} 上的表现  (n={len(idx)})")
        print("=" * 80)
        print(f"  阈值 0.50 :  acc={base['acc']*100:6.2f}%  恶性Recall={base['rec']*100:6.2f}%  "
              f"恶性Prec={base['prec']*100:6.2f}%  F1={base['f1']*100:6.2f}%  AUC={base['auc']:.4f}")
        print(f"             混淆 TN={base['tn']} FP={base['fp']} FN={base['fn']} TP={base['tp']}")
        print(f"  最优阈值 {best['thr']:.2f}:  acc={best['acc']*100:6.2f}%  恶性Recall={best['rec']*100:6.2f}%  "
              f"F1={best['f1']*100:6.2f}%  AUC={best['auc']:.4f}")
        print(f"             混淆 TN={best['tn']} FP={best['fp']} FN={best['fn']} TP={best['tp']}")

    # ---- 对比 HAM 测试集的参照值 ----
    print()
    print("=" * 80)
    print("📌 参照：同模型在 HAM10000 测试集（源域，213 张）上的表现")
    print("    集成2模型@0.51:  acc=85.45%  恶性Recall=87.29%  AUC≈0.9287")
    print("=" * 80)

    json.dump(results, open(os.path.join(args.out, "cross_dataset_results.json"), "w",
                            encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {os.path.join(args.out, 'cross_dataset_results.json')}")

    # 泛化落差提示
    d_acc = results['bcn_balanced']['best_thr']['acc'] * 100 - 85.45
    print()
    print(f"🔍 泛化落差（BCN平衡集最优 acc - HAM acc）: {d_acc:+.2f} 个百分点")
    if d_acc < -5:
        print("   → 落差明显，说明模型有较强的『域依赖』，跨院数据泛化不足")
    elif d_acc < -2:
        print("   → 有轻度落差，属正常跨域衰减")
    else:
        print("   → 泛化良好，模型学到的是通用病变特征")


if __name__ == "__main__":
    main()
