#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型推理服务 —— 核心模块
================================================================
职责:
  - 启动时自动探测并加载可用的 best.pt（按 config.MODEL_CANDIDATES 优先级）
  - 从 checkpoint 读取 arch / img_size / classes，自动构建对应结构
  - 提供单张图像预测接口（图像 → 良性/恶性 + 置信度 + 概率）

设计要点:
  - 延迟加载 + 单例：避免每个请求重复加载模型
  - 线程安全：推理时加锁，防止并发 OOM
  - 优雅降级：模型加载失败不阻塞服务启动（健康检查会报告状态）
"""

import io
import os
import threading
import time
from typing import Dict, Optional

import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms
from torchvision.models import (
    resnet50, resnet101,
    ResNet50_Weights, ResNet101_Weights,
)

from .. import config

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


class Predictor:
    """模型推理单例"""

    _instance: Optional["Predictor"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.model: Optional[nn.Module] = None
        self.onnx = None
        self.backend: str = ""
        self.arch: str = ""
        self.img_size: int = 224
        self.classes = list(config.CLASSES)
        self.device = torch.device(
            config.DEVICE if torch.cuda.is_available() else "cpu"
        )
        self.model_path: str = ""
        self.load_error: str = ""
        self.ready: bool = False
        self.infer_lock = threading.Lock()
        self._transform = None
        # 集成模式
        self.ensemble: list = []          # [(name, model, img_size, transform), ...]
        self.is_ensemble: bool = False
        # 统计
        self.load_time: float = 0.0
        self.infer_count: int = 0
        self.total_infer_ms: float = 0.0

    # ---------- 单例 ----------
    @classmethod
    def get(cls) -> "Predictor":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    cls._instance.load()
        return cls._instance

    # ---------- 加载 ----------
    def _find_model(self) -> Optional[str]:
        for sub, fname in config.MODEL_CANDIDATES:
            p = os.path.join(config.MODELS_DIR, sub, fname)
            if os.path.isfile(p):
                return p
        return None

    def _build_model(self, arch: str) -> nn.Module:
        """
        根据 checkpoint 里的 arch 重建结构（与训练脚本 train_sota.py 一致）

        支持架构: resnet50 / resnet101 / convnext_tiny / convnext_small
                  / efficientnet_v2_s / swin_t
        """
        if arch == "resnet50":
            m = resnet50(weights=None)
            m.fc = nn.Sequential(nn.Dropout(0.4), nn.Linear(m.fc.in_features, len(self.classes)))
        elif arch == "resnet101":
            m = resnet101(weights=None)
            m.fc = nn.Sequential(nn.Dropout(0.4), nn.Linear(m.fc.in_features, len(self.classes)))
        elif arch.startswith("convnext"):
            from torchvision.models import convnext_tiny, convnext_small
            m = convnext_tiny(weights=None) if arch == "convnext_tiny" else convnext_small(weights=None)
            dim = m.classifier[2].in_features
            m.classifier[2] = nn.Sequential(nn.Dropout(0.4), nn.Linear(dim, len(self.classes)))
        elif arch.startswith("efficientnet"):
            from torchvision.models import efficientnet_v2_s
            m = efficientnet_v2_s(weights=None)
            dim = m.classifier[1].in_features
            m.classifier[1] = nn.Sequential(nn.Dropout(0.4), nn.Linear(dim, len(self.classes)))
        elif arch.startswith("swin"):
            from torchvision.models import swin_t
            m = swin_t(weights=None)
            m.head = nn.Sequential(nn.Dropout(0.4), nn.Linear(m.head.in_features, len(self.classes)))
        else:
            raise ValueError(f"未知架构: {arch}")
        return m

    def _load_ensemble(self) -> bool:
        """
        加载多个二分类模型用于集成推理（支持加权）。

        ENSEMBLE_MODELS 格式: (目录, 文件名[, 权重]) —— 权重省略时默认 1.0（等权）。
        要求所有模型的类别顺序一致（[benign, malignant]），否则跳过。
        """
        loaded = []
        for entry in getattr(config, "ENSEMBLE_MODELS", []):
            # 兼容 2 元组（旧格式）与 3 元组（带权重）
            if len(entry) == 2:
                sub, fname, weight = entry[0], entry[1], 1.0
            else:
                sub, fname, weight = entry[0], entry[1], float(entry[2])
            p = os.path.join(config.MODELS_DIR, sub, fname)
            if not os.path.isfile(p):
                print(f"[Predictor] 集成成员缺失，跳过: {sub}/{fname}", flush=True)
                continue
            try:
                ckpt = torch.load(p, map_location=self.device, weights_only=False)
                arch = ckpt.get("arch", "resnet50")
                isz = int(ckpt.get("img_size", 224))
                cls = ckpt.get("classes", list(config.CLASSES))
                if list(cls) != list(config.CLASSES):
                    print(f"[Predictor] 集成成员类别不匹配，跳过: {sub} ({cls})", flush=True)
                    continue

                # 用统一的 _build_model（支持多架构）
                _saved_cls = self.classes
                self.classes = list(cls)
                m = self._build_model(arch)
                self.classes = _saved_cls

                state = ckpt.get("model") or ckpt.get("state_dict") or ckpt
                m.load_state_dict(state)
                m.to(self.device).eval()

                tf = transforms.Compose([
                    transforms.Resize((isz, isz)),
                    transforms.ToTensor(),
                    transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
                ])
                loaded.append({"name": sub, "model": m, "img_size": isz,
                               "transform": tf, "arch": arch, "weight": weight})
                meta = ckpt.get("metrics") or {}
                print(f"[Predictor]    集成成员 {sub:22s} arch={arch:15s} "
                      f"w={weight:.1f} acc={meta.get('accuracy', 0):.4f}", flush=True)
            except Exception as e:
                print(f"[Predictor] 集成成员加载失败 {sub}: {e}", flush=True)

        if len(loaded) < 1:
            print("[Predictor] 无可用集成成员，回退单模型", flush=True)
            return False

        self.ensemble = loaded
        self.is_ensemble = True
        self.backend = "pytorch-ensemble"
        self.arch = f"ensemble({len(loaded)})"
        self.model_path = ",".join(m["name"] for m in loaded)
        self.img_size = max(m["img_size"] for m in loaded)
        return True

    def load(self) -> bool:
        t0 = time.time()

        # ---------- ① 集成模式（准确率最优）----------
        if getattr(config, "ENABLE_ENSEMBLE", False):
            if self._load_ensemble():
                self.load_time = time.time() - t0
                self.ready = True
                self.load_error = ""
                print(f"[Predictor] ✅ 集成模式已启用: {len(self.ensemble)} 个模型 "
                      f"耗时{self.load_time:.2f}s", flush=True)
                return True

        # ---------- ② 优先尝试 ONNX（体积小、内存占用低） ----------
        if config.USE_ONNX and os.path.isfile(config.ONNX_MODEL_PATH):
            try:
                from .onnx_backend import OnnxBackend
                self.onnx = OnnxBackend(config.ONNX_MODEL_PATH, self.img_size, self.classes)
                self.backend = "onnx-int8"
                self.arch = "resnet50(onnx-int8)"
                self.model_path = config.ONNX_MODEL_PATH
                self.load_time = time.time() - t0
                self.ready = True
                self.load_error = ""
                print(f"[Predictor] ✅ ONNX 后端已加载: {config.ONNX_MODEL_PATH}", flush=True)
                print(f"[Predictor]    体积 {self.onnx.size_mb:.2f}MB "
                      f"(较 PyTorch 压缩约 4x) 耗时{self.load_time:.2f}s", flush=True)
                return True
            except Exception as e:
                print(f"[Predictor] ONNX 加载失败，回退 PyTorch: {e}", flush=True)

        # ---------- 回退：PyTorch checkpoint ----------
        path = self._find_model()
        if not path:
            self.load_error = (
                f"未找到任何模型文件。候选路径: "
                + ", ".join(f"{s}/{f}" for s, f in config.MODEL_CANDIDATES)
            )
            print(f"[Predictor] ❌ {self.load_error}", flush=True)
            return False

        try:
            ckpt = torch.load(path, map_location=self.device, weights_only=False)
            self.arch = ckpt.get("arch", "resnet50")
            self.img_size = int(ckpt.get("img_size", 224))
            self.classes = ckpt.get("classes", list(config.CLASSES))

            model = self._build_model(self.arch)
            state = ckpt.get("model") or ckpt.get("state_dict") or ckpt
            model.load_state_dict(state)
            model.to(self.device).eval()

            self.model = model
            self.backend = "pytorch"
            self.model_path = path
            self._transform = transforms.Compose([
                transforms.Resize((self.img_size, self.img_size)),
                transforms.ToTensor(),
                transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
            ])
            self.load_time = time.time() - t0
            self.ready = True
            self.load_error = ""
            meta = ckpt.get("metrics") or {}
            print(f"[Predictor] ✅ 模型已加载: {path}", flush=True)
            print(f"[Predictor]    arch={self.arch} img_size={self.img_size} "
                  f"device={self.device} 耗时{self.load_time:.2f}s", flush=True)
            if meta:
                print(f"[Predictor]    训练时指标: acc={meta.get('accuracy', 0):.4f} "
                      f"auc={meta.get('auc', 0):.4f}", flush=True)
            return True
        except Exception as e:
            self.load_error = f"模型加载失败: {type(e).__name__}: {e}"
            print(f"[Predictor] ❌ {self.load_error}", flush=True)
            return False

    # ---------- 预处理 ----------
    def _preprocess(self, image_bytes: bytes) -> torch.Tensor:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return self._transform(img).unsqueeze(0)

    # ---------- 预测 ----------
    @torch.no_grad()
    def predict_bytes(self, image_bytes: bytes, threshold: Optional[float] = None) -> Dict:
        """
        输入: 图像字节
        输出: {label, label_cn, probability, confidence, probs, infer_ms}
        """
        if not self.ready:
            raise RuntimeError(self.load_error or "模型未就绪")

        # 集成模式有专属推荐阈值
        if threshold is None:
            if self.is_ensemble:
                thr = getattr(config, "ENSEMBLE_THRESHOLD", 0.51)
            else:
                thr = config.MALIGNANT_THRESHOLD
        else:
            thr = threshold
        t0 = time.time()

        # ---------- 集成分支（加权平均）----------
        if self.is_ensemble and self.ensemble:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            prob_sum = None
            w_sum = 0.0
            with self.infer_lock:
                for m in self.ensemble:
                    x = m["transform"](img).unsqueeze(0).to(self.device)
                    logits = m["model"](x)
                    p = torch.softmax(logits.float(), dim=1)[0].cpu().numpy()
                    w = float(m.get("weight", 1.0))
                    prob_sum = (p * w) if prob_sum is None else (prob_sum + p * w)
                    w_sum += w
            probs = (prob_sum / max(w_sum, 1e-9)).tolist()

            p_benign, p_malignant = float(probs[0]), float(probs[1])
            is_malignant = p_malignant >= thr
            label = "malignant" if is_malignant else "benign"
            infer_ms = (time.time() - t0) * 1000
            self.infer_count += 1
            self.total_infer_ms += infer_ms

            return {
                "label": label,
                "label_cn": config.CLASS_CN.get(label, label),
                "probability": round(p_malignant if is_malignant else p_benign, 4),
                "confidence": round(p_malignant if is_malignant else p_benign, 4),
                "malignant_prob": round(p_malignant, 4),
                "benign_prob": round(p_benign, 4),
                "threshold": thr,
                "infer_ms": round(infer_ms, 1),
                "mode": f"ensemble-{len(self.ensemble)}",
                "members": [m["name"] for m in self.ensemble],
            }

        # ---------- ONNX 分支 ----------
        if self.backend == "onnx-int8" and self.onnx is not None:
            r = self.onnx.predict(image_bytes, thr)
            infer_ms = (time.time() - t0) * 1000
            r["infer_ms"] = round(infer_ms, 1)
            self.infer_count += 1
            self.total_infer_ms += infer_ms
            return r

        # ---------- PyTorch 分支 ----------
        x = self._preprocess(image_bytes).to(self.device)
        with self.infer_lock:            # 串行化推理，防并发显存峰值
            logits = self.model(x)
            probs = torch.softmax(logits.float(), dim=1)[0].cpu().tolist()

        # classes 顺序: [benign, malignant]
        p_benign = float(probs[0])
        p_malignant = float(probs[1])
        is_malignant = p_malignant >= thr
        label = "malignant" if is_malignant else "benign"

        infer_ms = (time.time() - t0) * 1000
        self.infer_count += 1
        self.total_infer_ms += infer_ms

        return {
            "label": label,
            "label_cn": config.CLASS_CN.get(label, label),
            "probability": round(p_malignant if is_malignant else p_benign, 4),
            "confidence": round(p_malignant if is_malignant else p_benign, 4),
            "malignant_prob": round(p_malignant, 4),
            "benign_prob": round(p_benign, 4),
            "threshold": thr,
            "infer_ms": round(infer_ms, 1),
        }

    def warmup(self):
        """用一张随机图预热，避免首个请求慢"""
        if not self.ready:
            return
        try:
            import numpy as np
            dummy = (np.random.rand(self.img_size, self.img_size, 3) * 255).astype("uint8")
            buf = io.BytesIO()
            Image.fromarray(dummy).save(buf, format="PNG")
            # 集成模式下预热会跑 N 次，为节省启动时间只预热一次
            self.predict_bytes(buf.getvalue())
            self.infer_count = 0
            self.total_infer_ms = 0.0
            print("[Predictor] 预热完成", flush=True)
        except Exception as e:
            print(f"[Predictor] 预热跳过: {e}", flush=True)

    # ---------- 状态 ----------
    def status(self) -> Dict:
        st = {
            "ready": self.ready,
            "backend": self.backend,
            "model_path": self.model_path,
            "arch": self.arch,
            "img_size": self.img_size,
            "classes": self.classes,
            "device": ("cpu (onnxruntime)" if self.backend == "onnx-int8" else str(self.device)),
            "load_time_s": round(self.load_time, 3),
            "load_error": self.load_error,
            "infer_count": self.infer_count,
            "avg_infer_ms": round(self.total_infer_ms / self.infer_count, 1) if self.infer_count else None,
            "ensemble": self.is_ensemble,
            "ensemble_size": len(self.ensemble),
            "ensemble_members": [m["name"] for m in self.ensemble],
            "default_threshold": (getattr(config, "ENSEMBLE_THRESHOLD", 0.51)
                                  if self.is_ensemble else config.MALIGNANT_THRESHOLD),
        }
        return st
