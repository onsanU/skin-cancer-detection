#!/usr/bin/env python3
"""
部位先验概率校准 —— 有效性验证脚本

目的：在落代码之前，先回答「按部位校准概率，到底能不能提高准确率？」

原理（贝叶斯校准）：
    模型输出的是 P(恶性|图像) —— 即「似然」
    部位提供的是 P(恶性|部位) —— 即「先验」
    联合后：posterior ∝ likelihood × prior

    工程实现（对数几率域的加权融合，避免两路概率直接相乘导致数值溢出）：
        logit_post = logit_likelihood + λ · log(prior / (1 - prior))
    其中 λ 是校准强度（0=完全不校准，1=完全采信先验）

    λ 只在 **val 集** 上搜索，然后在 **test 集** 上报成绩。

用法:
  python3 location_prior_calibration.py \
      --model models_convnext_focal/best.pt \
      --data dataset/processed_v2_full \
      --meta dataset/HAM10000_raw/HAM10000_metadata.csv
"""
import os
import sys
import csv
import json
import argparse
from collections import Counter, defaultdict

import numpy as np
import torch
import torch.nn as nn
from torchvision import transforms, models
from torch.utils.data import Dataset, DataLoader
from PIL import Image

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

# 前端可选的部位 → HAM10000 localization 字段的映射
# （HAM 的 localization 有 15 个值，这里收敛成用户好理解的 8 类）
FRONTEND_SITES = {
    "face":     ["face", "ear", "nose"],          # 面部/耳/鼻
    "scalp":    ["scalp", "neck"],                # 头皮/颈部
    "trunk":    ["trunk", "chest", "abdomen", "back"],  # 躯干/胸/腹/背
    "arm":      ["upper extremity", "hand", "acral"],   # 上肢/手
    "leg":      ["lower extremity", "foot"],      # 下肢/足
    "genital":  ["genital"],                      # 生殖器
    "unknown":  ["unknown"],                      # 不明
}


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
                    self.samples.append((os.path.join(d, fn), label,
                                         os.path.splitext(fn)[0]))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        p, y, iid = self.samples[i]
        return self.transform(Image.open(p).convert("RGB")), y, iid


def build_model(arch, nc):
    if arch.startswith("resnet101"):
        m = models.resnet101(weights=None)
        m.fc = nn.Sequential(nn.Dropout(0.0), nn.Linear(m.fc.in_features, nc))
    elif arch.startswith("resnet"):
        m = models.resnet50(weights=None)
        m.fc = nn.Sequential(nn.Dropout(0.0), nn.Linear(m.fc.in_features, nc))
    elif arch.startswith("convnext"):
        m = models.convnext_tiny(weights=None)
        d = m.classifier[2].in_features
        m.classifier[2] = nn.Sequential(nn.Dropout(0.0), nn.Linear(d, nc))
    else:
        raise ValueError(arch)
    return m


def load_ckpt(p, device):
    c = torch.load(p, map_location=device, weights_only=False)
    m = build_model(c.get("arch", "resnet50"), len(c.get("classes", ["b", "m"])))
    m.load_state_dict(c["model"]); m.eval().to(device)
    return m, c.get("img_size", 224), c.get("classes", ["benign", "malignant"])


def probs_of(model, isz, cls, root, split, device, bs=32, workers=4):
    tf = transforms.Compose([transforms.Resize((isz, isz)), transforms.ToTensor(),
                             transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])
    ds = SkinDS(root, split, tf, cls)
    if len(ds) == 0:
        return None, None, None
    dl = DataLoader(ds, batch_size=bs, shuffle=False, num_workers=workers)
    ps, ys, ids = [], [], []
    with torch.no_grad():
        for x, y, iid in dl:
            out = torch.softmax(model(x.to(device)), dim=1)
            ps.append(out[:, 1].cpu().numpy()); ys.append(y.numpy()); ids.extend(list(iid))
    return np.concatenate(ps), np.concatenate(ys), ids


