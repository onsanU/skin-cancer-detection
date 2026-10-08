#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型集成 + TTA 推理评估
================================================================
目的：不重新训练，用现有模型集成提升准确率

方法：
  1. 模型集成（Ensemble）—— 多个模型的 softmax 概率求平均
     候选：models_v2_full (R50/224) + models_vE_r101_288 (R101/288)
  2. TTA（Test Time Augmentation）—— 同一张图做多个变换后预测再平均
     变换：原图 / 水平翻转 / 垂直翻转 / 旋转±10° / 缩放
  3. 组合：多模型 × 多变换 = N×M 次推理，概率平均

预期收益：+2~3%（模型集成）+1~2%（TTA）
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import (ResNet50_Weights, ResNet101_Weights,
                                resnet50, resnet101)

# ==================== 配置 ====================
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]
PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA = os.path.join(PROJ_ROOT, "dataset", "processed_v2_full")
DEFAULT_OUT = os.path.join(PROJ_ROOT, "docs")


# ==================== TTA 变换集 ====================
def build_tta_transforms(img_size):
    """5 种变换：原图 / 水平翻转 / 垂直翻转 / 旋转+10 / 旋转-10"""
    base = [
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ]
    return [
        ("orig", transforms.Compose(base)),
        ("hflip", transforms.Compose([transforms.Resize((img_size, img_size)),
                                      transforms.RandomHorizontalFlip(p=1.0),
                                      transforms.ToTensor(),
                                      transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])),
        ("vflip", transforms.Compose([transforms.Resize((img_size, img_size)),
                                      transforms.RandomVerticalFlip(p=1.0),
                                      transforms.ToTensor(),
                                      transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])),
        ("rot10", transforms.Compose([transforms.Resize((img_size, img_size)),
                                      transforms.RandomRotation((10, 10)),
                                      transforms.ToTensor(),
                                      transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])),
        ("rot-10", transforms.Compose([transforms.Resize((img_size, img_size)),
                                       transforms.RandomRotation((-10, -10)),
                                       transforms.ToTensor(),
                                       transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])),
    ]


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
        img = Image.open(p).convert("RGB")
        return self.transform(img), y, p


# ==================== 模型加载 ====================
def load_model(ckpt_path, device):
    """从 checkpoint 加载模型（自动识别 arch / img_size / classes）"""
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    arch = ckpt.get("arch", "resnet50")
    img_size = ckpt.get("img_size", 224)
    ckpt_classes = ckpt.get("classes", ["benign", "malignant"])
    n_cls = len(ckpt_classes)

    if arch.startswith("resnet101"):
        m = resnet101(weights=None)
        dim = m.fc.in_features
    else:
        m = resnet50(weights=None)
        dim = m.fc.in_features
    m.fc = nn.Sequential(nn.Dropout(0.0), nn.Linear(dim, n_cls))
    m.load_state_dict(ckpt["model"])
    m.eval().to(device)
    return m, arch, img_size, ckpt_classes, ckpt


# ==================== 指标 ====================
def metrics_at(y_true, y_prob_pos, thr=0.5):
    """二分类指标（y_prob_pos 是恶性概率）"""
    y_true = np.asarray(y_true)
    y_pred = (np.asarray(y_prob_pos) >= thr).astype(int)
    acc = float((y_true == y_pred).mean())
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    try:
        from sklearn.metrics import roc_auc_score
        auc = float(roc_auc_score(y_true, y_prob_pos)) if len(set(y_true)) > 1 else 0.0
    except Exception:
        auc = 0.0
    return {
        "accuracy": acc, "malignant_recall": rec, "malignant_precision": prec,
        "macro_f1": f1, "auc": auc,
        "confusion_matrix": [[tn, fp], [fn, tp]],
    }


