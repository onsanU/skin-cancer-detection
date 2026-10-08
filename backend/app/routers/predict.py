#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图像检测路由：上传图像 → 良恶性判别 + 健康建议"""

import json
import os
import random
import shutil
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import config, database
from ..routers.auth import get_current_user, resolve_optional_user
from ..services.predictor import Predictor

router = APIRouter(prefix="/api", tags=["图像检测"])

# ---------- 部位知识（懒加载 + 进程内缓存）----------
_LOC_KNOWLEDGE = None


def _load_location_knowledge():
    """读取部位知识数据（只加载一次）"""
    global _LOC_KNOWLEDGE
    if _LOC_KNOWLEDGE is None:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "location_knowledge.json")
        try:
            with open(path, encoding="utf-8") as f:
                _LOC_KNOWLEDGE = json.load(f)
        except Exception as e:
            print(f"[predict] 部位知识加载失败: {type(e).__name__}: {e}", flush=True)
            _LOC_KNOWLEDGE = {"sites": {}}
    return _LOC_KNOWLEDGE



def _validate_upload(file: UploadFile) -> None:
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in config.ALLOWED_EXT:
        raise HTTPException(
            400, f"不支持的图片格式: {ext or '(无扩展名)'}。"
                 f"支持的格式: {', '.join(sorted(config.ALLOWED_EXT))}"
        )


