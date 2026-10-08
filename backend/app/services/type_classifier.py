#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
7 类病变类型推理服务（辅助模型）
================================================================
定位：在二分类（良性/恶性）主结论之外，提供"可能是哪种病变"的参考信息。

设计:
  - 与 Predictor 解耦：独立单例、独立加载、失败不影响主服务
  - 与 Predictor 一致：懒加载 + 线程锁 + 优雅降级
  - 输出：Top-3 类型 + 概率 + 中文名 + 医学分组（良性/恶性）

重要说明（前端展示需注明）:
  7 类分类准确率（约 74%）明显低于二分类（约 85%），
  仅作为参考信息，不作为诊断依据。
"""

import io
import os
import threading
import time
from typing import Dict, List, Optional

import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms
from torchvision.models import resnet50, resnet101

from .. import config

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

# 7 类中文名与医学分组（HAM10000 标准）
TYPE_CN = {
    "akiec": "光化性角化/原位鳞癌",
    "bcc": "基底细胞癌",
    "bkl": "良性角化",
    "df": "皮肤纤维瘤",
    "mel": "黑色素瘤",
    "nv": "黑色素细胞痣",
    "vasc": "血管性病变",
}
TYPE_GROUP = {
    "akiec": "malignant", "bcc": "malignant", "mel": "malignant",
    "bkl": "benign", "df": "benign", "nv": "benign", "vasc": "benign",
}
TYPE_DESC = {
    "akiec": "日晒相关的癌前病变或早期鳞状细胞癌，需专业评估",
    "bcc": "最常见的皮肤恶性肿瘤，生长缓慢，早期治疗预后良好",
    "bkl": "包括脂溢性角化等良性增生，通常无需处理",
    "df": "良性的皮肤纤维组织增生，多为质硬小结节",
    "mel": "恶性程度最高的皮肤癌，早期发现治疗至关重要",
    "nv": "最常见的良性色素痣，绝大多数终身良性",
    "vasc": "血管来源的良性病变，如樱桃状血管瘤",
}


class TypeClassifier:
    """7 类病变类型分类器（单例）"""

    _instance: Optional["TypeClassifier"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.model: Optional[nn.Module] = None
        self.onnx = None                  # ONNX 后端（可选）
        self.backend: str = ""            # "pytorch" 或 "onnx-int8"
        self.classes: List[str] = []
        self.img_size: int = 224
        self.arch: str = ""
        self.model_path: str = ""
        self.device = torch.device(
            config.DEVICE if torch.cuda.is_available() else "cpu"
        )
        self.ready: bool = False
        self.load_error: str = ""
        self.infer_lock = threading.Lock()
        self._transform = None
        self.load_time: float = 0.0
        self.infer_count: int = 0
        self.enabled: bool = bool(getattr(config, "ENABLE_TYPE_PREDICT", True))

    # ---------- 单例 ----------
    @classmethod
    def get(cls) -> "TypeClassifier":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    cls._instance.load()
        return cls._instance

    # ---------- 加载 ----------
    def _find_model(self) -> Optional[str]:
        cands = getattr(config, "TYPE_MODEL_CANDIDATES", [])
        for sub, fname in cands:
            p = os.path.join(config.MODELS_DIR, sub, fname)
            if os.path.isfile(p):
                return p
        return None

    def load(self) -> bool:
        if not self.enabled:
            self.load_error = "类型推理已通过配置关闭 (ENABLE_TYPE_PREDICT=False)"
            print(f"[TypeClf] 已禁用: {self.load_error}", flush=True)
            return False

        t0 = time.time()

        # ---------- ① 优先尝试 ONNX（体积小、内存低）----------
        onnx_path = getattr(config, "TYPE_ONNX_PATH", "")
        if getattr(config, "TYPE_USE_ONNX", False) and onnx_path and os.path.isfile(onnx_path):
            try:
                from .onnx_backend import OnnxBackend
                self.onnx = OnnxBackend(onnx_path, self.img_size, list(TYPE_CN.keys()))
                self.classes = list(TYPE_CN.keys())
                self.backend = "onnx-int8"
                self.arch = "resnet50(onnx-int8)"
                self.model_path = onnx_path
                self.load_time = time.time() - t0
                self.ready = True
                self.load_error = ""
                print(f"[TypeClf] ✅ ONNX 后端已加载: {onnx_path}", flush=True)
                print(f"[TypeClf]    体积 {self.onnx.size_mb:.2f}MB 耗时{self.load_time:.2f}s",
                      flush=True)
                return True
            except Exception as e:
                print(f"[TypeClf] ONNX 加载失败，回退 PyTorch: {e}", flush=True)

        # ---------- ② PyTorch checkpoint ----------
        path = self._find_model()
        if not path:
            self.load_error = "未找到 7 类模型（TYPE_MODEL_CANDIDATES 均不存在）"
            print(f"[TypeClf] ⚠️ {self.load_error}", flush=True)
            return False

        try:
            ckpt = torch.load(path, map_location=self.device, weights_only=False)
            self.arch = ckpt.get("arch", "resnet50")
            self.img_size = int(ckpt.get("img_size", 224))
            self.classes = ckpt.get("classes", list(TYPE_CN.keys()))

            if self.arch == "resnet101":
                m = resnet101(weights=None)
            else:
                m = resnet50(weights=None)
            feat = m.fc.in_features
            m.fc = nn.Sequential(nn.Dropout(0.4), nn.Linear(feat, len(self.classes)))
            state = ckpt.get("model") or ckpt.get("state_dict") or ckpt
            m.load_state_dict(state)
            m.to(self.device).eval()

            self.model = m
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
            print(f"[TypeClf] ✅ 7类模型已加载: {path}", flush=True)
            print(f"[TypeClf]    classes={self.classes} img_size={self.img_size} "
                  f"耗时{self.load_time:.2f}s", flush=True)
            if meta:
                print(f"[TypeClf]    训练指标: acc={meta.get('accuracy', 0):.4f} "
                      f"macro_f1={meta.get('macro_f1', 0):.4f}", flush=True)
            return True
        except Exception as e:
            self.load_error = f"7类模型加载失败: {type(e).__name__}: {e}"
            print(f"[TypeClf] ❌ {self.load_error}", flush=True)
            return False

    # ---------- 预测 ----------
    @torch.no_grad()
    def predict_bytes(self, image_bytes: bytes, topk: int = 3) -> Optional[Dict]:
        """
        返回:
          {
            "top1": {"code","name","group","prob","desc"},
            "topk": [ ... ],          # 前 K 个
            "all_probs": {code: prob},# 全部类别概率
            "group_sum": {"benign": p, "malignant": p},  # 按医学分组聚合
            "infer_ms": float,
            "model_acc": float,       # 该模型自身准确率（用于前端标注可信度）
            "disclaimer": str,
          }
        未就绪时返回 None（调用方应优雅处理）
        """
        if not self.ready:
            return None

        t0 = time.time()

        # ---------- 取概率（ONNX 或 PyTorch）----------
        if self.backend == "onnx-int8" and self.onnx is not None:
            probs = self.onnx.predict_probs(image_bytes).tolist()
        else:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            x = self._transform(img).unsqueeze(0).to(self.device)
            with self.infer_lock:
                logits = self.model(x)
                probs = torch.softmax(logits.float(), dim=1)[0].cpu().tolist()

        pairs = sorted(zip(self.classes, probs), key=lambda kv: -kv[1])
        topk_list = []
        for code, p in pairs[:topk]:
            topk_list.append({
                "code": code,
                "name": TYPE_CN.get(code, code),
                "group": TYPE_GROUP.get(code, "unknown"),
                "prob": round(float(p), 4),
                "desc": TYPE_DESC.get(code, ""),
            })

        all_probs = {c: round(float(p), 4) for c, p in zip(self.classes, probs)}
        group_sum = {"benign": 0.0, "malignant": 0.0}
        for c, p in zip(self.classes, probs):
            g = TYPE_GROUP.get(c)
            if g in group_sum:
                group_sum[g] += float(p)
        group_sum = {k: round(v, 4) for k, v in group_sum.items()}

        infer_ms = (time.time() - t0) * 1000
        self.infer_count += 1

        return {
            "top1": topk_list[0] if topk_list else None,
            "topk": topk_list,
            "all_probs": all_probs,
            "group_sum": group_sum,
            "infer_ms": round(infer_ms, 1),
            "model_acc": getattr(config, "TYPE_MODEL_ACCURACY", 0.7432),
            "disclaimer": getattr(config, "TYPE_DISCLAIMER", ""),
        }

    def warmup(self):
        if not self.ready:
            return
        try:
            import numpy as np
            dummy = (np.random.rand(self.img_size, self.img_size, 3) * 255).astype("uint8")
            buf = io.BytesIO()
            Image.fromarray(dummy).save(buf, format="PNG")
            self.predict_bytes(buf.getvalue())
            self.infer_count = 0
            print("[TypeClf] 预热完成", flush=True)
        except Exception as e:
            print(f"[TypeClf] 预热跳过: {e}", flush=True)

    def status(self) -> Dict:
        return {
            "enabled": self.enabled,
            "ready": self.ready,
            "backend": self.backend,
            "model_path": self.model_path,
            "arch": self.arch,
            "img_size": self.img_size,
            "classes": self.classes,
            "num_classes": len(self.classes),
            "classes_cn": {c: TYPE_CN.get(c, c) for c in self.classes},
            "load_time_s": round(self.load_time, 3),
            "load_error": self.load_error,
            "infer_count": self.infer_count,
        }
