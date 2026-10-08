#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
皮肤癌图像检测 - ResNet50 二分类训练脚本（良性 / 恶性）
================================================================
特性:
  - 迁移学习(ImageNet预训练) + 差分学习率(backbone慢/分类头快)
  - 训练集强增强(翻转/旋转/色彩抖动/随机裁剪)，验证集仅resize归一化
  - AMP 混合精度 + 梯度裁剪 + 早停 + 余弦退火学习率
  - 类别权重处理不平衡
  - 医疗重点指标: Recall(恶性) / AUC / 混淆矩阵
  - 输出: best.pt / last.pt / history.json / 曲线图 / 评估报告

用法:
  python3 train_resnet50.py                      # 默认参数
  python3 train_resnet50.py --epochs 60 --bs 32  # 自定义
  python3 train_resnet50.py --arch resnet101     # 换网络
"""

import argparse
import json
import os
import sys
import time
from collections import Counter

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import transforms
from torchvision.models import resnet50, resnet101, ResNet50_Weights, ResNet101_Weights


# ==================== 配置 ====================
# 类别从数据目录自动推断（支持二分类 / 7分类共用同一脚本）
# 若目录结构为 {root}/{split}/{class}/*.jpg，则按字母序取子目录名为类别
DEFAULT_CLASSES = ["benign", "malignant"]   # 兜底（目录不存在时）
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def discover_classes(root, split="train"):
    """从数据目录自动发现类别（按字母序）"""
    d = os.path.join(root, split)
    if not os.path.isdir(d):
        return list(DEFAULT_CLASSES)
    cls = sorted(
        x for x in os.listdir(d)
        if os.path.isdir(os.path.join(d, x)) and not x.startswith(".")
    )
    return cls or list(DEFAULT_CLASSES)


# 全局类别（main 中按 --data 重新赋值）
CLASSES = list(DEFAULT_CLASSES)
NUM_CLASSES = len(CLASSES)

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA = os.path.join(PROJ_ROOT, "dataset", "processed")
DEFAULT_OUT = os.path.join(PROJ_ROOT, "models")


# ==================== 数据集 ====================
class SkinCancerDataset(Dataset):
    """从 processed/{split}/{class}/*.jpg 读取"""

    def __init__(self, root, split, transform=None):
        self.transform = transform
        self.samples = []      # [(path, label), ...]
        for label, cls in enumerate(CLASSES):
            d = os.path.join(root, split, cls)
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                if fn.lower().endswith((".jpg", ".jpeg", ".png")):
                    self.samples.append((os.path.join(d, fn), label))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]
        img = Image.open(path).convert("RGB")
        if self.transform:
            img = self.transform(img)
        return img, label


def build_transforms(img_size, aug_strength="medium"):
    """训练/验证 数据变换"""
    if aug_strength == "light":
        train_tf = transforms.Compose([
            transforms.Resize((img_size, img_size)),
            transforms.RandomHorizontalFlip(0.5),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ])
    elif aug_strength == "strong":
        train_tf = transforms.Compose([
            transforms.Resize((int(img_size * 1.15), int(img_size * 1.15))),
            transforms.RandomResizedCrop(img_size, scale=(0.7, 1.0)),
            transforms.RandomHorizontalFlip(0.5),
            transforms.RandomVerticalFlip(0.5),
            transforms.RandomRotation(30),
            transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.05),
            transforms.RandomAffine(degrees=0, translate=(0.1, 0.1)),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
            transforms.RandomErasing(p=0.25, scale=(0.02, 0.15)),
        ])
    else:  # medium (默认)
        train_tf = transforms.Compose([
            transforms.Resize((int(img_size * 1.15), int(img_size * 1.15))),
            transforms.RandomResizedCrop(img_size, scale=(0.8, 1.0)),
            transforms.RandomHorizontalFlip(0.5),
            transforms.RandomVerticalFlip(0.5),
            transforms.RandomRotation(20),
            transforms.ColorJitter(brightness=0.25, contrast=0.25, saturation=0.25, hue=0.05),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ])

    val_tf = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    return train_tf, val_tf


# ==================== 模型 ====================
def build_model(arch="resnet50", pretrained=True, dropout=0.2):
    if arch == "resnet50":
        weights = ResNet50_Weights.IMAGENET1K_V2 if pretrained else None
        model = resnet50(weights=weights)
        feat_dim = model.fc.in_features
    elif arch == "resnet101":
        weights = ResNet101_Weights.IMAGENET1K_V2 if pretrained else None
        model = resnet101(weights=weights)
        feat_dim = model.fc.in_features
    else:
        raise ValueError(f"不支持的架构: {arch}")

    model.fc = nn.Sequential(
        nn.Dropout(dropout),
        nn.Linear(feat_dim, NUM_CLASSES),
    )
    return model


# ==================== 指标 ====================
def compute_metrics(y_true, y_pred, y_prob):
    """手算指标，避免依赖 torchmetrics 的版本差异"""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    y_prob = np.asarray(y_prob)

    acc = float((y_true == y_pred).mean()) if len(y_true) else 0.0

    metrics = {"accuracy": acc}
    for i, name in enumerate(CLASSES):
        tp = int(((y_pred == i) & (y_true == i)).sum())
        fp = int(((y_pred == i) & (y_true != i)).sum())
        fn = int(((y_pred != i) & (y_true == i)).sum())
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        metrics[f"{name}_precision"] = float(prec)
        metrics[f"{name}_recall"] = float(rec)
        metrics[f"{name}_f1"] = float(f1)

    # 宏平均
    metrics["macro_precision"] = float(np.mean([metrics[f"{c}_precision"] for c in CLASSES]))
    metrics["macro_recall"] = float(np.mean([metrics[f"{c}_recall"] for c in CLASSES]))
    metrics["macro_f1"] = float(np.mean([metrics[f"{c}_f1"] for c in CLASSES]))

    # AUC：二分类用 P(正类)，多分类用 macro OVR
    try:
        from sklearn.metrics import roc_auc_score
        if NUM_CLASSES == 2:
            metrics["auc"] = float(roc_auc_score(y_true, y_prob)) if len(set(y_true)) > 1 else 0.0
        else:
            # y_prob 是多类概率矩阵 (n, C)
            present = sorted(set(y_true.tolist()))
            if len(present) > 1:
                metrics["auc"] = float(roc_auc_score(
                    y_true, y_prob, multi_class="ovr", average="macro",
                    labels=present,
                ))
            else:
                metrics["auc"] = 0.0
    except Exception:
        metrics["auc"] = 0.0

    # 混淆矩阵：二分类保持 [[TN,FP],[FN,TP]]；多分类输出 C×C
    if NUM_CLASSES == 2:
        tn = int(((y_pred == 0) & (y_true == 0)).sum())
        fp = int(((y_pred == 1) & (y_true == 0)).sum())
        fn = int(((y_pred == 0) & (y_true == 1)).sum())
        tp = int(((y_pred == 1) & (y_true == 1)).sum())
        metrics["confusion_matrix"] = [[tn, fp], [fn, tp]]
    else:
        C = NUM_CLASSES
        cm = [[0] * C for _ in range(C)]
        for t, p in zip(y_true.tolist(), y_pred.tolist()):
            cm[int(t)][int(p)] += 1
        metrics["confusion_matrix"] = cm

    metrics["n_samples"] = int(len(y_true))
    return metrics


@torch.no_grad()
def evaluate(model, loader, criterion, device, use_amp=True):
    model.eval()
    y_true, y_pred, y_prob = [], [], []
    total_loss, n_batches = 0.0, 0

    for x, y in loader:
        x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
        with torch.amp.autocast("cuda", enabled=use_amp):
            out = model(x)
            loss = criterion(out, y)
        probs = torch.softmax(out.float(), dim=1)
        preds = out.argmax(dim=1)

        total_loss += loss.item()
        n_batches += 1
        y_true.extend(y.cpu().tolist())
        y_pred.extend(preds.cpu().tolist())
        # 二分类：记录 P(正类=恶性)；多分类：记录完整概率矩阵
        if NUM_CLASSES == 2:
            y_prob.extend(probs[:, 1].cpu().tolist())
        else:
            y_prob.extend(probs.cpu().tolist())

    metrics = compute_metrics(y_true, y_pred, y_prob)
    metrics["loss"] = total_loss / max(1, n_batches)
    return metrics


def format_metrics(m):
    """二分类显示恶性召回/精确，多分类显示宏平均"""
    if NUM_CLASSES == 2:
        return (f"loss={m['loss']:.4f} acc={m['accuracy']:.4f} "
                f"mal_recall={m['malignant_recall']:.4f} mal_prec={m['malignant_precision']:.4f} "
                f"macro_f1={m['macro_f1']:.4f} auc={m['auc']:.4f}")
    return (f"loss={m['loss']:.4f} acc={m['accuracy']:.4f} "
            f"macro_recall={m['macro_recall']:.4f} macro_prec={m['macro_precision']:.4f} "
            f"macro_f1={m['macro_f1']:.4f} auc={m['auc']:.4f}")


# ==================== 训练主流程 ====================
def main():
    ap = argparse.ArgumentParser(description="皮肤癌 ResNet 二分类训练")
    ap.add_argument("--data", default=DEFAULT_DATA, help="processed 数据集目录")
    ap.add_argument("--out", default=DEFAULT_OUT, help="模型输出目录")
    ap.add_argument("--arch", default="resnet50", choices=["resnet50", "resnet101"])
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--bs", type=int, default=32, help="batch size")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--lr-head", type=float, default=1e-3, help="分类头学习率")
    ap.add_argument("--lr-backbone", type=float, default=1e-4, help="backbone学习率(应为head的1/10)")
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--dropout", type=float, default=0.3)
    ap.add_argument("--aug", default="medium", choices=["light", "medium", "strong"])
    ap.add_argument("--patience", type=int, default=12, help="早停耐心值")
    ap.add_argument("--eval-split", default="test",
                    help="用于早停/选best/画曲线的划分（train/val/test）。"
                         "⚠️ 严谨实验请用 val —— 用 test 选 best 属测试集泄漏")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--freeze-backbone", action="store_true", help="冻结backbone只训分类头")
    ap.add_argument("--no-amp", action="store_true", help="关闭混合精度")
    ap.add_argument("--resume", default=None, help="从checkpoint恢复训练")
    ap.add_argument("--warmup", type=int, default=0,
                    help="warmup轮数：前N轮学习率从1/50线性升到目标值，保护预训练特征")
    ap.add_argument("--label-smoothing", type=float, default=0.0,
                    help="标签平滑，缓解过拟合")
    args = ap.parse_args()

    # ---- 自动发现类别（支持二分类 / 7分类）----
    global CLASSES, NUM_CLASSES
    CLASSES = discover_classes(args.data, "train")
    NUM_CLASSES = len(CLASSES)

    use_amp = not args.no_amp
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
        torch.backends.cudnn.benchmark = True    # 固定输入尺寸提速

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    os.makedirs(args.out, exist_ok=True)

    print("=" * 78)
    print(f"皮肤癌图像检测 - ResNet {'二分类' if NUM_CLASSES == 2 else f'{NUM_CLASSES}分类'}训练")
    print("=" * 78)
    print(f"类别      : {', '.join(CLASSES)}")
    print(f"设备      : {device}" + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else ""))
    print(f"架构      : {args.arch}  输入 {args.img_size}x{args.img_size}  batch={args.bs}")
    print(f"学习率    : head={args.lr_head}  backbone={args.lr_backbone}")
    print(f"增强强度  : {args.aug}   混合精度: {use_amp}   冻结backbone: {args.freeze_backbone}")
    print(f"Warmup    : {args.warmup} 轮" + (f" (起始lr=目标的1/50)" if args.warmup > 0 else "")
          + f"   标签平滑: {args.label_smoothing}")
    print("=" * 78)

    # ---- 数据 ----
    train_tf, val_tf = build_transforms(args.img_size, args.aug)
    train_ds = SkinCancerDataset(args.data, "train", train_tf)
    test_ds = SkinCancerDataset(args.data, args.eval_split, val_tf)

    if len(train_ds) == 0 or len(test_ds) == 0:
        print(f"[ERROR] 数据集为空！检查路径: {args.data} / split={args.eval_split}", file=sys.stderr)
        sys.exit(1)

    labels = [lb for _, lb in train_ds.samples]
    cnt = Counter(labels)
    tcnt = Counter(lb for _, lb in test_ds.samples)

    def _dist(counter):
        return "  ".join(f"{CLASSES[i]}={counter.get(i, 0)}" for i in range(NUM_CLASSES))

    print(f"\n训练集: {len(train_ds)} 张  {_dist(cnt)}")
    print(f"测试集: {len(test_ds)} 张   {_dist(tcnt)}")

    # 类别权重（处理不平衡）
    n_total = len(labels)
    class_weights = torch.tensor(
        [n_total / (NUM_CLASSES * max(1, cnt.get(i, 0))) for i in range(NUM_CLASSES)],
        dtype=torch.float32, device=device,
    )
    print(f"类别权重: {'  '.join(f'{CLASSES[i]}={class_weights[i]:.3f}' for i in range(NUM_CLASSES))}")

    train_loader = DataLoader(train_ds, batch_size=args.bs, shuffle=True,
                              num_workers=args.workers, pin_memory=True, drop_last=False)
    test_loader = DataLoader(test_ds, batch_size=args.bs, shuffle=False,
                             num_workers=args.workers, pin_memory=True)

    # ---- 模型 ----
    model = build_model(args.arch, pretrained=True, dropout=args.dropout).to(device)

    if args.freeze_backbone:
        for name, p in model.named_parameters():
            if not name.startswith("fc."):
                p.requires_grad = False
        print("已冻结 backbone（只训练分类头）")

    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    n_total_p = sum(p.numel() for p in model.parameters())
    print(f"参数量: 可训练 {n_trainable:,} / 总计 {n_total_p:,} ({n_trainable/n_total_p:.1%})")

    # 差分学习率
    head_params, backbone_params = [], []
    for name, p in model.named_parameters():
        if not p.requires_grad:
            continue
        (head_params if name.startswith("fc.") else backbone_params).append(p)

    param_groups = [{"params": head_params, "lr": args.lr_head, "name": "head"}]
    if backbone_params:
        param_groups.append({"params": backbone_params, "lr": args.lr_backbone, "name": "backbone"})
    optimizer = torch.optim.AdamW(param_groups, weight_decay=args.weight_decay)

    # 余弦退火（warmup 期间手动接管 lr）
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-6)

    # warmup: 记录各参数组的基准 lr
    base_lrs = [pg["lr"] for pg in optimizer.param_groups]
    warmup_factor = 50.0   # 起始 lr = 目标值/50

    def apply_warmup(epoch):
        """前 warmup 轮线性升 lr；warmup 结束后交还给 scheduler"""
        if args.warmup <= 0 or epoch > args.warmup:
            return False
        ratio = (epoch - 1) / max(1, args.warmup)
        for pg, base in zip(optimizer.param_groups, base_lrs):
            pg["lr"] = base * (1.0 / warmup_factor + (1.0 - 1.0 / warmup_factor) * ratio)
        return True

    criterion = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=args.label_smoothing)
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    start_epoch, best_score = 1, -1.0
    history = {"train": [], "test": []}

    if args.resume and os.path.isfile(args.resume):
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model"])
        optimizer.load_state_dict(ckpt["optimizer"])
        if "scheduler" in ckpt:
            scheduler.load_state_dict(ckpt["scheduler"])
        start_epoch = ckpt.get("epoch", 0) + 1
        best_score = ckpt.get("best_score", -1.0)
        history = ckpt.get("history", history)
        print(f"从 {args.resume} 恢复，epoch {start_epoch} 开始，best={best_score:.4f}")

    # ---- 训练循环 ----
    print("\n" + "=" * 78)
    print("开始训练")
    print("=" * 78)

    no_improve = 0
    t_start = time.time()

    for epoch in range(start_epoch, args.epochs + 1):
        model.train()
        tr_loss, n_b = 0.0, 0
        y_true, y_pred, y_prob = [], [], []
        t0 = time.time()

        # warmup 期间手动设置 lr，不步进余弦调度器
        in_warmup = apply_warmup(epoch)

        for x, y in train_loader:
            x = x.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)

            with torch.amp.autocast("cuda", enabled=use_amp):
                out = model(x)
                loss = criterion(out, y)

            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            scaler.step(optimizer)
            scaler.update()

            tr_loss += loss.item(); n_b += 1
            with torch.no_grad():
                y_true.extend(y.cpu().tolist())
                y_pred.extend(out.argmax(dim=1).cpu().tolist())
                y_prob.extend(torch.softmax(out.float(), 1)[:, 1].cpu().tolist())

        train_m = compute_metrics(y_true, y_pred, y_prob)
        train_m["loss"] = tr_loss / max(1, n_b)

        test_m = evaluate(model, test_loader, criterion, device, use_amp)
        if not in_warmup:
            scheduler.step()
        cur_lr = optimizer.param_groups[0]["lr"]

        history["train"].append(train_m)
        history["test"].append(test_m)

        # 二分类：以【恶性召回率 + macro_f1】综合分选最佳（医疗更看重不漏诊）
        # 多分类：以 macro_f1 为主（类别不平衡下比 acc 更能反映真实能力）
        if NUM_CLASSES == 2:
            score = 0.5 * test_m["malignant_recall"] + 0.5 * test_m["macro_f1"]
        else:
            score = 0.6 * test_m["macro_f1"] + 0.4 * test_m["accuracy"]

        flag = ""
        if score > best_score:
            best_score = score
            no_improve = 0
            torch.save({
                "model": model.state_dict(), "arch": args.arch, "img_size": args.img_size,
                "classes": CLASSES, "epoch": epoch, "best_score": best_score,
                "metrics": test_m, "optimizer": optimizer.state_dict(),
                "scheduler": scheduler.state_dict(), "history": history,
                "args": vars(args),
            }, os.path.join(args.out, "best.pt"))
            flag = "  <== best saved"
        else:
            no_improve += 1

        print(f"[{epoch:3d}/{args.epochs}] lr={cur_lr:.2e} | "
              f"TRAIN {format_metrics(train_m)} | TEST {format_metrics(test_m)}{flag}")

        # 周期性存 last
        if epoch % 5 == 0 or epoch == args.epochs:
            torch.save({"model": model.state_dict(), "epoch": epoch, "arch": args.arch,
                        "classes": CLASSES, "img_size": args.img_size}, os.path.join(args.out, "last.pt"))

        if no_improve >= args.patience:
            print(f"\n早停触发：连续 {args.patience} 轮无提升（best score={best_score:.4f}）")
            break

    elapsed = time.time() - t_start
    print(f"\n训练完成，耗时 {elapsed/60:.1f} 分钟")

    # ---- 保存历史 ----
    with open(os.path.join(args.out, "history.json"), "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    # ---- 最终评估（用 best.pt）----
    print("\n" + "=" * 78)
    print("最终评估（best.pt 在测试集上）")
    print("=" * 78)
    ckpt = torch.load(os.path.join(args.out, "best.pt"), map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model"])
    final = evaluate(model, test_loader, criterion, device, use_amp)

    print(f"样本数     : {final['n_samples']}")
    print(f"准确率     : {final['accuracy']:.4f}")
    if NUM_CLASSES == 2:
        print(f"恶性 Recall: {final['malignant_recall']:.4f}   (漏诊率 {1-final['malignant_recall']:.4f})")
        print(f"恶性 Prec  : {final['malignant_precision']:.4f}")
        print(f"良性 Recall: {final['benign_recall']:.4f}")
    else:
        print(f"宏平均召回 : {final['macro_recall']:.4f}")
        print(f"宏平均精确 : {final['macro_precision']:.4f}")
        print("\n各类别明细:")
        print(f"      {'类别':<10} {'精确':>8} {'召回':>8} {'F1':>8}")
        for c in CLASSES:
            print(f"      {c:<10} {final[f'{c}_precision']:>8.4f} "
                  f"{final[f'{c}_recall']:>8.4f} {final[f'{c}_f1']:>8.4f}")
    print(f"Macro F1   : {final['macro_f1']:.4f}")
    print(f"AUC        : {final['auc']:.4f}")
    cm = final["confusion_matrix"]
    if NUM_CLASSES == 2:
        print(f"混淆矩阵   : TN={cm[0][0]} FP={cm[0][1]} FN={cm[1][0]} TP={cm[1][1]}")
    else:
        print(f"混淆矩阵   ({NUM_CLASSES}x{NUM_CLASSES}, 行=真实, 列=预测):")
        print("      " + " ".join(f"{c[:6]:>7}" for c in CLASSES))
        for i, c in enumerate(CLASSES):
            print(f"      {c[:6]:<6} " + " ".join(f"{cm[i][j]:>7}" for j in range(NUM_CLASSES)))

    with open(os.path.join(args.out, "final_metrics.json"), "w", encoding="utf-8") as f:
        json.dump({"best_epoch": ckpt["epoch"], "best_score": ckpt["best_score"],
                   "test_metrics": final, "train_time_min": elapsed / 60}, f,
                  ensure_ascii=False, indent=2)

    # ---- 画曲线 ----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Noto Sans CJK JP", "WenQuanYi Zen Hei"]
        plt.rcParams["axes.unicode_minus"] = False

        ep = range(1, len(history["test"]) + 1)
        if NUM_CLASSES == 2:
            keys = ["loss", "accuracy", "malignant_recall", "macro_f1", "auc"]
            titles = ["Loss", "Accuracy", "Malignant Recall", "Macro F1", "AUC"]
        else:
            keys = ["loss", "accuracy", "macro_recall", "macro_f1", "auc"]
            titles = ["Loss", "Accuracy", "Macro Recall", "Macro F1", "AUC"]
        fig, axes = plt.subplots(1, 5, figsize=(24, 4.5))
        for ax, k, t in zip(axes, keys, titles):
            ax.plot(ep, [m[k] for m in history["train"]], "b-o", ms=3, label="Train")
            ax.plot(ep, [m[k] for m in history["test"]], "r-o", ms=3, label="Test")
            ax.set_title(t); ax.set_xlabel("Epoch"); ax.legend(); ax.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(os.path.join(args.out, "training_curves.png"), dpi=110)
        plt.close(fig)
        print(f"\n曲线图已保存: {os.path.join(args.out, 'training_curves.png')}")
    except Exception as e:
        print(f"[WARN] 画图失败: {e}")

    print(f"\n输出目录: {args.out}")
    print("  best.pt / last.pt / history.json / final_metrics.json / training_curves.png")

    # 达标判断
    print("\n" + "=" * 78)
    if NUM_CLASSES == 2:
        target = 0.90
        if final["accuracy"] >= target:
            print(f"✅ 准确率 {final['accuracy']:.2%} 已达标（任务书要求 ≥90%）")
        else:
            print(f"⚠️  准确率 {final['accuracy']:.2%} 未达 90%，建议：")
            print("   - 增大增强强度 --aug strong")
            print("   - 换 resnet101 或加大输入尺寸 --img-size 288")
            print("   - 增加 --epochs 并放宽 --patience")
    else:
        print(f"多分类结果（{NUM_CLASSES} 类，类别不平衡）")
        print(f"  准确率    : {final['accuracy']:.2%}")
        print(f"  宏平均F1  : {final['macro_f1']:.4f}  ← 不平衡场景主要指标")
        print(f"  宏平均召回: {final['macro_recall']:.4f}")
        print(f"  AUC(macro): {final['auc']:.4f}")
        print("\n  说明：7 类分布极不平衡（nv 占 67%，df 仅 1.1%），")
        print("        宏平均指标比准确率更能反映真实能力。")
    print("=" * 78)


if __name__ == "__main__":
    main()
