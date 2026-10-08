#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阈值调优 —— 用训练好的模型在测试集上扫描判定阈值
================================================================
背景:
  默认用 argmax（阈值0.5）判定恶性/良性。但医疗场景中
  「漏诊（把恶性判成良性）」的代价远大于「误诊（把良性判成恶性）」，
  因此需要扫描阈值，找到更合适的操作点。

本脚本输出:
  - 阈值扫描表（0.20~0.80，步长0.01）的 acc / 恶性Recall / 恶性Precision / F1
  - 三个推荐操作点:
      ① 最大准确率点
      ② 召回优先点（恶性Recall >= 0.95）
      ③ 平衡点（约登指数 J = Recall + Specificity - 1 最大）
  - 可视化曲线图
  - JSON 结果供后端配置使用

用法:
  python3 threshold_tuning.py
  python3 threshold_tuning.py --model models_v2_full/best.pt
"""

import argparse
import json
import os
import sys

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import resnet50, resnet101

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]
CLASSES = ["benign", "malignant"]

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA = os.path.join(PROJ_ROOT, "dataset", "processed_v2_full")
LOCAL_DATA = os.path.expanduser("~/skin_cancer_data/processed_v2_full")


class TestDataset(Dataset):
    def __init__(self, root, img_size):
        self.samples = []
        self.tf = transforms.Compose([
            transforms.Resize((img_size, img_size)),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ])
        for label, cls in enumerate(CLASSES):
            d = os.path.join(root, "test", cls)
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                if fn.lower().endswith((".jpg", ".jpeg", ".png")):
                    self.samples.append((os.path.join(d, fn), label))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        p, y = self.samples[i]
        return self.tf(Image.open(p).convert("RGB")), y


def build_model(arch):
    if arch == "resnet50":
        m = resnet50(weights=None); feat = m.fc.in_features
    elif arch == "resnet101":
        m = resnet101(weights=None); feat = m.fc.in_features
    else:
        raise ValueError(arch)
    m.fc = nn.Sequential(nn.Dropout(0.4), nn.Linear(feat, 2))
    return m


@torch.no_grad()
def get_probs(model, loader, device):
    """返回 (labels, malignant_probs)"""
    ys, ps = [], []
    for x, y in loader:
        x = x.to(device)
        out = model(x)
        p = torch.softmax(out.float(), dim=1)[:, 1]     # 恶性概率
        ys.extend(y.tolist())
        ps.extend(p.cpu().tolist())
    return np.array(ys), np.array(ps)


def metrics_at(y, p, thr):
    """在给定阈值下计算指标"""
    pred = (p >= thr).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())

    acc = (tp + tn) / max(1, len(y))
    rec = tp / max(1, tp + fn)          # 恶性召回（灵敏度）
    spec = tn / max(1, tn + fp)         # 特异性
    prec = tp / max(1, tp + fp)
    f1 = 2 * prec * rec / max(1e-9, prec + rec)
    youden = rec + spec - 1             # 约登指数
    return {
        "threshold": round(thr, 3),
        "accuracy": round(acc, 4),
        "malignant_recall": round(rec, 4),
        "malignant_precision": round(prec, 4),
        "benign_recall": round(spec, 4),
        "macro_f1": round(f1, 4),
        "youden": round(youden, 4),
        "miss_rate": round(1 - rec, 4),      # 漏诊率
        "false_alarm_rate": round(1 - spec, 4),  # 误报率
        "confusion": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(PROJ_ROOT, "models_v2_full", "best.pt"))
    ap.add_argument("--data", default=None, help="测试数据根目录（含 test/benign、test/malignant）")
    ap.add_argument("--out", default=os.path.join(PROJ_ROOT, "docs", "threshold_tuning.json"))
    args = ap.parse_args()

    # 优先本地盘（速度快）
    data_root = args.data
    if not data_root:
        data_root = LOCAL_DATA if os.path.isdir(LOCAL_DATA) else DEFAULT_DATA

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("=" * 78)
    print("阈值调优 —— 扫描判定阈值，寻找最优操作点")
    print("=" * 78)

    ckpt = torch.load(args.model, map_location=device, weights_only=False)
    arch = ckpt.get("arch", "resnet50")
    img_size = int(ckpt.get("img_size", 224))
    model = build_model(arch)
    model.load_state_dict(ckpt.get("model") or ckpt)
    model.to(device).eval()
    print(f"模型  : {args.model}")
    print(f"        arch={arch} img_size={img_size} epoch={ckpt.get('epoch')}")
    print(f"数据  : {data_root}")

    ds = TestDataset(data_root, img_size)
    loader = DataLoader(ds, batch_size=32, shuffle=False, num_workers=4)
    y, p = get_probs(model, loader, device)
    n_mal, n_ben = int((y == 1).sum()), int((y == 0).sum())
    print(f"测试集: {len(ds)} 张 (恶性{n_mal} / 良性{n_ben})")
    print("=" * 78)

    # ---------- 扫描阈值 ----------
    thresholds = np.round(np.arange(0.20, 0.81, 0.01), 2)
    rows = [metrics_at(y, p, t) for t in thresholds]

    print(f"\n{'阈值':>5} {'准确率':>7} {'恶性召回':>8} {'恶性精确':>8} {'良性召回':>8} "
          f"{'F1':>6} {'约登':>6} {'漏诊率':>7}")
    print("-" * 78)
    for r in rows:
        if abs(r["threshold"] * 100 - round(r["threshold"] * 100)) < 0.5 and int(round(r["threshold"] * 100)) % 5 == 0:
            print(f"{r['threshold']:>5.2f} {r['accuracy']:>7.4f} {r['malignant_recall']:>8.4f} "
                  f"{r['malignant_precision']:>8.4f} {r['benign_recall']:>8.4f} {r['macro_f1']:>6.4f} "
                  f"{r['youden']:>6.4f} {r['miss_rate']:>7.4f}")

    # ---------- 三类推荐点 ----------
    best_acc = max(rows, key=lambda r: (r["accuracy"], r["youden"]))
    best_youden = max(rows, key=lambda r: r["youden"])

    recall_priority = None
    for r in sorted(rows, key=lambda x: -x["threshold"]):    # 从高阈值往低找
        if r["malignant_recall"] >= 0.95:
            recall_priority = r
            break
    if recall_priority is None:
        recall_priority = max(rows, key=lambda r: r["malignant_recall"])

    base = metrics_at(y, p, 0.5)

    print("\n" + "=" * 78)
    print("推荐操作点")
    print("=" * 78)
    def show(title, r):
        print(f"\n【{title}】阈值 = {r['threshold']:.2f}")
        print(f"  准确率 {r['accuracy']:.4f}  |  恶性召回 {r['malignant_recall']:.4f} (漏诊 {r['miss_rate']:.2%})"
              f"  |  恶性精确 {r['malignant_precision']:.4f}")
        print(f"  良性召回 {r['benign_recall']:.4f} (误报 {r['false_alarm_rate']:.2%})  |  MacroF1 {r['macro_f1']:.4f}"
              f"  |  约登 {r['youden']:.4f}")
        c = r["confusion"]
        print(f"  混淆矩阵 TN={c['tn']} FP={c['fp']} FN={c['fn']} TP={c['tp']}")

    show("默认阈值 (argmax)", base)
    show("① 最大准确率", best_acc)
    show("② 约登指数最优 (Recall+Spec-1)", best_youden)
    show("③ 召回优先 (恶性召回≥95%)", recall_priority)

    print("\n" + "=" * 78)
    print("对比默认阈值 0.50 的收益")
    print("=" * 78)
    for name, r in [("最大准确率", best_acc), ("约登最优", best_youden), ("召回优先", recall_priority)]:
        da = (r["accuracy"] - base["accuracy"]) * 100
        dr = (r["malignant_recall"] - base["malignant_recall"]) * 100
        print(f"  {name:12s}: acc {da:+.2f}%  |  恶性召回 {dr:+.2f}%")

    # ---------- 保存 ----------
    result = {
        "model": args.model,
        "arch": arch,
        "img_size": img_size,
        "test_samples": len(ds),
        "n_malignant": n_mal,
        "n_benign": n_ben,
        "baseline_thr_0.5": base,
        "recommended": {
            "max_accuracy": best_acc,
            "best_youden": best_youden,
            "recall_priority": recall_priority,
        },
        "curve": rows,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {args.out}")

    # ---------- 画图 ----------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False

        th = [r["threshold"] for r in rows]
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))

        ax = axes[0]
        ax.plot(th, [r["accuracy"] for r in rows], "b-", label="Accuracy")
        ax.plot(th, [r["malignant_recall"] for r in rows], "r-", label="Malignant Recall")
        ax.plot(th, [r["benign_recall"] for r in rows], "g-", label="Benign Recall")
        ax.plot(th, [r["macro_f1"] for r in rows], "m--", label="Macro F1")
        ax.axvline(0.5, color="gray", ls=":", label="default 0.5")
        ax.axvline(best_acc["threshold"], color="b", ls=":", alpha=0.6)
        ax.axvline(recall_priority["threshold"], color="r", ls=":", alpha=0.6)
        ax.set_xlabel("Threshold"); ax.set_ylabel("Score")
        ax.set_title("Metrics vs Threshold"); ax.legend(fontsize=8); ax.grid(alpha=0.3)

        ax = axes[1]
        ax.plot(th, [r["youden"] for r in rows], "purple", label="Youden J")
        ax.axvline(best_youden["threshold"], color="purple", ls=":", alpha=0.6)
        ax.set_xlabel("Threshold"); ax.set_ylabel("Youden Index")
        ax.set_title("Youden Index (Recall+Specificity-1)"); ax.legend(fontsize=8); ax.grid(alpha=0.3)

        plt.tight_layout()
        png = os.path.join(os.path.dirname(args.out), "threshold_tuning.png")
        plt.savefig(png, dpi=110)
        print(f"曲线图已保存: {png}")
    except Exception as e:
        print(f"[WARN] 画图失败: {e}")


if __name__ == "__main__":
    main()