def _save_upload(file: UploadFile, user_id: Optional[int]) -> tuple:
    """保存上传文件，返回 (原始文件名, 存储路径)"""
    ext = os.path.splitext(file.filename or ".jpg")[1].lower() or ".jpg"
    uid_part = f"u{user_id}" if user_id else "guest"
    stamp = time.strftime("%Y%m%d_%H%M%S")
    stored_name = f"{uid_part}_{stamp}_{uuid.uuid4().hex[:8]}{ext}"
    stored_path = os.path.join(config.UPLOAD_DIR, stored_name)
    with open(stored_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    size_mb = os.path.getsize(stored_path) / 1024 / 1024
    if size_mb > config.MAX_UPLOAD_MB:
        os.remove(stored_path)
        raise HTTPException(400, f"图片过大（{size_mb:.1f}MB），限制 {config.MAX_UPLOAD_MB}MB")
    return file.filename or stored_name, stored_path


@router.post("/predict", summary="皮肤病变图像检测")
async def predict(
    file: UploadFile = File(..., description="皮肤病变图像（jpg/png等）"),
    threshold: Optional[float] = Form(None, description="恶性判定阈值。不传则用当前模式默认值（集成0.51/单模型0.50）；降低可提高召回"),
    note: Optional[str] = Form("", description="备注"),
    location: Optional[str] = Form(None, description="病变部位（可选，仅作科普参考，不参与判定）"),
    user=Depends(resolve_optional_user),
):
    """
    上传皮肤病变图像，返回良恶性判别结果与健康建议。

    - **file**: 图像文件
    - **threshold**: 恶性概率判定阈值（默认 0.5；医疗场景可设 0.45 提升召回）
    - **note**: 可选的用户备注
    - **location**: 可选的病变部位（face/scalp/trunk/arm/leg/genital/unknown），
      仅用于返回该部位的群体统计参考，不影响模型判定

    游客也可使用，但不会保存检测记录。
    """
    predictor = Predictor.get()
    if not predictor.ready:
        raise HTTPException(503, f"模型未就绪：{predictor.load_error}")

    _validate_upload(file)
    original_name, stored_path = _save_upload(file, user["id"] if user else None)

    # 读取字节用于推理
    with open(stored_path, "rb") as f:
        image_bytes = f.read()

    try:
        result = predictor.predict_bytes(image_bytes, threshold=threshold)
    except Exception as e:
        raise HTTPException(500, f"推理失败: {type(e).__name__}: {e}")

    label = result["label"]
    advice = dict(config.ADVICE[label])       # 复制一份，避免污染全局配置

    # ---- 7 类类型推理（辅助参考，失败不影响主结论）----
    type_info = None
    try:
        from ..services.type_classifier import TypeClassifier
        tc = TypeClassifier.get()
        if tc.ready:
            type_info = tc.predict_bytes(image_bytes, topk=3)
    except Exception as e:
        print(f"[predict] 类型推理跳过: {type(e).__name__}: {e}", flush=True)

    # ---- 按 top1 类型叠加【细分建议】----
    #    仅当类型模型就绪且置信度不过低时附加，避免低质量提示误导用户
    type_advice = None
    if type_info and type_info.get("top1"):
        top1 = type_info["top1"]
        code = top1.get("code") or top1.get("class")
        code_bin = top1.get("group")            # malignant / benign
        prob = float(top1.get("prob") or 0.0)
        cfg_adv = getattr(config, "TYPE_ADVICE", {}).get(code)
        # 一致性保护：类型归属与主判定不矛盾时才附加
        consistent = (code_bin is None) or (code_bin == label)
        if cfg_adv and prob >= 0.30 and consistent:
            type_advice = {
                "code": code,
                "name": cfg_adv["name"],
                "urgency": cfg_adv["urgency"],
                "focus": cfg_adv["focus"],
                "actions": cfg_adv["actions"],
                "prob": round(prob, 4),
                "disclaimer": getattr(config, "TYPE_ADVICE_DISCLAIMER", ""),
            }
            advice["type_advice"] = type_advice

    # ---- 部位知识参考（用户选定部位时附加；仅作科普，不参与判定）----
    location_info = None
    if location:
        knowledge = _load_location_knowledge()
        site = knowledge.get("sites", {}).get(location)
        label_cn = next((o["label"] for o in config.LOCATION_OPTIONS
                         if o["key"] == location), location)
        if site:
            location_info = {
                "key": location,
                "label": label_cn,
                "n": site["n"],
                "malignant_pct": site["malignant_pct"],
                "top_types": site["top_types"],
                "top_malignant": site.get("top_malignant"),
                "source": knowledge.get("source", ""),
                "disclaimer": getattr(config, "LOCATION_DISCLAIMER", ""),
            }

    record_id = None
    if user:
        record_id = database.create_record(
            user_id=user["id"],
            filename=original_name,
            stored_path=stored_path,
            label=label,
            label_cn=result["label_cn"],
            probability=result["probability"],
            malignant_prob=result["malignant_prob"],
            benign_prob=result["benign_prob"],
            threshold=result["threshold"],
            infer_ms=result["infer_ms"],
            note=note or "",
        )

    resp = {
        "record_id": record_id,
        "result": {
            "label": label,
            "label_cn": result["label_cn"],
            "probability": result["probability"],
            "malignant_prob": result["malignant_prob"],
            "benign_prob": result["benign_prob"],
            "threshold": result["threshold"],
            "infer_ms": result["infer_ms"],
        },
        "advice": advice,
        "image_url": f"/api/image/{os.path.basename(stored_path)}",
        "saved": bool(user),
        "disclaimer": config.DISCLAIMER,
    }

    # 推理模式信息（集成 / 单模型）
    if "mode" in result:
        resp["result"]["mode"] = result["mode"]
        resp["result"]["members"] = result.get("members", [])

    # 类型参考信息（独立于主结论，前端应标注为"仅供参考"）
    if type_info:
        resp["type_reference"] = type_info

    # 部位知识参考（仅科普，不参与判定）
    if location_info:
        resp["location_reference"] = location_info

    # ---- 可解释性分析（Grad-CAM 热力图 + 配套图表；失败静默降级）----
    #   必须放在 resp 之后：任何异常都只影响解释部分，主结论照常返回
    try:
        from ..services import gradcam as _gradcam
        cam_raw = _gradcam.CamService.generate_all(image_bytes, save=True)
        if cam_raw:
            from ..services import explain as _explain
            analysis = _explain.build_analysis(
                gradcam_result=cam_raw,
                prob_malignant=result["malignant_prob"],
                feature_vec=cam_raw.get("feature_vec"),
                cams_raw=cam_raw.get("_cams_raw"),
                threshold=result.get("threshold"),
            )
            if analysis:
                resp["explanation"] = analysis
            # 热力图图集（前端渲染用）
            resp["gradcam"] = {
                "images": cam_raw.get("images", []),
                "method": cam_raw.get("method", "Grad-CAM"),
                "target_layer": cam_raw.get("target_layer", {}),
                "legend": cam_raw.get("legend", {}),
                "elapsed_ms": cam_raw.get("elapsed_ms"),
                "disclaimer": cam_raw.get("disclaimer", ""),
            }
        # 周期清理旧热力图（约每 200 次检测清一次，避免磁盘堆积）
        if random.random() < 0.005:
            n = _gradcam.cleanup_old_cams(keep=300)
            if n:
                print(f"[predict] 已清理 {n} 张过期热力图", flush=True)
    except Exception as e:
        print(f"[predict] 可解释性分析跳过: {type(e).__name__}: {e}", flush=True)

    return resp


@router.get("/image/{name}", summary="获取上传的图片")
def get_image(name: str):
    """按存储名读取图片（做路径穿越防护）"""
    safe = os.path.basename(name)
    path = os.path.join(config.UPLOAD_DIR, safe)
    if not os.path.isfile(path):
        raise HTTPException(404, "图片不存在")
    return FileResponse(path)


@router.get("/image/cam/{name}", summary="获取 Grad-CAM 热力图")
def get_cam_image(name: str):
    """按存储名读取热力图（路径穿越防护）"""
    safe = os.path.basename(name)
    path = os.path.join(config.UPLOAD_DIR, "cam", safe)
    if not os.path.isfile(path):
        raise HTTPException(404, "热力图不存在")
    return FileResponse(path, media_type="image/png")


@router.get("/explain/feature-surface", summary="特征空间底图数据")
def feature_surface():
    """
    返回 val 集的 UMAP 特征空间投影（静态缓存）。
    前端用它作为散点图底图，再叠加当前图像的落点。
    """
    from ..services import explain as _explain
    surf = _explain.load_surface()
    if not surf:
        raise HTTPException(
            404,
            "特征空间数据未生成。请先运行：python src/gen_feature_surface.py"
        )
    # 不返回 note 以外的重字段；points 已是精简格式
    return {
        "method": surf.get("method"),
        "n_samples": surf.get("n_samples"),
        "n_benign": surf.get("n_benign"),
        "n_malignant": surf.get("n_malignant"),
        "feature_dim": surf.get("feature_dim"),
        "members": surf.get("members", []),
        "source": surf.get("source", ""),
        "note": surf.get("note", ""),
        "umap_params": surf.get("umap_params", {}),
        "points": surf.get("points", []),
    }


@router.get("/model/info", summary="模型信息")
def model_info():
    p = Predictor.get()
    info = {"model": p.status(), "disclaimer": config.DISCLAIMER}
    # 7 类类型模型状态（辅助）
    try:
        from ..services.type_classifier import TypeClassifier
        info["type_model"] = TypeClassifier.get().status()
    except Exception as e:
        info["type_model"] = {"ready": False, "load_error": str(e)}
    return info


@router.get("/model/types", summary="7 类病变类型定义")
def model_types():
    """返回 7 类类型的编码、中文名、医学分组与说明"""
    from ..services.type_classifier import TYPE_CN, TYPE_DESC, TYPE_GROUP
    return {
        "classes": [
            {"code": c, "name": TYPE_CN[c], "group": TYPE_GROUP[c], "desc": TYPE_DESC[c]}
            for c in TYPE_CN
        ],
        "group_cn": {"benign": "良性", "malignant": "恶性"},
        "model_accuracy": getattr(config, "TYPE_MODEL_ACCURACY", None),
        "disclaimer": getattr(config, "TYPE_DISCLAIMER", ""),
    }


@router.get("/thresholds", summary="可用判定阈值预设")
def thresholds():
    """返回三种工作模式的阈值配置，前端可据此提供切换"""
    p = Predictor.get()
    # 集成模式有专属推荐阈值，单模型用默认阈值
    default_thr = (getattr(config, "ENSEMBLE_THRESHOLD", 0.51)
                   if p.is_ensemble else config.MALIGNANT_THRESHOLD)
    return {
        "presets": config.THRESHOLD_PRESETS,
        "default": default_thr,
        "mode": "ensemble" if p.is_ensemble else "single",
        "note": "阈值越低越敏感（恶性召回高、漏诊少），代价是误报增多",
    }
