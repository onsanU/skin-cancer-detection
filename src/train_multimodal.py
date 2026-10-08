#!/usr/bin/env python3
"""
皮肤癌图像检测 - 图像 + 临床元数据 多模态融合训练

设计原理：
  HAM10000 二分类中，临床元数据有强区分力（实测验证）：
    · 年龄:  0-30岁恶性占比 4.1% → 80+岁 50.1%  (跨度46%)
    · 部位:  躯干 4.2% → 面部 42.7%             (跨度38.5%)
    · 性别:  男 22.7% / 女 16.0%                (弱)

架构（双分支）:
    ┌─────────────┐        ┌──────────────────┐
    │  图像 224²  │        │ 临床特征 (age,   │
    │  ResNet50   │        │ sex, site 编码)  │
    │  → 2048维   │        │  → MLP → 64维    │
    └──────┬──────┘        └────────┬─────────┘
           │                        │
           └──────── concat ────────┘
                      ↓
                 分类头 → 2类

临床特征编码:
    age:          归一化 (0-1) + 分箱 one-hot (7箱)
    sex:          one-hot (male/female/unknown)
    localization: one-hot (15个部位，按训练集出现的位置)
    → 合计 7 + 3 + 15 = 25 维

用法:
  python3 train_multimodal.py --data dataset/processed_v2_full \
      --meta dataset/HAM10000_raw/HAM10000_metadata.csv \
      --out models_multimodal_v1 --epochs 30 --warmup 3
"""
import argparse
import csv
import json
import os
import sys
import time
from collections import Counter

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import resnet50, resnet101, ResNet50_Weights

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

# 年龄分箱（依据实测的恶性占比拐点）
AGE_BINS = [0, 30, 40, 50, 60, 70, 80, 200]
SEXES = ["male", "female", "unknown"]
# 部位列表（HAM10000 的 15 个）
SITES = ["back", "lower extremity", "trunk", "upper extremity", "abdomen",
         "face", "chest", "foot", "unknown", "neck", "scalp", "hand",
         "ear", "genital", "acral"]


def load_meta(meta_csv):
    """返回 {image_id: {...临床字段}}"""
    out = {}
    for r in csv.DictReader(open(meta_csv, encoding="utf-8-sig")):
        iid = (r.get("image_id") or "").strip()
        if not iid:
            continue
        age = r.get("age", "")
        try:
            age_v = float(age) if age and age.strip() else np.nan
        except ValueError:
            age_v = np.nan
        out[iid] = {
            "age": age_v,
            "sex": (r.get("sex") or "unknown").strip().lower(),
            "site": (r.get("localization") or "unknown").strip().lower(),
        }
    return out


def encode_clinical(meta, age_mean, age_std):
    """把一条临床记录编码成向量"""
    # --- age ---
    a = meta["age"]
    if np.isnan(a):
        a_norm = 0.0
        a_bin = 0
    else:
        a_norm = (a - age_mean) / (age_std + 1e-6)
        a_bin = 0
        for i in range(len(AGE_BINS) - 1):
            if AGE_BINS[i] <= a < AGE_BINS[i + 1]:
                a_bin = i
                break
    age_feat = [a_norm] + [1.0 if i == a_bin else 0.0 for i in range(len(AGE_BINS) - 1)]
    # --- sex ---
    sex_feat = [1.0 if meta["sex"] == s else 0.0 for s in SEXES]
    # --- site ---
    site = meta["site"]
    site_feat = [1.0 if site == s else 0.0 for s in SITES]
    return np.array(age_feat + sex_feat + site_feat, dtype=np.float32)


class MultiModalDS(Dataset):
    def __init__(self, root, split, transform, classes, id2meta, age_mean, age_std):
        self.transform = transform
        self.samples = []
        self.id2meta = id2meta
        self.age_mean = age_mean
        self.age_std = age_std
        for label, cls in enumerate(classes):
            d = os.path.join(root, split, cls)
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                if fn.lower().endswith((".jpg", ".jpeg", ".png")):
                    iid = os.path.splitext(fn)[0]
                    self.samples.append((os.path.join(d, fn), label, iid))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        p, y, iid = self.samples[i]
        img = Image.open(p).convert("RGB")
        meta = self.id2meta.get(iid, {"age": np.nan, "sex": "unknown", "site": "unknown"})
        clin = encode_clinical(meta, self.age_mean, self.age_std)
        return self.transform(img), torch.from_numpy(clin), y


