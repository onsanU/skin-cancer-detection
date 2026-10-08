#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ONNX 推理后端（可选）
================================================================
当 models_compressed/model_int8.onnx 存在且 config.USE_ONNX=True 时，
Predictor 会优先走这条路径（体积小、内存占用低）。

接口与 torch 版本保持一致，便于无缝替换。
"""

import io
import os
import threading
from typing import Dict, Optional

import numpy as np
from PIL import Image

from .. import config

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class OnnxBackend:
    """ONNX Runtime 推理后端"""

    def __init__(self, model_path: str, img_size: int = 224, classes=None):
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = config.ONNX_THREADS
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = ort.InferenceSession(
            model_path, so, providers=["CPUExecutionProvider"]
        )
        self.input_name = self.sess.get_inputs()[0].name
        self.output_name = self.sess.get_outputs()[0].name
        self.img_size = img_size
        self.classes = classes or list(config.CLASSES)
        self.model_path = model_path
        self.lock = threading.Lock()

    def _preprocess(self, image_bytes: bytes) -> np.ndarray:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = img.resize((self.img_size, self.img_size), Image.BILINEAR)
        x = np.asarray(img, dtype=np.float32) / 255.0
        x = (x - IMAGENET_MEAN) / IMAGENET_STD
        x = np.transpose(x, (2, 0, 1))[None, ...]      # NCHW
        return np.ascontiguousarray(x, dtype=np.float32)

    def predict_probs(self, image_bytes: bytes) -> np.ndarray:
        """返回完整 softmax 概率数组（长度 = 类别数），支持二分类/多分类"""
        x = self._preprocess(image_bytes)
        with self.lock:
            logits = self.sess.run([self.output_name], {self.input_name: x})[0]
        e = np.exp(logits - logits.max(axis=1, keepdims=True))
        return (e / e.sum(axis=1, keepdims=True))[0]

    def predict(self, image_bytes: bytes, threshold: float = 0.5) -> Dict:
        """二分类预测（保持向后兼容）"""
        probs = self.predict_probs(image_bytes)

        p_benign, p_malignant = float(probs[0]), float(probs[1])
        is_mal = p_malignant >= threshold
        label = "malignant" if is_mal else "benign"
        return {
            "label": label,
            "label_cn": config.CLASS_CN.get(label, label),
            "probability": round(p_malignant if is_mal else p_benign, 4),
            "confidence": round(p_malignant if is_mal else p_benign, 4),
            "malignant_prob": round(p_malignant, 4),
            "benign_prob": round(p_benign, 4),
            "threshold": threshold,
        }

    @property
    def size_mb(self) -> float:
        return os.path.getsize(self.model_path) / 1024 / 1024