def metrics(y, p, thr=0.5):
    pred = (np.asarray(p) >= thr).astype(int); y = np.asarray(y)
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
            "tp": tp, "fn": fn, "tn": tn, "fp": fp, "n": len(y), "thr": round(float(thr), 3)}


def best_thr(y, p):
    b = None
    for t in np.arange(0.20, 0.81, 0.01):
        m = metrics(y, p, t)
        if b is None or m["acc"] > b["acc"]:
            b = m
    return b


def logit(p, eps=1e-6):
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--out", default="/tmp/loc_prior")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    os.makedirs(args.out, exist_ok=True)

    print("=" * 96)
    print("部位先验概率校准 —— 有效性验证")
    print("=" * 96)

    # ---------- 1. 读元数据 ----------
    id2site = {}
    for r in csv.DictReader(open(args.meta, encoding="utf-8-sig")):
        iid = (r.get("image_id") or "").strip()
        raw = (r.get("localization") or "unknown").strip().lower()
        if not iid:
            continue
        # 收敛成前端类别
        bucket = "unknown"
        for front, raws in FRONTEND_SITES.items():
            if raw in raws:
                bucket = front
                break
        id2site[iid] = bucket

    # ---------- 2. 取模型概率 ----------
    m, isz, cls = load_ckpt(args.model, device)
    print(f"模型: {args.model}  arch={m.__class__.__name__} img={isz}")

    data = {}
    for sp in ("train", "val", "test"):
        p, y, ids = probs_of(m, isz, cls, args.data, sp, device)
        if p is None:
            print(f"  (跳过 {sp})")
            continue
        sites = [id2site.get(i, "unknown") for i in ids]
        data[sp] = {"p": p, "y": y, "site": sites}
        print(f"  {sp:<6} {len(y):>5} 张")

    if "val" not in data or "test" not in data:
        print("❌ 缺 val 或 test")
        return

    # ---------- 3. 从 train 统计部位先验 ----------
    print()
    print("=" * 96)
    print("① 部位恶性先验（从 train 集统计）")
    print("=" * 96)
    cnt = defaultdict(lambda: [0, 0])   # site -> [benign, malignant]
    for s, yy in zip(data["train"]["site"], data["train"]["y"]):
        cnt[s][int(yy)] += 1
    # 全局先验（拉普拉斯平滑用）
    tot_b = sum(v[0] for v in cnt.values()); tot_m = sum(v[1] for v in cnt.values())
    glob_prior = tot_m / max(1, tot_b + tot_m)

    priors = {}
    print(f"{'部位':<12}{'良性':>8}{'恶性':>8}{'恶性占比':>10}{'平滑后先验':>12}{'logit':>9}")
    print("-" * 96)
    for s in sorted(cnt.keys(), key=lambda k: -cnt[k][1] / max(1, sum(cnt[k]))):
        b, mm = cnt[s]
        raw_prior = mm / max(1, b + mm)
        # 拉普拉斯平滑：样本少的部位向全局先验收缩（k=20）
        k = 20
        smoothed = (mm + k * glob_prior) / (b + mm + k)
        priors[s] = smoothed
        print(f"{s:<12}{b:>8}{mm:>8}{raw_prior*100:>9.1f}%{smoothed*100:>11.1f}%{logit(np.array([smoothed]))[0]:>9.4f}")
    print(f"\n全局恶性先验: {glob_prior*100:.1f}%")
    print(f"先验跨度: {max(priors.values())*100:.1f}% ~ {min(priors.values())*100:.1f}%")

    # ---------- 4. 在 val 上搜索 λ ----------
    print()
    print("=" * 96)
    print("② 在 VAL 上搜索校准强度 λ（0=不校准，1=完全采信先验）")
    print("=" * 96)

    def calibrate(p, sites, lam):
        """logit 域融合：logit_post = logit_likelihood + λ·logit(prior)"""
        lp = logit(np.asarray(p))
        adj = np.array([logit(np.array([priors.get(s, glob_prior)]))[0] for s in sites])
        return 1.0 / (1.0 + np.exp(-(lp + lam * adj)))

    pv, yv, sv = data["val"]["p"], data["val"]["y"], data["val"]["site"]
    baseline_v = best_thr(yv, pv)
    print(f"  基线（不校准）: val best acc={baseline_v['acc']*100:.2f}%  阈值={baseline_v['thr']:.2f}  "
          f"恶性召回={baseline_v['rec']*100:.2f}%")
    print()
    print(f"{'λ':>6}{'val acc':>10}{'val召回':>10}{'最优阈值':>10}{'vs基线':>10}")
    print("-" * 96)
    lam_results = []
    for lam in [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0]:
        pc = calibrate(pv, sv, lam)
        b = best_thr(yv, pc)
        lam_results.append({"lam": lam, "val": b})
        delta = (b["acc"] - baseline_v["acc"]) * 100
        mark = " ⭐" if delta > 0.05 else ""
        print(f"{lam:>6.1f}{b['acc']*100:>9.2f}%{b['rec']*100:>9.2f}%{b['thr']:>10.2f}{delta:>+9.2f}%{mark}")

    # 选 val 上最优的 λ
    best_lam_r = max(lam_results, key=lambda r: r["val"]["acc"])
    lam_star = best_lam_r["lam"]
    thr_star = best_lam_r["val"]["thr"]
    print(f"\n  → val 上最优 λ = {lam_star}  (阈值 {thr_star:.2f})")

    # ---------- 5. 去 test 报成绩 ----------
    print()
    print("=" * 96)
    print(f"③ 用【val 选出的 λ={lam_star} + 阈值 {thr_star:.2f}】去 TEST 报成绩")
    print("=" * 96)
    pt, yt, st = data["test"]["p"], data["test"]["y"], data["test"]["site"]
    base_t = metrics(yt, pt, best_thr(yv, pv)["thr"])       # 基线：用 val 阈值
    cal_t = metrics(yt, calibrate(pt, st, lam_star), thr_star)
    print(f"{'方案':<28}{'准确率':>9}{'恶性召回':>10}{'恶性精确':>10}{'AUC':>9}")
    print("-" * 96)
    print(f"{'基线（不校准）':<28}{base_t['acc']*100:>8.2f}%{base_t['rec']*100:>9.2f}%"
          f"{base_t['prec']*100:>9.2f}%{base_t['auc']:>9.4f}")
    print(f"{'部位校准 λ='+str(lam_star):<28}{cal_t['acc']*100:>8.2f}%{cal_t['rec']*100:>9.2f}%"
          f"{cal_t['prec']*100:>9.2f}%{cal_t['auc']:>9.4f}")
    print(f"{'变化':<28}{(cal_t['acc']-base_t['acc'])*100:>+8.2f}%"
          f"{(cal_t['rec']-base_t['rec'])*100:>+9.2f}%"
          f"{(cal_t['prec']-base_t['prec'])*100:>+9.2f}%{(cal_t['auc']-base_t['auc']):>+9.4f}")

    # ---------- 6. 结论 ----------
    print()
    print("=" * 96)
    verdict = "有效，值得落地" if cal_t["acc"] > base_t["acc"] + 0.002 else \
              ("基本无效，建议不落地" if cal_t["acc"] < base_t["acc"] - 0.002 else "提升极小，可做可不做")
    print(f"🎯 结论: {verdict}")
    print("=" * 96)

    json.dump({"priors": priors, "global_prior": glob_prior,
               "lambda_star": lam_star, "threshold_star": thr_star,
               "val_baseline": baseline_v, "test_baseline": base_t, "test_calibrated": cal_t,
               "lam_scan": [{"lam": r["lam"], "val_acc": r["val"]["acc"]} for r in lam_results]},
              open(os.path.join(args.out, "location_prior_results.json"), "w"),
              ensure_ascii=False, indent=2)
    print(f"已保存: {os.path.join(args.out, 'location_prior_results.json')}")


if __name__ == "__main__":
    main()
