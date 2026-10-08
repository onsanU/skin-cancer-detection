#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Grad-CAM 可解释性服务
================================================================
职责:
  - 对集成中的每个成员模型，生成「模型关注区域」热力图
  - 输出与原图叠加的 PNG（医疗蓝色系），供前端并排展示

原理（Grad-CAM, Selvaraju et al. 2017）:
  ① 前向跑到目标卷积层，保留 feature map A^k (C×H×W)
  ② 对判定类别的 logit 反向求导，得到梯度 ∂y/∂A^k
  ③ 对梯度做全局平均池化 → 通道权重 α_k
  ④ L = ReLU(Σ_k α_k · A^k)  （ReLU 只保留正向贡献）
  ⑤ 归一化到 [0,1] → 上采样到原图尺寸 → 着色 → 与原图叠加

设计要点:
  - 复用 Predictor 里已加载的集成成员，绝不重复加载模型（省显存）
  - 推理时加锁，与主推理串行，避免并发显存峰值
  - 任何异常都降级为「无热力图」，绝不阻塞主判定结果返回
"""

import base64
import io
import os
import threading
import time
import uuid
from typing import Dict, List, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image

from .. import config

# ---------- 输出目录 ----------
CAM_DIR = os.path.join(config.UPLOAD_DIR, "cam")
os.makedirs(CAM_DIR, exist_ok=True)


# ============================================================
#  目标层选择：不同架构取「最后一个有空间分辨率的卷积模块」
# ============================================================
def _pick_target_layer(model: nn.Module, arch: str):
    """
    返回 (层名, 该层模块)。取不到时返回 (None, None)。

    · resnet*       → layer4（整个 stage 的输出，语义最强、分辨率 9×9@288）
    · convnext*     → features[-1]（最后一个 stage，含 3 个 block）
    · 其它          → 兜底：找最后一个 Conv2d 所在模块
    """
    if arch.startswith("resnet"):
        return "layer4", model.layer4

    if arch.startswith("convnext"):
        return "features", model.features[-1]

    if arch.startswith("efficientnet"):
        return "features", model.features[-1]

    if arch.startswith("swin"):
        return "features", model.features[-1]

    # 兜底：最后一个 Conv2d
    name, mod = None, None
    for n, m in model.named_modules():
        if isinstance(m, nn.Conv2d):
            name, mod = n.rsplit(".", 1)[0] or n, m
    if name and mod is not None:
        parent = model
        for part in name.split(".")[:-1]:
            parent = getattr(parent, part)
        return name, getattr(parent, name.split(".")[-1], mod)
    return None, None


# ============================================================
#  医疗蓝色系色带（deep blue → cyan → warm amber）
# ------------------------------------------------------------
#  低关注 = 浅蓝（贴近原图），高关注 = 琥珀/橙红（医学影像惯用警示色）
#  整体色调与项目「医疗蓝」主色协调，避免经典 jet 的刺眼彩虹感
# ============================================================
_STOPS = np.array([
    [0.00, 235, 245, 252],   # 极浅蓝（几乎透明，露出原图）
    [0.25, 165, 205, 240],   # 浅蓝
    [0.50,  70, 160, 220],   # 医疗蓝
    [0.72,  20, 105, 190],   # 深蓝
    [0.88, 250, 175,  60],   # 琥珀
    [1.00, 230,  85,  55],   # 橙红（最高关注）
], dtype=np.float32)


def _apply_colormap(gray: np.ndarray) -> np.ndarray:
    """
    gray: (H, W) float32 in [0,1] → RGB uint8 (H, W, 3)

    分段线性插值实现，避免依赖 matplotlib。
    """
    g = np.clip(gray, 0.0, 1.0)
    pos = _STOPS[:, 0]
    out = np.empty(g.shape + (3,), dtype=np.float32)
    for c in range(3):
        out[..., c] = np.interp(g, pos, _STOPS[:, c + 1])
    return out.astype(np.uint8)


def _overlay(img_rgb: np.ndarray, heat: np.ndarray,
             alpha: float = 0.45, gamma: float = 0.75) -> np.ndarray:
    """
    原图 + 热力图叠加。

    img_rgb : (H, W, 3) uint8
    heat    : (H, W)    float32 in [0,1]，已上采样+平滑
    gamma   : <1 时压低中间值，让高关注区更聚焦（视觉更干净）
    """
    heat_adj = np.power(np.clip(heat, 0, 1), gamma)
    color = _apply_colormap(heat_adj).astype(np.float32)
    base = img_rgb.astype(np.float32)

    # 逐像素 alpha 混合：heat 越低越透（几乎显示原图）
    a = (heat_adj * alpha)[..., None]
    out = base * (1.0 - a) + color * a
    return np.clip(out, 0, 255).astype(np.uint8)


def _smooth_cam(cam: np.ndarray, size, sigma_ratio: float = 0.06) -> np.ndarray:
    """
    CAM 上采样 + 高斯平滑。

    问题背景：ResNet101 的 layer4 输出仅 9×9，直接双线性放大到 480px 会留下
    明显的块状/矩形伪影（实测被误认为"模型关注边缘方块"）。
    解法：上采样后做一次高斯模糊，把块状边界糊开，视觉上更接近真实注意力分布。

    cam        : (h, w) float32 in [0,1]
    size       : (th, tw) 目标尺寸
    sigma_ratio: 高斯核大小相对目标短边的比例（0.06 → 480px 图上约 29px 核）
    """
    up = _upsample(cam, size)
    th, tw = size
    try:
        import cv2
        k = max(3, int(min(th, tw) * sigma_ratio) | 1)      # 强制奇数
        up = cv2.GaussianBlur(up, (k, k), 0)
    except Exception:
        # 无 cv2 时用 PIL 兜底
        from PIL import ImageFilter
        k = max(3, int(min(th, tw) * sigma_ratio) | 1)
        img = Image.fromarray((np.clip(up, 0, 1) * 255).astype(np.uint8))
        img = img.filter(ImageFilter.GaussianBlur(radius=k / 3.0))
        up = np.asarray(img).astype(np.float32) / 255.0

    # 重新归一化（模糊会削弱峰值）
    up = up - up.min()
    d = up.max()
    return (up / d).astype(np.float32) if d > 1e-8 else np.zeros_like(up)


# ============================================================
#  Grad-CAM 核心
# ============================================================
class GradCAM:
    """对单个模型做 Grad-CAM。每次 generate 前先 detach 上一轮缓存。"""

    def __init__(self, model: nn.Module, target_layer: nn.Module):
        self.model = model
        self.target_layer = target_layer
        self._feat: Optional[torch.Tensor] = None
        self._grad: Optional[torch.Tensor] = None
        self._h1 = target_layer.register_forward_hook(self._fwd_hook)
        self._h2 = target_layer.register_full_backward_hook(self._bwd_hook)

    # ---------- hooks ----------
    def _fwd_hook(self, module, inp, out):
        self._feat = out

    def _bwd_hook(self, module, grad_in, grad_out):
        self._grad = grad_out[0]

    def close(self):
        self._h1.remove()
        self._h2.remove()

    # ---------- 生成 ----------
    def generate(self, x: torch.Tensor, class_idx: Optional[int] = None):
        """
        x: (1, 3, H, W) 已归一化
        class_idx: 目标类别。None = 用模型自己预测的类别
                   （热力图含义变为「模型凭什么这么判」，更符合解释性直觉）

        返回 (cam: np.ndarray (h,w) float32 in [0,1], probs: list[float], used_idx: int)
        """
        self.model.zero_grad(set_to_none=True)
        self._feat = None
        self._grad = None

        # ① 前向（需要梯度，不能用 no_grad）
        logits = self.model(x)
        probs = torch.softmax(logits.float(), dim=1)[0].detach().cpu().numpy().tolist()

        # 未指定类别 → 用模型自己的预测类（argmax）
        used_idx = int(np.argmax(probs)) if class_idx is None else int(class_idx)

        # ② 反向目标类别的 logit
        self.model.zero_grad(set_to_none=True)
        logits[0, used_idx].backward()

        if self._feat is None or self._grad is None:
            raise RuntimeError("未捕获到特征/梯度，target_layer 可能选错")

        feat = self._feat.detach()          # (1, C, h, w)
        grad = self._grad.detach()          # (1, C, h, w)

        # ③ 通道权重 α_k = GAP(∂y/∂A^k)
        alpha = grad.mean(dim=(2, 3), keepdim=True)   # (1, C, 1, 1)

        # ④ 加权求和 + ReLU
        cam = F.relu((alpha * feat).sum(dim=1, keepdim=True))   # (1, 1, h, w)

        # ⑤ 归一化
        cam = cam[0, 0]
        cam = cam - cam.min()
        denom = cam.max()
        cam = (cam / denom) if denom > 1e-8 else torch.zeros_like(cam)

        return (cam.detach().cpu().numpy().astype(np.float32), probs, used_idx)


# ============================================================
#  对外服务
# ============================================================
class CamService:
    """Grad-CAM 生成服务（进程内单例，复用 Predictor 的模型）"""

    _generators: Dict[str, GradCAM] = {}
    _init_lock = threading.Lock()
    _ready = False
    _error = ""

    @classmethod
    def _ensure_generators(cls) -> bool:
        """按需为集成成员创建 Grad-CAM 生成器（只建一次）"""
        if cls._ready:
            return True
        with cls._init_lock:
            if cls._ready:
                return True
            try:
                from .predictor import Predictor
                p = Predictor.get()
                if not p.ready or not p.is_ensemble:
                    cls._error = "集成模型未就绪，无法生成热力图"
                    return False
                for m in p.ensemble:
                    name = m["name"]
                    if name in cls._generators:
                        continue
                    layer_name, layer = _pick_target_layer(m["model"], m.get("arch", ""))
                    if layer is None:
                        print(f"[GradCAM] {name} 未找到目标层，跳过", flush=True)
                        continue
                    cls._generators[name] = GradCAM(m["model"], layer)
                    print(f"[GradCAM] 已挂载 {name:24s} 目标层 {layer_name}", flush=True)
                cls._ready = len(cls._generators) > 0
                if not cls._ready:
                    cls._error = "没有任何模型可生成热力图"
                return cls._ready
            except Exception as e:
                cls._error = f"{type(e).__name__}: {e}"
                print(f"[GradCAM] 初始化失败: {cls._error}", flush=True)
                return False

    @classmethod
    def generate_all(cls, image_bytes: bytes, save: bool = True) -> Optional[Dict]:
        """
        为所有集成成员生成热力图。

        返回:
          {
            "images": [
              {"member": 模型名, "url": "/api/image/cam/xxx.png",
               "malignant_prob": 0.87, "focus": "malignant", "focus_cn": "恶性特征区"}
            ],
            "agreement": 0.82,        # 两图关注区域的余弦相似度（0~1）
            "note": "..."
          }
        失败返回 None（调用方应静默降级）。
        """
        if not cls._ensure_generators():
            return None

        try:
            from .predictor import Predictor
            p = Predictor.get()

            t0 = time.time()
            base_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            results = []

            # 与主推理串行，避免并发显存峰值
            with p.infer_lock:
                cams = []
                for m in p.ensemble:
                    name = m["name"]
                    gen = cls._generators.get(name)
                    if gen is None:
                        continue

                    x = m["transform"](base_img).unsqueeze(0).to(p.device)
                    cls._zero_grad_safe(m["model"])

                    with torch.enable_grad():
                        # class_idx=None → 用该成员自己预测的类别做梯度，
                        #  热力图语义 = 「模型凭什么这么判」
                        cam, probs, used_idx = gen.generate(x, class_idx=None)
                    cams.append(cam)

                    focus = "malignant" if used_idx == 1 else "benign"
                    results.append({
                        "member": name,
                        "arch": m.get("arch", ""),
                        "malignant_prob": round(float(probs[1]), 4),
                        "benign_prob": round(float(probs[0]), 4),
                        "focus": focus,
                        "focus_cn": config.CLASS_CN.get(focus, focus),
                        "cam": cam,
                    })

            if not results:
                return None

            # ---------- 渲染 ----------
            # 上采样基准：用原图尺寸，但限制最长边 480（省流量、够看清）
            W0, H0 = base_img.size
            scale = min(1.0, 480.0 / max(W0, H0))
            tw, th = max(64, int(W0 * scale)), max(64, int(H0 * scale))
            base_small = np.asarray(base_img.resize((tw, th), Image.BILINEAR))

            for r in results:
                heat = _smooth_cam(r["cam"], (th, tw))
                overlay = _overlay(base_small, heat)
                img = Image.fromarray(overlay)

                if save:
                    fname = f"cam_{uuid.uuid4().hex[:12]}.png"
                    fpath = os.path.join(CAM_DIR, fname)
                    img.save(fpath, format="PNG", optimize=True)
                    r["url"] = f"/api/image/cam/{fname}"
                r.pop("cam", None)

            # ---------- 一致性 ----------
            agreement = None
            if len(cams) >= 2:
                a = cams[0].ravel()
                b = cams[1].ravel()
                na, nb = np.linalg.norm(a), np.linalg.norm(b)
                if na > 1e-8 and nb > 1e-8:
                    agreement = round(float(np.dot(a, b) / (na * nb)), 4)

            elapsed = (time.time() - t0) * 1000
            return {
                "images": results,
                "agreement": agreement,
                "agreement_cn": _agreement_text(agreement),
                "method": "Grad-CAM",
                "target_layer": {n: (_pick_target_layer(p.ensemble[i]["model"],
                                                        p.ensemble[i].get("arch", ""))[0])
                                 for i, (n, _) in enumerate([(m["name"], None) for m in p.ensemble])},
                "elapsed_ms": round(elapsed, 1),
                # 原始 CAM（同尺寸 float32 [0,1]），供 explain 模块算集中度/一致性
                "_cams_raw": _resize_stack(cams, (th, tw)),
                "feature_vec": _collect_features(base_img, p),
                "legend": {
                    "low": "低关注",
                    "high": "高关注",
                    "note": "颜色越暖表示模型判定时越关注的区域，仅反映模型注意力，不等同病灶范围",
                },
                "disclaimer": getattr(config, "CAM_DISCLAIMER", ""),
            }
        except Exception as e:
            print(f"[GradCAM] 生成失败，降级跳过: {type(e).__name__}: {e}", flush=True)
            return None

    @classmethod
    def status(cls) -> Dict:
        return {
            "ready": cls._ready,
            "error": cls._error,
            "generators": list(cls._generators.keys()),
        }

    @staticmethod
    def _zero_grad_safe(model: nn.Module):
        try:
            model.zero_grad(set_to_none=True)
        except Exception:
            model.zero_grad()


def _upsample(cam: np.ndarray, size) -> np.ndarray:
    """把低分辨率 CAM 双线性上采样到 (h, w)"""
    t = torch.from_numpy(cam).float()[None, None]      # (1,1,h,w)
    t = F.interpolate(t, size=size, mode="bilinear", align_corners=False)
    return t[0, 0].numpy().astype(np.float32)


def _resize_stack(cams, size):
    """把多张 CAM 统一上采样到同一尺寸，返回 list[np.ndarray]"""
    return [_upsample(np.asarray(c), size) for c in cams]


def _collect_features(base_img: Image.Image, p) -> Optional[np.ndarray]:
    """
    提取当前图像在集成模型特征空间中的向量（供散点图定位）。

    与 src/gen_feature_surface.py 的提取口径严格一致：
      · 抓 avgpool 输出（分类头之前的池化特征）
      · 每个模型的特征先 L2 归一化，再按成员顺序拼接
    口径不一致会导致散点落到错误位置，务必同步修改两处。
    """
    try:
        import numpy as _np
        vecs = []
        with p.infer_lock:
            for m in p.ensemble:
                model = m["model"]
                if not hasattr(model, "avgpool"):
                    return None
                captured = {}

                def _hook(module, inp, out, _c=captured):
                    _c["f"] = out

                h = model.avgpool.register_forward_hook(_hook)
                try:
                    x = m["transform"](base_img).unsqueeze(0).to(p.device)
                    with torch.no_grad():
                        model(x)
                finally:
                    h.remove()
                f = captured.get("f")
                if f is None:
                    return None
                v = f.detach().cpu().numpy().reshape(-1).astype(_np.float32)
                vecs.append(v / (_np.linalg.norm(v) + 1e-8))
        if not vecs:
            return None
        return _np.concatenate(vecs) if len(vecs) > 1 else vecs[0]
    except Exception as e:
        print(f"[GradCAM] 特征提取失败（散点图跳过）: {type(e).__name__}: {e}", flush=True)
        return None


def _agreement_text(a: Optional[float]) -> str:
    """把余弦相似度翻译成人话"""
    if a is None:
        return "仅单模型，无一致性数据"
    if a >= 0.75:
        return "两个模型关注区域高度一致，结论可解释性较强"
    if a >= 0.50:
        return "两个模型关注区域基本一致，存在少量差异"
    if a >= 0.30:
        return "两个模型关注区域差异较明显，建议结合医生面诊"
    return "两个模型关注区域差异很大，该图判定稳定性偏低，请务必就医复核"


def cleanup_old_cams(keep: int = 200) -> int:
    """清理旧热力图文件，保留最近 keep 张（按 mtime）"""
    try:
        files = [os.path.join(CAM_DIR, f) for f in os.listdir(CAM_DIR) if f.endswith(".png")]
        if len(files) <= keep:
            return 0
        files.sort(key=os.path.getmtime)
        removed = 0
        for f in files[:-keep]:
            try:
                os.remove(f)
                removed += 1
            except Exception:
                pass
        return removed
    except Exception:
        return 0