@torch.no_grad()
def predict_with_tta(model, root, split, classes, img_size, device, tta=True, bs=32):
    """返回 (y_true, 概率矩阵[n,C])，用 TTA 平均"""
    tfs = build_tta_transforms(img_size) if tta else build_tta_transforms(img_size)[:1]
    n_tta = len(tfs)
    prob_sum = None
    y_all = None

    for name, tf in tfs:
        ds = SkinDS(root, split, tf, classes)
        dl = DataLoader(ds, batch_size=bs, shuffle=False, num_workers=4)
        probs, ys = [], []
        for x, y, _ in dl:
            x = x.to(device)
            with torch.amp.autocast("cuda", enabled=(device.type == "cuda")):
                out = model(x)
            probs.append(torch.softmax(out.float(), dim=1).cpu().numpy())
            ys.append(y.numpy())
        p = np.concatenate(probs, axis=0)
        if prob_sum is None:
            prob_sum = p
            y_all = np.concatenate(ys, axis=0)
        else:
            prob_sum += p

    return y_all, prob_sum / n_tta


def main():
    ap = argparse.ArgumentParser(description="模型集成 + TTA 评估")
    ap.add_argument("--data", default=DEFAULT_DATA, help="数据集目录")
    ap.add_argument("--split", default="test", help="评估用的划分")
    ap.add_argument("--models", nargs="+", default=[
        "models_v2_full/best.pt",
        "models_vE_r101_288/best.pt",
    ], help="参与集成的 checkpoint 列表（相对项目根）")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出目录")
    ap.add_argument("--no-tta", action="store_true", help="关闭 TTA（仅测集成）")
    ap.add_argument("--thr", type=float, default=0.5, help="判定阈值")
    ap.add_argument("--bs", type=int, default=32)
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("=" * 80)
    print("模型集成 + TTA 评估")
    print("=" * 80)
    print(f"设备    : {device}")
    print(f"数据集  : {args.data}/{args.split}")
    print(f"TTA     : {'关闭' if args.no_tta else '开启（5 种变换）'}")
    print(f"阈值    : {args.thr}")
    print(f"参与模型: {len(args.models)} 个")

    # ---- 1. 单模型评估（无 TTA，作为基线）----
    print("\n" + "-" * 80)
    print("【1】单模型基线（无 TTA）")
    print("-" * 80)
    singles = {}
    all_probs = []          # [(prob矩阵, y_true, 模型名)]
    ref_y = None

    for rel in args.models:
        path = rel if os.path.isabs(rel) else os.path.join(PROJ_ROOT, rel)
        if not os.path.isfile(path):
            print(f"  ⚠️ 跳过（不存在）: {rel}")
            continue
        m, arch, isz, cls, ckpt = load_model(path, device)
        # 类别顺序必须与数据目录一致
        ds_classes = sorted(os.listdir(os.path.join(args.data, args.split)))
        ds_classes = [c for c in ds_classes if os.path.isdir(os.path.join(args.data, args.split, c))]
        if cls != ds_classes:
            print(f"  ⚠️ {rel}: checkpoint 类别 {cls} != 数据类别 {ds_classes}，跳过")
            continue

        t0 = time.time()
        y, p = predict_with_tta(m, args.data, args.split, cls, isz, device,
                                tta=False, bs=args.bs)
        mt = metrics_at(y, p[:, 1], args.thr)
        print(f"  {os.path.basename(os.path.dirname(path)):24s} acc={mt['accuracy']:.4f} "
              f"rec={mt['malignant_recall']:.4f} f1={mt['macro_f1']:.4f} auc={mt['auc']:.4f} "
              f"({time.time()-t0:.1f}s)")
        singles[rel] = mt
        all_probs.append((p, os.path.basename(os.path.dirname(path))))
        ref_y = y

    if not all_probs:
        print("[ERROR] 没有可用模型")
        sys.exit(1)

    # ---- 2. 模型集成（无 TTA）----
    print("\n" + "-" * 80)
    print("【2】模型集成（概率平均，无 TTA）")
    print("-" * 80)
    ens_p = np.mean([p for p, _ in all_probs], axis=0)
    ens_m = metrics_at(ref_y, ens_p[:, 1], args.thr)
    print(f"  Ensemble({len(all_probs)}模型) acc={ens_m['accuracy']:.4f} "
          f"rec={ens_m['malignant_recall']:.4f} f1={ens_m['macro_f1']:.4f} auc={ens_m['auc']:.4f}")

    # ---- 3. TTA 单模型 ----
    tta_singles = {}
    if not args.no_tta:
        print("\n" + "-" * 80)
        print("【3】单模型 + TTA（5 变换平均）")
        print("-" * 80)
        tta_probs = []
        for rel in args.models:
            path = rel if os.path.isabs(rel) else os.path.join(PROJ_ROOT, rel)
            if not os.path.isfile(path):
                continue
            m, arch, isz, cls, ckpt = load_model(path, device)
            ds_classes = sorted(os.listdir(os.path.join(args.data, args.split)))
            ds_classes = [c for c in ds_classes if os.path.isdir(os.path.join(args.data, args.split, c))]
            if cls != ds_classes:
                continue
            t0 = time.time()
            y, p = predict_with_tta(m, args.data, args.split, cls, isz, device, tta=True, bs=args.bs)
            mt = metrics_at(y, p[:, 1], args.thr)
            nm = os.path.basename(os.path.dirname(path))
            print(f"  {nm:24s} acc={mt['accuracy']:.4f} rec={mt['malignant_recall']:.4f} "
                  f"f1={mt['macro_f1']:.4f} auc={mt['auc']:.4f} ({time.time()-t0:.1f}s)")
            tta_singles[rel] = mt
            tta_probs.append((p, nm))

        # ---- 4. 集成 + TTA ----
        print("\n" + "-" * 80)
        print("【4】★ 模型集成 + TTA（最终方案）")
        print("-" * 80)
        ens_tta_p = np.mean([p for p, _ in tta_probs], axis=0)
        ens_tta_m = metrics_at(ref_y, ens_tta_p[:, 1], args.thr)
        print(f"  Ensemble+TTA acc={ens_tta_m['accuracy']:.4f} "
              f"rec={ens_tta_m['malignant_recall']:.4f} f1={ens_tta_m['macro_f1']:.4f} "
              f"auc={ens_tta_m['auc']:.4f}")

    # ---- 5. 汇总对比 ----
    print("\n" + "=" * 80)
    print("汇总对比")
    print("=" * 80)
    rows = []
    for rel, mt in singles.items():
        rows.append((os.path.basename(os.path.dirname(rel)) + " (单模型)", mt))
    rows.append((f"集成 ({len(all_probs)}模型)", ens_m))
    for rel, mt in tta_singles.items():
        rows.append((os.path.basename(os.path.dirname(rel)) + " +TTA", mt))
    if not args.no_tta:
        rows.append((f"★ 集成+TTA ({len(all_probs)}模型)", ens_tta_m))

    print(f"{'方案':<34} {'准确率':>8} {'恶性召回':>9} {'F1':>8} {'AUC':>8}")
    print("-" * 80)
    best_acc = max(r[1]["accuracy"] for r in rows)
    for name, mt in rows:
        flag = " ⭐" if abs(mt["accuracy"] - best_acc) < 1e-9 else ""
        print(f"{name:<34} {mt['accuracy']:>8.4f} {mt['malignant_recall']:>9.4f} "
              f"{mt['macro_f1']:>8.4f} {mt['auc']:>8.4f}{flag}")

    # ---- 6. 保存结果 ----
    os.makedirs(args.out, exist_ok=True)
    out = {
        "config": {
            "data": args.data, "split": args.split, "threshold": args.thr,
            "tta": not args.no_tta, "models": args.models,
        },
        "singles": singles,
        "ensemble": ens_m,
        "tta_singles": tta_singles,
        "ensemble_tta": (ens_tta_m if not args.no_tta else None),
    }
    op = os.path.join(args.out, "ensemble_results.json")
    with open(op, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {op}")

    # 提升幅度
    base_acc = list(singles.values())[0]["accuracy"]
    final = ens_tta_m if not args.no_tta else ens_m
    print(f"\n基线（最强单模型）: {base_acc:.4f}")
    print(f"最终方案          : {final['accuracy']:.4f}")
    print(f"提升              : {(final['accuracy']-base_acc)*100:+.2f} 个百分点")


if __name__ == "__main__":
    main()