class MultiModalNet(nn.Module):
    """图像分支 + 临床分支 → 融合分类"""

    def __init__(self, num_classes=2, arch="resnet50", clin_dim=25,
                 clin_hidden=64, dropout=0.3, meta_dropout=0.1,
                 pretrained=True):
        super().__init__()
        if arch.startswith("resnet101"):
            backbone = resnet101(weights=ResNet101_Weights.DEFAULT if pretrained else None)
            img_dim = 2048
        else:
            backbone = resnet50(weights=ResNet50_Weights.DEFAULT if pretrained else None)
            img_dim = 2048
        # 去掉原分类头
        self.backbone = nn.Sequential(*list(backbone.children())[:-1])  # → (B,2048,1,1)

        # 临床分支: 小 MLP
        self.clin_branch = nn.Sequential(
            nn.Linear(clin_dim, clin_hidden),
            nn.BatchNorm1d(clin_hidden),
            nn.ReLU(inplace=True),
            nn.Dropout(meta_dropout),
            nn.Linear(clin_hidden, clin_hidden),
            nn.ReLU(inplace=True),
        )

        # 融合头
        self.head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(img_dim + clin_hidden, num_classes),
        )
        self.meta_dropout = meta_dropout

    def forward(self, img, clin):
        f_img = self.backbone(img).flatten(1)               # (B,2048)
        f_clin = self.clin_branch(clin)                     # (B,64)
        # 训练时随机丢掉临床特征（防止模型过度依赖元数据）
        if self.training and self.meta_dropout > 0:
            keep = (torch.rand(f_clin.size(0), 1, device=f_clin.device) > 0.15).float()
            f_clin = f_clin * keep
        return self.head(torch.cat([f_img, f_clin], dim=1))


