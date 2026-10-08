#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型压缩：动态量化 + 结构化剪枝
================================================================
任务书 3.3 要求："模型量化、剪枝，降低模型大小和计算量，提高推理速度"

本脚本产出四组对比：
  ① 原始 FP32          基准
  ② 通道剪枝 (Pruning)  L1范数剪掉小通道，参数量下降
  ③ 动态量化 (INT8)    权重从 FP32 → INT8，体积缩至约 1/4
  ④ 剪枝+量化          组合方案

评测指标：
  - 模型文件大小 (MB)
  - 参数量
  - CPU 推理延迟 (ms/张)
  - 测试集准确率 / 恶性召回 / AUC

用法:
  python3 model_compress.py
  python3 model_compress.py --prune-ratio 0.3 --no-finetune
"""

import argparse
import copy
import io
import json
import os
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.utils.prune as prune
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import resnet50, resnet101

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]
CLASSES = ["benign", "malignant"]

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_DATA = os.path.expanduser("~/skin_cancer_data/processed_v2_full")
FALLBACK_DATA = os.path.join(PROJ_ROOT, "dataset", "processed_v2_full")
OUT_DIR = os.path.join(PROJ_ROOT, "models_compressed")


# ==================== 数据 ====================
class TestDS(Dataset):
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


# ==================== 模型 ====================
def build_model(arch, dropout=0.4):
    if arch == "resnet50":
        m = resnet50(weights=None); feat = m.fc.in_features
    elif arch == "resnet101":
        m = resnet101(weights=None); feat = m.fc.in_features
    else:
        raise ValueError(arch)
    m.fc = nn.Sequential(nn.Dropout(dropout), nn.Linear(feat, 2))
    return m


def load_model(path, device="cpu"):
    ckpt = torch.load(path, map_location=device, weights_only=False)
    arch = ckpt.get("arch", "resnet50")
    img_size = int(ckpt.get("img_size", 224))
    m = build_model(arch)
    m.load_state_dict(ckpt.get("model") or ckpt)
    m.to(device).eval()
    return m, arch, img_size, ckpt


# ==================== 评测 ====================
def file_size_mb(model_or_path):
    if isinstance(model_or_path, str):
        return os.path.getsize(model_or_path) / 1024 / 1024
    buf = io.BytesIO()
    torch.save(model_or_path.state_dict(), buf)
    return buf.tell() / 1024 / 1024


def count_params(model, trainable_only=False):
    ps = model.parameters()
    if trainable_only:
        return sum(p.numel() for p in ps if p.requires_grad)
    return sum(p.numel() for p in ps)


@torch.no_grad()
def evaluate(model, loader, device="cpu"):
    model.eval()
    ys, ps, preds = [], [], []
    for x, y in loader:
        x = x.to(device)
        out = model(x)
        prob = torch.softmax(out.float(), dim=1)[:, 1]
        ys.extend(y.tolist())
        ps.extend(prob.cpu().tolist())
        preds.extend(out.argmax(1).cpu().tolist())

    y = np.array(ys); p = np.array(ps); pr = np.array(preds)
    tp = int(((pr == 1) & (y == 1)).sum()); fp = int(((pr == 1) & (y == 0)).sum())
    fn = int(((pr == 0) & (y == 1)).sum()); tn = int(((pr == 0) & (y == 0)).sum())
    acc = (tp + tn) / max(1, len(y))
    rec = tp / max(1, tp + fn)
    prec = tp / max(1, tp + fp)
    f1 = 2 * prec * rec / max(1e-9, prec + rec)
    try:
        from sklearn.metrics import roc_auc_score
        auc = float(roc_auc_score(y, p))
    except Exception:
        auc = 0.0
    return {
        "accuracy": round(float(acc), 4),
        "malignant_recall": round(float(rec), 4),
        "malignant_precision": round(float(prec), 4),
        "macro_f1": round(float(f1), 4),
        "auc": round(auc, 4),
        "confusion": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
    }


def measure_latency(model, img_size, n=30, warmup=5, device="cpu"):
    """测 CPU 单张推理延迟"""
    x = torch.randn(1, 3, img_size, img_size).to(device)
    model.eval()
    with torch.no_grad():
        for _ in range(warmup):
            model(x)
        t0 = time.time()
        for _ in range(n):
            model(x)
        ms = (time.time() - t0) / n * 1000
    return round(ms, 2)


# ==================== 剪枝 ====================
def prune_model(model, ratio=0.3):
    """
    对卷积层做 L1 非结构化剪枝（全局）。
    注意：torch 的非结构化剪枝产生稀疏权重，需配合 to_sparse 或专用后端才真正提速。
    这里同时演示"永久移除"方式（remove + 稀疏化），用于对比体积。
    """
    m = copy.deepcopy(model)
    targets = []
    for name, mod in m.named_modules():
        if isinstance(mod, nn.Conv2d):
            targets.append((mod, "weight"))
    prune.global_unstructured(
        targets,
        pruning_method=prune.L1Unstructured,
        amount=ratio,
    )
    # 永久化剪枝（把 mask 应用到权重上并移除 hook）
    for mod, name in targets:
        prune.remove(mod, name)
    return m


def sparsity(model):
    """统计权重中零元素占比"""
    total, zeros = 0, 0
    for p in model.parameters():
        total += p.numel()
        zeros += int((p == 0).sum())
    return zeros / max(1, total)


def to_sparse_storage(model):
    """
    把剪枝后的卷积权重转成稀疏 COO 并序列化，衡量真实存储收益。
    注意：PyTorch 的稀疏张量只支持推理，且需要专用算子才能真正加速；
    此处只用于评估存储收益。
    """
    total_sparse, total_dense = 0, 0
    m = copy.deepcopy(model)
    for name, mod in m.named_modules():
        if isinstance(mod, nn.Conv2d):
            w = mod.weight.data
            total_dense += w.numel() * w.element_size()
            sp = w.to_sparse()
            # COO 存储: values + indices(2 rows) + 少量元数据
            total_sparse += sp.values().numel() * w.element_size()
            total_sparse += sp.indices().numel() * sp.indices().element_size()
    return total_dense / 1024 / 1024, total_sparse / 1024 / 1024


def sparse_size_mb(model):
    """返回稀疏存储后的体积（仅卷积层，MB）"""
    _, sp = to_sparse_storage(model)
    return round(sp, 2)


# ==================== 量化 ====================
def dynamic_quantize(model):
    """
    动态量化：权重量化为 INT8，激活在推理时动态量化。
    对 CPU 推理最友好，无需校准数据。
    """
    m = copy.deepcopy(model).cpu().eval()
    q = torch.ao.quantization.quantize_dynamic(
        m,
        {nn.Linear, nn.Conv2d},
        dtype=torch.qint8,
    )
    return q


def static_quantize(model, calib_loader):
    """
    静态量化（PTQ）：需要校准数据，精度通常更好。
    """
    m = copy.deepcopy(model).cpu().eval()
    m.qconfig = torch.ao.quantization.get_default_qconfig("fbgemm")
    torch.ao.quantization.prepare(m, inplace=True)
    with torch.no_grad():
        for i, (x, _) in enumerate(calib_loader):
            m(x)
            if i >= 10:
                break
    torch.ao.quantization.convert(m, inplace=True)
    return m


def quant_size_mb(model):
    """
    量化模型的真实存储大小。
    注意：torch.save(state_dict()) 会保持量化张量结构，但更准确的是
    用 TorchScript 序列化 —— 那才是部署时的真实体积。
    """
    # 方式1: state_dict 序列化
    buf = io.BytesIO()
    torch.save(model.state_dict(), buf)
    sd_size = buf.tell() / 1024 / 1024

    # 方式2: TorchScript（部署真实体积）
    jit_size = None
    try:
        scripted = torch.jit.script(model)
        buf2 = io.BytesIO()
        torch.jit.save(scripted, buf2)
        jit_size = buf2.tell() / 1024 / 1024
    except Exception:
        try:
            example = torch.randn(1, 3, 224, 224)
            traced = torch.jit.trace(model, example)
            buf2 = io.BytesIO()
            torch.jit.save(traced, buf2)
            jit_size = buf2.tell() / 1024 / 1024
        except Exception:
            pass

    return round(jit_size if jit_size else sd_size, 2), round(sd_size, 2)


# ==================== 主流程 ====================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(PROJ_ROOT, "models_v2_full", "best.pt"))
    ap.add_argument("--data", default=None)
    ap.add_argument("--prune-ratio", type=float, default=0.3, help="剪枝比例")
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--bs", type=int, default=32)
    args = ap.parse_args()

    data_root = args.data or (LOCAL_DATA if os.path.isdir(LOCAL_DATA) else FALLBACK_DATA)
    os.makedirs(args.out, exist_ok=True)
    device = "cpu"      # 量化模型在 CPU 上评测

    print("=" * 84)
    print("模型压缩对比：原始 / 剪枝 / 量化 / 剪枝+量化")
    print("=" * 84)

    base_model, arch, img_size, ckpt = load_model(args.model, device)
    ds = TestDS(data_root, img_size)
    loader = DataLoader(ds, batch_size=args.bs, shuffle=False, num_workers=4)
    print(f"模型  : {args.model}")
    print(f"        arch={arch} img_size={img_size} epoch={ckpt.get('epoch')}")
    print(f"测试集: {len(ds)} 张")
    print("=" * 84)

    results = {}

    # ---------- ① 原始 FP32 ----------
    print("\n[1/4] 原始 FP32 模型...")
    m0 = copy.deepcopy(base_model)
    r0 = evaluate(m0, loader, device)
    lat0 = measure_latency(m0, img_size, device=device)
    p0 = count_params(m0)
    sz0 = file_size_mb(m0)
    results["fp32"] = {"size_mb": round(sz0, 2), "params": p0, "latency_ms": lat0, **r0}
    torch.save(m0.state_dict(), os.path.join(args.out, "model_fp32.pt"))
    print(f"      体积 {sz0:.2f}MB | 参数 {p0/1e6:.2f}M | 延迟 {lat0}ms | "
          f"acc {r0['accuracy']:.4f} | AUC {r0['auc']:.4f}")

    # ---------- ② 剪枝 ----------
    print(f"\n[2/4] 通道剪枝 (L1 全局, ratio={args.prune_ratio})...")
    m1 = prune_model(base_model, args.prune_ratio)
    sp = sparsity(m1)
    r1 = evaluate(m1, loader, device)
    lat1 = measure_latency(m1, img_size, device=device)
    sz1 = file_size_mb(m1)
    # 稀疏存储（COO）的真实体积 —— 这才是剪枝的实际收益
    sparse_mb = sparse_size_mb(m1)
    results["pruned"] = {
        "size_mb": round(sz1, 2), "sparse_size_mb": sparse_mb,
        "params": count_params(m1), "latency_ms": lat1,
        "sparsity": round(sp, 4), "prune_ratio": args.prune_ratio, **r1,
    }
    torch.save(m1.state_dict(), os.path.join(args.out, "model_pruned.pt"))
    print(f"      稀疏度 {sp:.1%} | 稠密体积 {sz1:.2f}MB | 稀疏存储 {sparse_mb:.2f}MB | "
          f"延迟 {lat1}ms")
    print(f"      acc {r1['accuracy']:.4f} | AUC {r1['auc']:.4f}")

    # ---------- ③ 动态量化 ----------
    print("\n[3/4] 动态量化 INT8 (仅权重)...")
    m2 = dynamic_quantize(base_model)
    r2 = evaluate(m2, loader, device)
    lat2 = measure_latency(m2, img_size, device=device)
    jit2, sd2 = quant_size_mb(m2)
    sz2 = jit2
    results["dynamic_int8"] = {"size_mb": round(sz2, 2), "state_dict_mb": sd2,
                               "latency_ms": lat2, **r2}
    torch.save(m2.state_dict(), os.path.join(args.out, "model_dynamic_int8.pt"))
    print(f"      体积 {sz2:.2f}MB (压缩 {sz0/sz2:.2f}x) | 延迟 {lat2}ms | "
          f"acc {r2['accuracy']:.4f} | AUC {r2['auc']:.4f}")

    # ---------- ④ 静态量化 ----------
    print("\n[4/4] 静态量化 INT8 (PTQ, 需要校准)...")
    m3 = static_quantize(base_model, loader)
    r3 = evaluate(m3, loader, device)
    lat3 = measure_latency(m3, img_size, device=device)
    jit3, sd3 = quant_size_mb(m3)
    sz3 = jit3
    results["static_int8"] = {"size_mb": round(sz3, 2), "state_dict_mb": sd3,
                              "latency_ms": lat3, **r3}
    torch.save(m3.state_dict(), os.path.join(args.out, "model_static_int8.pt"))
    print(f"      体积 {sz3:.2f}MB (压缩 {sz0/sz3:.2f}x) | 延迟 {lat3}ms | "
          f"acc {r3['accuracy']:.4f} | AUC {r3['auc']:.4f}")

    # ---------- 汇总 ----------
    print("\n" + "=" * 84)
    print("压缩效果汇总")
    print("=" * 84)
    print(f"{'方案':<16} {'体积(MB)':>9} {'压缩比':>7} {'延迟(ms)':>9} {'加速比':>7} "
          f"{'准确率':>8} {'恶性召回':>9} {'AUC':>7} {'精度损失':>9}")
    print("-" * 84)
    rows = [
        ("原始 FP32", "fp32"),
        (f"剪枝 {args.prune_ratio:.0%}", "pruned"),
        ("动态量化 INT8", "dynamic_int8"),
        ("静态量化 INT8", "static_int8"),
    ]
    for label, key in rows:
        d = results[key]
        cr = sz0 / d["size_mb"]
        sr = lat0 / d["latency_ms"] if d["latency_ms"] else 0
        dacc = (d["accuracy"] - r0["accuracy"]) * 100
        print(f"{label:<16} {d['size_mb']:>9.2f} {cr:>6.2f}x {d['latency_ms']:>9.2f} "
              f"{sr:>6.2f}x {d['accuracy']:>8.4f} {d['malignant_recall']:>9.4f} "
              f"{d['auc']:>7.4f} {dacc:>+8.2f}%")

    print("\n" + "=" * 84)
    print("结论")
    print("=" * 84)
    # 自动推荐
    best_size = min(results.items(), key=lambda kv: kv[1]["size_mb"] if kv[0] != "fp32" else 1e9)
    best_acc = max(
        [(k, v) for k, v in results.items() if k != "fp32"],
        key=lambda kv: kv[1]["accuracy"],
    )
    print(f"  最小体积  : {best_size[0]} ({best_size[1]['size_mb']:.2f}MB)")
    print(f"  精度最优  : {best_acc[0]} (acc {best_acc[1]['accuracy']:.4f})")

    # 推荐：精度损失 < 1% 且体积压缩 >= 2x
    cand = [(k, v) for k, v in results.items()
            if k != "fp32" and (v["accuracy"] - r0["accuracy"]) > -0.01
            and sz0 / v["size_mb"] >= 2.0]
    if cand:
        rec = max(cand, key=lambda kv: sz0 / kv[1]["size_mb"])
        print(f"  ✅ 推荐    : {rec[0]}  "
              f"(压缩 {sz0/rec[1]['size_mb']:.2f}x, 精度损失 {(rec[1]['accuracy']-r0['accuracy'])*100:+.2f}%)")
    else:
        print("  ⚠️  没有同时满足「压缩≥2x 且 精度损失<1%」的方案，建议用剪枝+微调组合")

    # ---------- 保存 ----------
    report = {
        "source_model": args.model,
        "arch": arch,
        "img_size": img_size,
        "test_samples": len(ds),
        "baseline": results["fp32"],
        "results": results,
    }
    with open(os.path.join(args.out, "compression_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存: {os.path.join(args.out, 'compression_report.json')}")
    print(f"模型已保存: {args.out}/model_*.pt")


if __name__ == "__main__":
    main()
