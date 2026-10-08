#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ONNX 模型量化 —— 真正的 INT8 压缩与加速
================================================================
任务书 3.3 要求"模型量化、剪枝，降低模型大小和计算量，提高推理速度"。

PyTorch 原生量化在本机受限（缺 fbgemm 量化卷积算子），
本脚本走工业界标准路径：PyTorch → ONNX → onnxruntime INT8 静态量化

流程:
  1. 导出 FP32 ONNX
  2. 用校准数据集做静态量化 (QDQ 格式，INT8)
  3. 分别评测 FP32 ONNX / INT8 ONNX 的：
     - 文件体积
     - CPU 推理延迟
     - 准确率 / 恶性召回 / AUC

用法:
  python3 onnx_quantize.py
  python3 onnx_quantize.py --model models_v2_full/best.pt --calib 100
"""

import argparse
import json
import os
import time

import numpy as np
import onnxruntime as ort
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import resnet50, resnet101
from onnxruntime.quantization import (
    quantize_static, quantize_dynamic,
    CalibrationDataReader, QuantType, QuantFormat,
)

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]
# 类别从 checkpoint 自动读取（支持二分类 / 7分类共用本脚本）
CLASSES = ["benign", "malignant"]      # 兜底默认值

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_DATA = os.path.expanduser("~/skin_cancer_data/processed_v2_full")
FALLBACK_DATA = os.path.join(PROJ_ROOT, "dataset", "processed_v2_full")
OUT_DIR = os.path.join(PROJ_ROOT, "models_compressed")


# ==================== 数据 ====================
def build_tf(img_size):
    return transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])


class ImgDS(Dataset):
    def __init__(self, root, split, img_size, classes=None):
        self.tf = build_tf(img_size)
        self.classes = list(classes or CLASSES)
        self.samples = []
        for label, cls in enumerate(self.classes):
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
        return self.tf(Image.open(p).convert("RGB")), y


# ==================== 模型 ====================
def build_model(arch, num_classes=2):
    if arch == "resnet50":
        m = resnet50(weights=None); feat = m.fc.in_features
    elif arch == "resnet101":
        m = resnet101(weights=None); feat = m.fc.in_features
    else:
        raise ValueError(arch)
    m.fc = nn.Sequential(nn.Dropout(0.4), nn.Linear(feat, num_classes))
    return m


def load_torch_model(path):
    """加载 checkpoint，返回 (model, arch, img_size, classes)"""
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    arch = ckpt.get("arch", "resnet50")
    img_size = int(ckpt.get("img_size", 224))
    classes = list(ckpt.get("classes", ["benign", "malignant"]))
    m = build_model(arch, len(classes))
    m.load_state_dict(ckpt.get("model") or ckpt)
    m.eval()
    return m, arch, img_size, classes


# ==================== ONNX 导出 ====================
def export_onnx(model, img_size, out_path):
    dummy = torch.randn(1, 3, img_size, img_size)
    torch.onnx.export(
        model, dummy, out_path,
        input_names=["input"], output_names=["logits"],
        dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
        dynamo=False,          # 用传统导出器，量化兼容性更好
    )
    return os.path.getsize(out_path) / 1024 / 1024


# ==================== 校准数据读取器 ====================
class SkinCalibReader(CalibrationDataReader):
    def __init__(self, root, img_size, n=100, split="train", classes=None):
        ds = ImgDS(root, split, img_size, classes)
        self.n = min(n, len(ds))
        self.batches = []
        for i in range(self.n):
            x, _ = ds[i]
            self.batches.append({"input": x.unsqueeze(0).numpy().astype(np.float32)})
        self._iter = iter(self.batches)
        print(f"[校准] 准备了 {self.n} 张校准图（来源: {split}）")

    def get_next(self):
        return next(self._iter, None)

    def rewind(self):
        self._iter = iter(self.batches)


# ==================== ONNX 推理与评测 ====================
def make_session(path, threads=4):
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])


def evaluate_onnx(sess, ds, bs=16, threads=4):
    """在 ONNX session 上评测整个测试集（支持二分类 / 多分类）"""
    loader = DataLoader(ds, batch_size=bs, shuffle=False, num_workers=0)
    ys, probs, preds = [], [], []
    for x, y in loader:
        logits = sess.run(["logits"], {"input": x.numpy().astype(np.float32)})[0]
        # softmax
        e = np.exp(logits - logits.max(axis=1, keepdims=True))
        p = e / e.sum(axis=1, keepdims=True)
        ys.extend(y.tolist())
        probs.append(p)                       # 保留完整概率矩阵
        preds.extend(p.argmax(1).tolist())

    y = np.array(ys)
    P = np.concatenate(probs, axis=0)         # (n, C)
    pr = np.array(preds)
    n_cls = P.shape[1]

    acc = float((pr == y).mean()) if len(y) else 0.0

    if n_cls == 2:
        p_pos = P[:, 1]
        tp = int(((pr == 1) & (y == 1)).sum()); fp = int(((pr == 1) & (y == 0)).sum())
        fn = int(((pr == 0) & (y == 1)).sum()); tn = int(((pr == 0) & (y == 0)).sum())
        rec = tp / max(1, tp + fn)
        prec = tp / max(1, tp + fp)
        f1 = 2 * prec * rec / max(1e-9, prec + rec)
        try:
            from sklearn.metrics import roc_auc_score
            auc = float(roc_auc_score(y, p_pos)) if len(set(y.tolist())) > 1 else 0.0
        except Exception:
            auc = 0.0
        return {
            "accuracy": round(acc, 4),
            "malignant_recall": round(float(rec), 4),
            "malignant_precision": round(float(prec), 4),
            "macro_f1": round(float(f1), 4),
            "auc": round(auc, 4),
            "confusion": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        }

    # ---- 多分类：宏平均指标 ----
    precs, recs, f1s = [], [], []
    for c in range(n_cls):
        tp = int(((pr == c) & (y == c)).sum())
        fp = int(((pr == c) & (y != c)).sum())
        fn = int(((pr != c) & (y == c)).sum())
        p_ = tp / max(1, tp + fp)
        r_ = tp / max(1, tp + fn)
        precs.append(p_); recs.append(r_)
        f1s.append(2 * p_ * r_ / max(1e-9, p_ + r_))
    try:
        from sklearn.metrics import roc_auc_score
        present = sorted(set(y.tolist()))
        auc = float(roc_auc_score(y, P, multi_class="ovr", average="macro",
                                  labels=present)) if len(present) > 1 else 0.0
    except Exception:
        auc = 0.0
    return {
        "accuracy": round(acc, 4),
        "macro_precision": round(float(np.mean(precs)), 4),
        "macro_recall": round(float(np.mean(recs)), 4),
        "macro_f1": round(float(np.mean(f1s)), 4),
        "auc": round(auc, 4),
        "num_classes": n_cls,
    }


def measure_latency_onnx(sess, img_size, n=50, warmup=10):
    x = np.random.randn(1, 3, img_size, img_size).astype(np.float32)
    for _ in range(warmup):
        sess.run(["logits"], {"input": x})
    t0 = time.time()
    for _ in range(n):
        sess.run(["logits"], {"input": x})
    return round((time.time() - t0) / n * 1000, 2)


# ==================== 主流程 ====================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(PROJ_ROOT, "models_v2_full", "best.pt"))
    ap.add_argument("--data", default=None)
    ap.add_argument("--calib", type=int, default=100, help="校准样本数")
    ap.add_argument("--out", default=OUT_DIR)
    args = ap.parse_args()

    data_root = args.data or (LOCAL_DATA if os.path.isdir(LOCAL_DATA) else FALLBACK_DATA)
    os.makedirs(args.out, exist_ok=True)

    print("=" * 84)
    print("ONNX 量化对比：PyTorch FP32 / ONNX FP32 / ONNX INT8")
    print("=" * 84)

    model, arch, img_size, classes = load_torch_model(args.model)
    print(f"模型  : {args.model}")
    print(f"        arch={arch} img_size={img_size} classes={classes}")
    print(f"数据  : {data_root}")
    print(f"输出  : {args.out}")

    test_ds = ImgDS(data_root, "test", img_size, classes)
    print(f"测试集: {len(test_ds)} 张（{len(classes)} 类）")
    print("=" * 84)

    results = {}

    # ---------- ① PyTorch FP32 基线 ----------
    torch_mb = os.path.getsize(args.model) / 1024 / 1024
    pt_path = os.path.join(args.out, "model_fp32.pt")
    torch.save(model.state_dict(), pt_path)
    torch_mb = os.path.getsize(pt_path) / 1024 / 1024
    results["pytorch_fp32"] = {"size_mb": round(torch_mb, 2), "format": "PyTorch"}
    print(f"\n[1/3] PyTorch FP32 基线: {torch_mb:.2f}MB")

    # ---------- ② 导出 ONNX FP32 ----------
    print("\n[2/3] 导出 ONNX FP32 ...")
    onnx_path = os.path.join(args.out, "model_fp32.onnx")
    sz_onnx = export_onnx(model, img_size, onnx_path)
    print(f"      导出完成: {sz_onnx:.2f}MB")

    sess_fp32 = make_session(onnx_path)
    r_fp32 = evaluate_onnx(sess_fp32, test_ds)
    lat_fp32 = measure_latency_onnx(sess_fp32, img_size)
    results["onnx_fp32"] = {
        "size_mb": round(sz_onnx, 2), "format": "ONNX FP32",
        "latency_ms": lat_fp32, **r_fp32,
    }
    print(f"      延迟 {lat_fp32}ms | acc {r_fp32['accuracy']:.4f} | AUC {r_fp32['auc']:.4f}")

    # ---------- ③ 静态量化 INT8 ----------
    print(f"\n[3/3] ONNX INT8 静态量化（校准 {args.calib} 张）...")
    int8_path = os.path.join(args.out, "model_int8.onnx")
    calib = SkinCalibReader(data_root, img_size, n=args.calib, split="train", classes=classes)
    try:
        quantize_static(
            model_input=onnx_path,
            model_output=int8_path,
            calibration_data_reader=calib,
            quant_format=QuantFormat.QDQ,
            activation_type=QuantType.QInt8,
            weight_type=QuantType.QInt8,
            per_channel=True,
            extra_options={"ActivationSymmetric": False, "WeightSymmetric": True},
        )
        sz_int8 = os.path.getsize(int8_path) / 1024 / 1024
        sess_int8 = make_session(int8_path)
        r_int8 = evaluate_onnx(sess_int8, test_ds)
        lat_int8 = measure_latency_onnx(sess_int8, img_size)
        results["onnx_int8"] = {
            "size_mb": round(sz_int8, 2), "format": "ONNX INT8 (QDQ)",
            "latency_ms": lat_int8, **r_int8,
        }
        print(f"      体积 {sz_int8:.2f}MB | 延迟 {lat_int8}ms | "
              f"acc {r_int8['accuracy']:.4f} | AUC {r_int8['auc']:.4f}")
    except Exception as e:
        print(f"      ❌ 静态量化失败: {type(e).__name__}: {e}")
        sz_int8, r_int8, lat_int8 = None, None, None

    # ---------- 动态量化（备选）----------
    if sz_int8 is None:
        print(f"\n[备选] ONNX INT8 动态量化...")
        try:
            dyn_path = os.path.join(args.out, "model_int8_dynamic.onnx")
            quantize_dynamic(onnx_path, dyn_path, weight_type=QuantType.QInt8)
            sz_dyn = os.path.getsize(dyn_path) / 1024 / 1024
            sess_dyn = make_session(dyn_path)
            r_dyn = evaluate_onnx(sess_dyn, test_ds)
            lat_dyn = measure_latency_onnx(sess_dyn, img_size)
            results["onnx_int8_dynamic"] = {
                "size_mb": round(sz_dyn, 2), "format": "ONNX INT8 (Dynamic)",
                "latency_ms": lat_dyn, **r_dyn,
            }
            print(f"      体积 {sz_dyn:.2f}MB | 延迟 {lat_dyn}ms | "
                  f"acc {r_dyn['accuracy']:.4f} | AUC {r_dyn['auc']:.4f}")
        except Exception as e:
            print(f"      ❌ 动态量化失败: {e}")

    # ---------- 汇总 ----------
    print("\n" + "=" * 84)
    print("汇总")
    print("=" * 84)
    print(f"{'方案':<24} {'体积(MB)':>9} {'压缩比':>7} {'延迟(ms)':>9} {'加速比':>7} "
          f"{'准确率':>8} {'恶性召回':>9} {'AUC':>7}")
    print("-" * 84)
    base_lat = None
    for key, label in [
        ("pytorch_fp32", "PyTorch FP32"),
        ("onnx_fp32", "ONNX FP32"),
        ("onnx_int8", "ONNX INT8 (QDQ)"),
        ("onnx_int8_dynamic", "ONNX INT8 (Dynamic)"),
    ]:
        if key not in results:
            continue
        d = results[key]
        lat = d.get("latency_ms")
        if base_lat is None and lat:
            base_lat = lat
        cr = f"{torch_mb/d['size_mb']:.2f}x" if d.get("size_mb") else "—"
        sr = f"{base_lat/lat:.2f}x" if (lat and base_lat) else "—"
        acc = f"{d['accuracy']:.4f}" if "accuracy" in d else "—"
        rec = f"{d['malignant_recall']:.4f}" if "malignant_recall" in d else "—"
        auc = f"{d['auc']:.4f}" if "auc" in d else "—"
        print(f"{label:<24} {d.get('size_mb', 0):>9.2f} {cr:>7} "
              f"{(f'{lat:.2f}' if lat else '—'):>9} {sr:>7} {acc:>8} {rec:>9} {auc:>7}")

    report = {
        "source_model": args.model, "arch": arch, "img_size": img_size,
        "test_samples": len(test_ds), "calib_samples": args.calib,
        "results": results,
    }
    with open(os.path.join(args.out, "onnx_quant_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存: {os.path.join(args.out, 'onnx_quant_report.json')}")
    print(f"ONNX 模型: {args.out}/model_fp32.onnx, model_int8.onnx")


if __name__ == "__main__":
    main()