def build_transforms(img_size, aug="medium"):
    if aug == "light":
        tr = transforms.Compose([
            transforms.Resize((img_size, img_size)),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])
    elif aug == "strong":
        tr = transforms.Compose([
            transforms.Resize((int(img_size * 1.15), int(img_size * 1.15))),
            transforms.RandomResizedCrop(img_size, scale=(0.7, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomVerticalFlip(),
            transforms.RandomRotation(20),
            transforms.ColorJitter(0.3, 0.3, 0.3, 0.1),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])
    else:
        tr = transforms.Compose([
            transforms.Resize((int(img_size * 1.1), int(img_size * 1.1))),
            transforms.RandomResizedCrop(img_size, scale=(0.85, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomRotation(15),
            transforms.ColorJitter(0.2, 0.2, 0.2, 0.05),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])
    va = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])
    return tr, va


def metrics_from_logits(logits, y, num_classes=2):
    prob = F.softmax(logits, dim=1)[:, 1].detach().cpu().numpy()
    y = y.detach().cpu().numpy()
    pred = (prob >= 0.5).astype(int)
    out = {}
    acc = (pred == y).mean()
    out["accuracy"] = float(acc)
    if num_classes == 2:
        tp = int(((pred == 1) & (y == 1)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
        tn = int(((pred == 0) & (y == 0)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
        out["malignant_recall"] = float(tp / (tp + fn)) if (tp + fn) else 0.0
        out["malignant_precision"] = float(tp / (tp + fp)) if (tp + fp) else 0.0
        out["benign_recall"] = float(tn / (tn + fp)) if (tn + fp) else 0.0
        out["confusion_matrix"] = [[tn, fp], [fn, tp]]
        p1 = out["malignant_precision"]; r1 = out["malignant_recall"]
        p0 = out["benign_recall"]
        out["benign_precision"] = float(tn / (tn + fn)) if (tn + fn) else 0.0
        f1_m = 2 * p1 * r1 / (p1 + r1) if (p1 + r1) else 0.0
        f1_b = 2 * out["benign_precision"] * p0 / (out["benign_precision"] + p0) if (out["benign_precision"] + p0) else 0.0
        out["macro_f1"] = float((f1_m + f1_b) / 2)
        # AUC
        order = np.argsort(prob); ranks = np.empty(len(prob), float); ranks[order] = np.arange(1, len(prob) + 1)
        n1 = int((y == 1).sum()); n0 = int((y == 0).sum())
        out["auc"] = float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else 0.0
        out["_prob"] = prob
        out["_y"] = y
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="数据集目录（含 train/val/test）")
    ap.add_argument("--meta", required=True, help="HAM10000_metadata.csv")
    ap.add_argument("--out", default="models_multimodal", help="输出目录")
    ap.add_argument("--arch", default="resnet50", choices=["resnet50", "resnet101"])
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--lr-head", type=float, default=5e-4)
    ap.add_argument("--lr-backbone", type=float, default=5e-5)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--dropout", type=float, default=0.3)
    ap.add_argument("--meta-dropout", type=float, default=0.1)
    ap.add_argument("--aug", default="medium", choices=["light", "medium", "strong"])
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--patience", type=int, default=12)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--eval-split", default="test", help="用于选best/早停的划分")
    ap.add_argument("--class-weight-mode", default="sqrt", choices=["none", "sqrt", "full"],
                    help="类别权重: none=不加(1:1) / sqrt=平方根逆频率(温和) / full=完整逆频率(激进,易过拟合)")
    ap.add_argument("--no-pretrained", action="store_true")
    args = ap.parse_args()

    torch.manual_seed(args.seed); np.random.seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    os.makedirs(args.out, exist_ok=True)

    print("=" * 78)
    print("皮肤癌检测 - 多模态（图像 + 临床元数据）训练")
    print("=" * 78)
    print(f"数据      : {args.data}")
    print(f"元数据    : {args.meta}")
    print(f"输出      : {args.out}")
    print(f"架构      : {args.arch} @ {args.img_size}  设备: {device}")
    print(f"学习率    : head={args.lr_head}  backbone={args.lr_backbone}")
    print(f"元数据dropout: {args.meta_dropout}   评估划分: {args.eval_split}")
    print("=" * 78)

    # ---- 元数据 ----
    id2meta = load_meta(args.meta)
    ages = [v["age"] for v in id2meta.values() if not np.isnan(v["age"])]
    age_mean, age_std = float(np.mean(ages)), float(np.std(ages))
    print(f"\n元数据: {len(id2meta)} 条   年龄均值 {age_mean:.1f} 标准差 {age_std:.1f}")

    # ---- 类别 ----
    d = os.path.join(args.data, "train")
    CLASSES = sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))) or ["benign", "malignant"]
    NUM_CLASSES = len(CLASSES)
    print(f"类别: {CLASSES}")

    train_tf, val_tf = build_transforms(args.img_size, args.aug)
    train_ds = MultiModalDS(args.data, "train", train_tf, CLASSES, id2meta, age_mean, age_std)
    eval_ds = MultiModalDS(args.data, args.eval_split, val_tf, CLASSES, id2meta, age_mean, age_std)
    if len(train_ds) == 0 or len(eval_ds) == 0:
        print(f"[ERROR] 数据集为空: train={len(train_ds)} eval={len(eval_ds)}")
        sys.exit(1)

    labels = [s[1] for s in train_ds.samples]
    cnt = Counter(labels)
    print(f"\n训练集: {len(train_ds)} 张  " + "  ".join(f"{CLASSES[i]}={cnt.get(i,0)}" for i in range(NUM_CLASSES)))
    ecnt = Counter(s[1] for s in eval_ds.samples)
    print(f"{args.eval_split}集: {len(eval_ds)} 张  " + "  ".join(f"{CLASSES[i]}={ecnt.get(i,0)}" for i in range(NUM_CLASSES)))

    n_total = len(labels)
    if args.class_weight_mode == "none":
        class_weights = torch.ones(NUM_CLASSES, dtype=torch.float32, device=device)
        wdesc = "不加权重 (1:1)"
    elif args.class_weight_mode == "sqrt":
        # 温和：逆频率开平方，避免过度偏袒少数类
        raw = [n_total / (NUM_CLASSES * max(1, cnt.get(i, 0))) for i in range(NUM_CLASSES)]
        class_weights = torch.tensor([r ** 0.5 for r in raw], dtype=torch.float32, device=device)
        wdesc = "平方根逆频率 (温和)"
    else:
        class_weights = torch.tensor(
            [n_total / (NUM_CLASSES * max(1, cnt.get(i, 0))) for i in range(NUM_CLASSES)],
            dtype=torch.float32, device=device)
        wdesc = "完整逆频率 (激进)"
    print(f"类别权重[{wdesc}]: " + "  ".join(f"{CLASSES[i]}={class_weights[i]:.3f}" for i in range(NUM_CLASSES)))

    train_loader = DataLoader(train_ds, batch_size=args.bs, shuffle=True,
                              num_workers=args.workers, pin_memory=True)
    eval_loader = DataLoader(eval_ds, batch_size=args.bs, shuffle=False,
                             num_workers=args.workers, pin_memory=True)

    # ---- 模型 ----
    clin_dim = 1 + (len(AGE_BINS) - 1) + len(SEXES) + len(SITES)
    model = MultiModalNet(NUM_CLASSES, args.arch, clin_dim, 64, args.dropout,
                          args.meta_dropout, pretrained=not args.no_pretrained).to(device)
    n_param = sum(p.numel() for p in model.parameters())
    print(f"参数量: {n_param/1e6:.2f}M  (临床特征维度 {clin_dim})")

    # 差分学习率
    bb_params, other_params = [], []
    for n, p in model.named_parameters():
        (bb_params if n.startswith("backbone.") else other_params).append(p)
    optimizer = torch.optim.AdamW([
        {"params": bb_params, "lr": args.lr_backbone},
        {"params": other_params, "lr": args.lr_head},
    ], weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    criterion = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=0.0)
    scaler = torch.amp.GradScaler("cuda", enabled=(device == "cuda"))

    base_lrs = [args.lr_backbone, args.lr_head]
    history = {"train": [], "eval": []}
    best_score, no_improve = -1.0, 0
    t0 = time.time()

    for epoch in range(1, args.epochs + 1):
        # ---- 学习率调度：先 warmup 线性升，再余弦退火 ----
        if args.warmup > 0 and epoch <= args.warmup:
            factor = epoch / (args.warmup + 1)          # 线性升到接近目标值
            for gi, g in enumerate(optimizer.param_groups):
                g["lr"] = base_lrs[gi] * factor
        else:
            # warmup 结束：先确保回到基准 lr，再交给余弦退火
            if args.warmup > 0 and epoch == args.warmup + 1:
                for gi, g in enumerate(optimizer.param_groups):
                    g["lr"] = base_lrs[gi]
            else:
                # 余弦退火（scheduler.step 在轮末调用，这里同步 lr）
                for gi, g in enumerate(optimizer.param_groups):
                    g["lr"] = scheduler.get_last_lr()[gi]

        # ---- train ----
        model.train()
        tl, tc, tn = 0.0, 0, 0
        for img, clin, y in train_loader:
            img, clin, y = img.to(device), clin.to(device), y.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=(device == "cuda")):
                logits = model(img, clin)
                loss = criterion(logits, y)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            scaler.step(optimizer); scaler.update()
            tl += loss.item() * y.size(0)
            tc += (logits.argmax(1) == y).sum().item(); tn += y.size(0)
        tr_loss, tr_acc = tl / max(1, tn), tc / max(1, tn)

        # ---- eval ----
        model.eval()
        all_logits, all_y = [], []
        el, en = 0.0, 0
        with torch.no_grad():
            for img, clin, y in eval_loader:
                img, clin, y = img.to(device), clin.to(device), y.to(device)
                with torch.amp.autocast("cuda", enabled=(device == "cuda")):
                    logits = model(img, clin)
                    loss = criterion(logits, y)
                all_logits.append(logits.float()); all_y.append(y)
                el += loss.item() * y.size(0); en += y.size(0)
        logits_cat = torch.cat(all_logits); y_cat = torch.cat(all_y)
        em = metrics_from_logits(logits_cat, y_cat, NUM_CLASSES)
        em["loss"] = el / max(1, en)

        history["train"].append({"loss": tr_loss, "acc": tr_acc})
        history["eval"].append({k: v for k, v in em.items() if not k.startswith("_")})

        lr_now = optimizer.param_groups[0]["lr"]
        print(f"[{epoch:3d}/{args.epochs}] lr={lr_now:.2e} | "
              f"TRAIN loss={tr_loss:.4f} acc={tr_acc:.4f} | "
              f"{args.eval_split.upper()} loss={em['loss']:.4f} acc={em['accuracy']:.4f} "
              f"mal_recall={em.get('malignant_recall',0):.4f} auc={em.get('auc',0):.4f}")

        # best（综合分：召回 + macro_f1）
        score = 0.5 * em.get("malignant_recall", 0) + 0.5 * em.get("macro_f1", 0)
        if score > best_score:
            best_score, no_improve = score, 0
            torch.save({
                "model": model.state_dict(),
                "arch": args.arch, "img_size": args.img_size,
                "classes": CLASSES, "epoch": epoch, "best_score": best_score,
                "metrics": {k: v for k, v in em.items() if not k.startswith("_")},
                "clinical": {"age_mean": age_mean, "age_std": age_std,
                             "age_bins": AGE_BINS, "sexes": SEXES, "sites": SITES,
                             "clin_dim": clin_dim},
                "optimizer": optimizer.state_dict(),
                "scheduler": scheduler.state_dict(),
                "history": history,
            }, os.path.join(args.out, "best.pt"))
            print(f"         <== best saved (score={score:.4f})")
        else:
            no_improve += 1
            if no_improve >= args.patience:
                print(f"\n早停：连续 {args.patience} 轮无提升 (best={best_score:.4f})")
                break
        if epoch > args.warmup:
            scheduler.step()

    print(f"\n训练完成，耗时 {(time.time()-t0)/60:.1f} 分钟，best score={best_score:.4f}")
    json.dump({"best_score": best_score, "history": history,
               "args": vars(args), "clinical": {"age_mean": age_mean, "age_std": age_std}},
              open(os.path.join(args.out, "history.json"), "w"), ensure_ascii=False, indent=2)
    print(f"输出目录: {args.out}")


if __name__ == "__main__":
    main()
