#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可解释性分析服务（Explainability）
================================================================
在 Grad-CAM 热力图之外，提供与参考产品（DUNEScan / SHAMSul）对齐的配套分析：

  ① 归属集中度（Attribution concentration）
     —— 各模型热力图中「≥ 峰值 50%」的像素占比
     高 = 模型注意力聚焦（好），低 = 注意力分散（判据不集中）

  ② 空间一致性矩阵（Spatial agreement）
     —— 模型两两之间热力图的空间相关系数

  ③ 特征空间投影（Feature surface）
     —— 新图像在 val 集 UMAP 特征空间中的落点（懒加载静态缓存）

  ④ 规则化文字解读（Narrative）
     —— 基于实际数值自动组织的"这是什么意思"，纯模板拼装，不用 LLM

设计原则:
  - 纯计算，不额外加载模型（复用 gradcam 已缓存的结果）
  - 所有解读文本都由真实数值驱动，绝不写死结论
"""

import json
import os
from typing import Dict, List, Optional

import numpy as np

from .. import config

# ---------- 特征空间缓存 ----------
_SURFACE_CACHE: Optional[Dict] = None
_SURFACE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "data", "feature_surface.json")


# ============================================================
#  ① 归属集中度
# ============================================================
def attribution_concentration(cams: List[np.ndarray],
                              threshold: float = 0.5) -> List[Dict]:
    """
    计算每张 CAM 中「≥ 峰值×threshold」的像素占比（%）。

    cams: 每张 CAM 已是 [0,1] 归一化、同尺寸的 float32 数组

    参考 SHAMSul 的 "Pixels ≥ 50% of peak attribution (%)" 口径。
    """
    out = []
    for cam in cams:
        c = np.asarray(cam, dtype=np.float32)
        peak = float(c.max())
        if peak <= 1e-8:
            pct = 0.0
        else:
            pct = float((c >= peak * threshold).sum()) / c.size * 100.0
        out.append({
            "pct": round(pct, 2),
            "peak": round(peak, 4),
            "threshold_used": threshold,
        })
    return out


def concentration_text(items: List[Dict]) -> str:
    """把集中度翻成人话"""
    if not items:
        return ""
    vals = [i["pct"] for i in items]
    avg = sum(vals) / len(vals)
    if avg >= 20:
        lvl = ("注意力高度聚焦", "模型把判断依据集中在很小的一片区域，判据明确")
    elif avg >= 10:
        lvl = ("注意力较为聚焦", "模型关注区域相对集中，判据比较明确")
    elif avg >= 4:
        lvl = ("注意力中等分散", "模型参考了多个区域，判据有一定分散")
    else:
        lvl = ("注意力高度分散", "模型关注区域很广、没有明显焦点，这类判断通常稳定性偏低，建议就医复核")

    detail = "；".join(f"{i+1} 号模型 {v:.1f}%" for i, v in enumerate(vals))
    return (f"各模型高关注区（≥峰值50%）的面积占比为 {detail}，"
            f"平均 {avg:.1f}%，属「{lvl[0]}」。{lvl[1]}。")


# ============================================================
#  ② 空间一致性矩阵
# ============================================================
def spatial_agreement(cams: List[np.ndarray]) -> Dict:
    """
    计算模型两两之间的热力图空间相关系数（Pearson）。

    返回:
      {"members": [...], "matrix": [[1.0, 0.58], [0.58, 1.0]]}
    """
    n = len(cams)
    if n == 0:
        return {"members": [], "matrix": []}

    flat = [np.asarray(c, dtype=np.float32).ravel() for c in cams]
    mat = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                mat[i][j] = 1.0
                continue
            a, b = flat[i], flat[j]
            # Pearson 相关系数
            a_c = a - a.mean()
            b_c = b - b.mean()
            denom = float(np.linalg.norm(a_c) * np.linalg.norm(b_c))
            mat[i][j] = round(float(np.dot(a_c, b_c) / denom), 4) if denom > 1e-8 else 0.0
    return {"members": [], "matrix": mat}


def agreement_text(val: Optional[float]) -> str:
    """一致性系数 → 人话（复用 gradcam 的口径）"""
    if val is None:
        return "仅单个模型可用，无法计算一致性。"
    if val >= 0.75:
        s = "两个模型关注区域高度一致，说明该图像的判别特征明显、结论可解释性较强"
    elif val >= 0.50:
        s = "两个模型关注区域基本一致，存在少量差异，属于正常范围"
    elif val >= 0.30:
        s = "两个模型关注区域差异较明显，说明可依据的特征不够突出，建议结合医生面诊"
    else:
        s = "两个模型关注区域差异很大，该图判定的稳定性偏低，请务必就医复核"
    return f"两模型热力图的空间相关系数为 {val:.2f}。{s}。"


# ============================================================
#  ③ 特征空间投影
# ============================================================
def load_surface() -> Optional[Dict]:
    """懒加载 UMAP 特征空间缓存（离线脚本生成）"""
    global _SURFACE_CACHE
    if _SURFACE_CACHE is not None:
        return _SURFACE_CACHE if _SURFACE_CACHE else None
    try:
        with open(_SURFACE_PATH, encoding="utf-8") as f:
            _SURFACE_CACHE = json.load(f)
        print(f"[Explain] 特征空间已加载: {_SURFACE_CACHE.get('n_samples')} 个点", flush=True)
    except Exception as e:
        print(f"[Explain] 特征空间未就绪（跳过散点图）: {type(e).__name__}: {e}", flush=True)
        _SURFACE_CACHE = {}
    return _SURFACE_CACHE if _SURFACE_CACHE else None


def project_image(feature_vec: np.ndarray) -> Optional[Dict]:
    """
    把新图像的特征投影到已缓存的特征空间中。

    做法（无需重新拟合 UMAP，保证与静态底图同一坐标系）：
      在原始高维特征空间里找最近的 K 个 val 样本，用它们的 2D 坐标
      做距离加权平均 → 得到新点的 2D 位置。这叫「out-of-sample 投影」的近似，
      对可视化定位足够，且计算量 O(N)，无需重训。

    返回: {"x":..., "y":..., "neighbors": [{"name","label","dist"}, ...],
           "malignant_neighbors": k, "benign_neighbors": k}
    """
    surf = load_surface()
    if not surf:
        return None
    pts = surf.get("points") or []
    if not pts:
        return None

    # 缓存里没有原始高维特征（JSON 太大），改用「预测概率」+「标签」做近邻代理？
    # → 不行，那样退化。所以：改为让离线脚本额外保存一份降维前的特征（float16 .npy）
    feats_path = os.path.splitext(_SURFACE_PATH)[0] + "_feats.npy"
    if not os.path.isfile(feats_path):
        return None
    try:
        X = np.load(feats_path)          # (N, D) float32
    except Exception:
        return None

    if feature_vec.shape[0] != X.shape[1]:
        return None

    # 余弦距离（与生成时 metric="cosine" 一致）
    q = feature_vec / (np.linalg.norm(feature_vec) + 1e-8)
    Xn = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-8)
    sims = Xn @ q
    order = np.argsort(-sims)

    K = 12
    idx = order[:K]
    sim_k = sims[idx]
    # 相似度转权重（负相似度截断为 0）
    w = np.clip(sim_k, 0, None) ** 3
    if w.sum() < 1e-8:
        w = np.ones_like(w)
    w = w / w.sum()

    xs = np.array([pts[i]["x"] for i in idx], dtype=np.float32)
    ys = np.array([pts[i]["y"] for i in idx], dtype=np.float32)
    x = float((xs * w).sum())
    y = float((ys * w).sum())

    n_mal = sum(1 for i in idx if pts[i]["label"] == "malignant")
    n_ben = sum(1 for i in idx if pts[i]["label"] == "benign")

    return {
        "x": round(x, 5),
        "y": round(y, 5),
        "neighbors": [
            {"name": pts[i]["name"], "label": pts[i]["label"],
             "sim": round(float(sims[i]), 4)}
            for i in idx[:5]
        ],
        "k": K,
        "malignant_neighbors": n_mal,
        "benign_neighbors": n_ben,
    }


def surface_text(proj: Optional[Dict]) -> str:
    """散点落点 → 人话"""
    if not proj:
        return ""
    n_mal = proj["malignant_neighbors"]
    n_ben = proj["benign_neighbors"]
    k = proj["k"]
    if n_mal >= k * 0.75:
        s = (f"它的 {k} 个最相似样本中有 {n_mal} 个为恶性，"
             f"特征与已知恶性病变高度接近，这是支持恶性判断的证据")
    elif n_mal >= k * 0.5:
        s = (f"它的 {k} 个最相似样本中有 {n_mal} 个为恶性、{n_ben} 个为良性，"
             f"特征处于两类交界处，属于需要谨慎对待的样本")
    elif n_mal > 0:
        s = (f"它的 {k} 个最相似样本中多为良性（{n_ben} 个），"
             f"仅 {n_mal} 个为恶性，特征更接近良性病变")
    else:
        s = (f"它的 {k} 个最相似样本全部为良性，"
             f"特征与已知良性病变一致")
    return ("特征空间散点图中的黑圈表示当前图像的位置（依据它与验证集样本在模型"
            f"特征空间中的相似度定位）。{s}。")


# ============================================================
#  ④ 汇总
# ============================================================
def build_analysis(gradcam_result: Dict,
                   prob_malignant: float,
                   feature_vec: Optional[np.ndarray] = None,
                   cams_raw: Optional[List[np.ndarray]] = None,
                   threshold: Optional[float] = None) -> Optional[Dict]:
    """
    组装完整的可解释性分析包。

    gradcam_result : gradcam.CamService.generate_all() 的返回
    prob_malignant : 集成模型的恶性概率
    feature_vec    : 当前图像的特征向量（用于散点定位，可为 None）
    cams_raw       : 原始 CAM 数组（用于计算集中度/一致性；None 则不计算）
    threshold      : 本次判定所用的阈值（前端画阈值刻度轴用）
    """
    if not gradcam_result:
        return None

    members = [im["member"] for im in gradcam_result.get("images", [])]
    analysis: Dict = {
        "method": "Grad-CAM",
        "members": members,
        "threshold": float(threshold) if threshold is not None else None,
    }

    # ---------- ① 集中度 ----------
    if cams_raw:
        conc = attribution_concentration(cams_raw)
        for i, item in enumerate(conc):
            if i < len(members):
                item["member"] = members[i]
        analysis["concentration"] = {
            "items": conc,
            "text": concentration_text(conc),
            "explain": (
                "计算方式：统计热力图中『亮度达到峰值 50% 以上』的像素占总像素的比例。"
                "比例高说明模型的注意力集中在一小片区域；比例低说明模型参考了很多分散区域，"
                "判据不够聚焦。这个指标只描述「注意力分布」，不评价对错。"
            ),
        }

    # ---------- ② 一致性矩阵 ----------
    if cams_raw and len(cams_raw) >= 2:
        ag = spatial_agreement(cams_raw)
        ag["members"] = members
        # ⚠️ 口径统一：矩阵用 Pearson，文字也必须用 Pearson，
        #   否则页面会出现「矩阵 0.47 / 文字 0.58」的自相矛盾（余弦 vs Pearson 差异）
        pearson = None
        if len(ag["matrix"]) >= 2:
            pearson = ag["matrix"][0][1]
            ag["value"] = pearson
        ag["text"] = agreement_text(pearson)
        ag["explain"] = (
            "计算方式：把两张热力图展平成向量，计算它们的皮尔逊相关系数（-1 ~ 1）。"
            "1 表示两个模型关注的完全是同一片区域，0 表示关注区域毫无关联。"
            "一致性高说明两个不同架构的模型「看到了同样的证据」，结论更可信；"
            "一致性低说明该图像的判别特征不明显，模型之间产生了分歧。"
        )
        if pearson is not None:
            analysis["agreement_value"] = pearson
        analysis["agreement"] = ag

    # ---------- ③ 特征空间投影 ----------
    if feature_vec is not None:
        proj = project_image(feature_vec)
        if proj:
            surf = load_surface() or {}
            proj["text"] = surface_text(proj)
            proj["meta"] = {
                "method": surf.get("method", "UMAP"),
                "n_samples": surf.get("n_samples"),
                "n_benign": surf.get("n_benign"),
                "n_malignant": surf.get("n_malignant"),
                "source": surf.get("source", ""),
                "feature_dim": surf.get("feature_dim"),
            }
            proj["explain"] = surf.get("note", "")
            analysis["feature_surface"] = proj

    # ---------- ④ 概率对比数据（柱状图用）----------
    imgs = gradcam_result.get("images", [])
    analysis["probabilities"] = {
        "ensemble_malignant": round(float(prob_malignant), 4),
        "items": [
            {"member": im["member"],
             "malignant_prob": im["malignant_prob"],
             "benign_prob": im["benign_prob"],
             "focus": im.get("focus", ""),
             "focus_cn": im.get("focus_cn", "")}
            for im in imgs
        ],
        "text": (
            f"集成模型给出的恶性概率为 {prob_malignant*100:.1f}%。"
            + "；".join(f"{im['member'][:20]} 单独判断为 "
                       f"{im['malignant_prob']*100:.1f}%"
                       for im in imgs)
            + "。两个模型概率越接近，说明它们的意见越统一。"
        ),
        "explain": (
            "每个成员模型都会独立给出一个恶性概率，系统最终取它们的平均作为集成结果。"
            "分别展示可以看清「集成结论是由哪些意见组成的」——如果某个模型明显偏离，"
            "说明该图像对这个模型来说比较难判断。"
        ),
    }

    return analysis
