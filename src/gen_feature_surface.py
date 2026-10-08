#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
特征空间投影数据生成（离线脚本）
================================================================
用途:
  为「特征空间散点图」（Classifier surface plot，参考 DUNEScan）预生成静态数据。

原理:
  ① 用集成模型对 val 集每张图提取「倒数第二层特征」（penultimate features）
     · ResNet101  → avgpool 输出（2048 维）
     · ConvNeXt-T → avgpool 输出（768 维）
  ② 拼接两个模型的特征（或取第一模型，见 --feature-mode）
  ③ UMAP 降到 2D，保存为静态 JSON，供前端散点图渲染

为什么离线:
  326 张图提特征 + UMAP 需要 2-5 分钟，绝不能放在请求路径里。
  生成一次即可，数据不变（val 集固定）。

用法:
  python src/gen_feature_surface.py                # 默认：两模型特征拼接
  python src/gen_feature_surface.py --feature-mode r101    # 只用 R101
  python src/gen_feature_surface.py --sample 1.0   # 用全部样本（默认）
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
from PIL import Image

# 让脚本能 import backend/app
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PROJ, "backend"))

from app.services.predictor import Predictor           # noqa: E402
from app import config                                  # noqa: E402

VAL_DIR = os.path.join(PROJ, "dataset", "processed_v2_full", "val")
OUT_JSON = os.path.join(PROJ, "backend", "app", "data", "feature_surface.json")


# ============================================================
#  特征提取器：抓「分类头之前」的池化输出
# ============================================================
class FeatureExtractor:
    """对单个模型挂 avgpool 钩子，取池化后特征向量"""

    def __init__(self, model: nn.Module, arch: str):
        self.model = model
        self.arch = arch
        self._feat = None
        self._hook = None
        self._attach()

    def _attach(self):
        # ResNet: avgpool（AdaptiveAvgPool2d）→ (1, C, 1, 1)
        # ConvNeXt: avgpool 同理
        if hasattr(self.model, "avgpool"):
            target = self.model.avgpool
        else:
            raise ValueError(f"{self.arch}: 找不到 avgpool 层")
        self._hook = target.register_forward_hook(self._h)

    def _h(self, module, inp, out):
        self._feat = out

    def extract(self, x: torch.Tensor) -> np.ndarray:
        self._feat = None
        with torch.no_grad():
            _ = self.model(x)
        f = self._feat
        if f is None:
            raise RuntimeError("未捕获到特征")
        return f.detach().cpu().numpy().reshape(-1)

    def close(self):
        if self._hook:
            self._hook.remove()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feature-mode", default="concat",
                    choices=["concat", "r101", "convnext"],
                    help="用哪些模型的特征（concat=两模型拼接，默认）")
    ap.add_argument("--n-neighbors", type=int, default=15, help="UMAP 局部邻域大小")
    ap.add_argument("--min-dist", type=float, default=0.1, help="UMAP 最小距离")
    ap.add_argument("--sample", type=float, default=1.0, help="采样比例（调试用）")
    ap.add_argument("--out", default=OUT_JSON)
    args = ap.parse_args()

    t_all = time.time()

    # ---------- 收集样本 ----------
    items = []
    for label, yi in [("benign", 0), ("malignant", 1)]:
        d = os.path.join(VAL_DIR, label)
        if not os.path.isdir(d):
            print(f"[警告] 目录不存在: {d}")
            continue
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith((".jpg", ".jpeg", ".png")):
                items.append({"path": os.path.join(d, fn), "name": fn,
                              "label": label, "y": yi})
    if args.sample < 1.0:
        import random
        random.seed(42)
        random.shuffle(items)
        items = items[: int(len(items) * args.sample)]

    print(f"[1/4] 样本数: {len(items)}  "
          f"(benign {sum(1 for i in items if i['y']==0)} / "
          f"malignant {sum(1 for i in items if i['y']==1)})")

    # ---------- 加载模型 ----------
    print("[2/4] 加载集成模型…")
    p = Predictor.get()
    if not p.ready:
        print(f"❌ 模型未就绪: {p.load_error}")
        return 1
    print(f"      集成成员: {[m['name'] for m in p.ensemble]}")

    # 按需选成员
    wanted = {"concat": None, "r101": "r101", "convnext": "convnext"}[args.feature_mode]
    members = p.ensemble
    if wanted == "r101":
        members = [m for m in p.ensemble if "r101" in m["name"].lower()]
    elif wanted == "convnext":
        members = [m for m in p.ensemble if "convnext" in m["name"].lower() or "mix" in m["name"].lower()]
    if not members:
        print("❌ 没有匹配的模型成员")
        return 1

    extractors = []
    for m in members:
        extractors.append((m, FeatureExtractor(m["model"], m.get("arch", ""))))
        print(f"      ✔ 特征提取器挂载: {m['name']} ({m.get('arch')})")

    # ---------- 提特征 ----------
    print("[3/4] 提取特征…")
    feats, preds = [], []
    t0 = time.time()
    for i, it in enumerate(items):
        img = Image.open(it["path"]).convert("RGB")
        vecs, prob_avg = [], None
        for m, ex in extractors:
            x = m["transform"](img).unsqueeze(0).to(p.device)
            vecs.append(ex.extract(x))
            with torch.no_grad():
                pr = torch.softmax(m["model"](x).float(), dim=1)[0].cpu().numpy()
            prob_avg = pr if prob_avg is None else prob_avg + pr
        prob_avg = prob_avg / len(extractors)

        # L2 归一化每个模型的向量后再拼接，避免维度大的模型主导
        normed = [v / (np.linalg.norm(v) + 1e-8) for v in vecs]
        feats.append(np.concatenate(normed) if len(normed) > 1 else normed[0])
        preds.append(float(prob_avg[1]))       # 恶性概率（集成平均）

        if (i + 1) % 50 == 0:
            el = time.time() - t0
            print(f"      {i+1}/{len(items)}  {el:.0f}s  "
                  f"({el/(i+1)*1000:.0f} ms/张)")

    X = np.stack(feats).astype(np.float32)
    preds = np.array(preds, dtype=np.float32)
    print(f"      特征矩阵: {X.shape}  耗时 {time.time()-t0:.0f}s")

    for _, ex in extractors:
        ex.close()

    # ---------- UMAP 降维 ----------
    print("[4/4] UMAP 降维…")
    import umap
    t0 = time.time()
    reducer = umap.UMAP(n_neighbors=args.n_neighbors,
                        min_dist=args.min_dist,
                        metric="cosine",
                        random_state=42)
    Y = reducer.fit_transform(X)
    print(f"      完成: {Y.shape}  耗时 {time.time()-t0:.0f}s")

    # 归一化到 [-1, 1]，便于前端统一坐标
    Y = Y - Y.mean(axis=0)
    scale = np.abs(Y).max(axis=0)
    Y = Y / (scale + 1e-8)

    # ---------- 保存 ----------
    points = []
    for i, it in enumerate(items):
        points.append({
            "x": round(float(Y[i, 0]), 5),
            "y": round(float(Y[i, 1]), 5),
            "label": it["label"],                    # 真实标签
            "name": it["name"],
            "prob": round(float(preds[i]), 4),       # 模型预测恶性概率
        })

    payload = {
        "method": "UMAP",
        "feature_mode": args.feature_mode,
        "members": [m["name"] for m, _ in [(m, None) for m in members]],
        "feature_dim": int(X.shape[1]),
        "n_samples": len(points),
        "n_benign": sum(1 for p_ in points if p_["label"] == "benign"),
        "n_malignant": sum(1 for p_ in points if p_["label"] == "malignant"),
        "umap_params": {"n_neighbors": args.n_neighbors,
                        "min_dist": args.min_dist, "metric": "cosine"},
        "source": "HAM10000 val 集（病灶级划分，与训练集无泄漏）",
        "points": points,
        "note": ("每个点是一张验证集图像在两个模型特征空间中的位置（UMAP 投影）。"
                 "红/蓝表示真实标签，点的位置反映特征的相似性——"
                 "被判定为恶性的新图像若落在恶性簇中，说明其特征与已知恶性病变相似。"),
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    # ---------- 同时保存原始高维特征（供新图像做 out-of-sample 定位）----------
    #   用 float16 存：2816 维 × 326 张 ≈ 1.8MB（float32 要 3.7MB），精度足够做近邻
    feats_path = os.path.splitext(args.out)[0] + "_feats.npy"
    np.save(feats_path, X.astype(np.float16))

    size_kb = os.path.getsize(args.out) / 1024
    fsize_mb = os.path.getsize(feats_path) / 1024 / 1024
    print(f"\n✅ 已保存: {args.out}  ({size_kb:.0f} KB, {len(points)} 个点)")
    print(f"   特征矩阵: {feats_path}  ({fsize_mb:.2f} MB, {X.shape})")
    print(f"   总耗时: {time.time()-t_all:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
