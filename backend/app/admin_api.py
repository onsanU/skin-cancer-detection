#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""管理后台 API（独立模块）

设计要点（与医小喵 admin_api 同构）：
- main.py 只加一行 include_router(prefix="/admin/api")，且必须放在根 mount 之前
- 引用 main/config 的常量用「函数内延迟 import」，避免循环依赖
- 所有接口统一依赖 get_current_admin（401 未登录 / 403 非管理员）
- system 接口优雅降级：模型未就绪返回 ok:false，不拖垮其他数据

接口清单：
  GET    /admin/api/stats             数据看板统计
  GET    /admin/api/records           检测记录（分页/筛选/搜索）
  GET    /admin/api/records/{id}      单条记录详情
  DELETE /admin/api/records/{id}      删除记录（含磁盘图片）
  GET    /admin/api/users             用户列表（分页/筛选/搜索）
  GET    /admin/api/users/{id}        用户详情（含最近记录）
  POST   /admin/api/users/{id}/role   调整角色（防自降级）
  POST   /admin/api/users/{id}/password  重置密码
  POST   /admin/api/users/{id}/active 启用/禁用账号
  DELETE /admin/api/users/{id}/records 清空该用户检测记录
  GET    /admin/api/system            系统状态
"""

import os
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from . import config, database
from .audit import ACTION_LABELS, action_label, mark_action
from .routers.auth import get_current_admin
from .services.auth import hash_password

router = APIRouter(tags=["管理后台"])

_START_TS = time.time()


# ==================== Schemas ====================
class RoleReq(BaseModel):
    role: str = Field(..., description="目标角色: user / admin")


class PasswordReq(BaseModel):
    password: str = Field(..., min_length=6, max_length=128,
                          description="新密码（至少 6 位）")


class ActiveReq(BaseModel):
    is_active: bool = Field(..., description="true=启用, false=禁用")


# ==================== 工具 ====================
def _record_out(r) -> dict:
    """记录行 → 前端 dict（fields 与 /api/records 保持一致，额外带用户名）"""
    d = {
        "id": r["id"],
        "user_id": r["user_id"],
        "username": r["username"] if "username" in r.keys() else "—",
        "filename": r["filename"],
        "label": r["label"],
        "label_cn": r["label_cn"],
        "probability": r["probability"],
        "malignant_prob": r["malignant_prob"],
        "benign_prob": r["benign_prob"],
        "threshold": r["threshold"],
        "infer_ms": r["infer_ms"],
        "note": r["note"],
        "created_at": r["created_at"],
        "image_url": f"/api/image/{os.path.basename(r['stored_path'])}",
        "stored_path": r["stored_path"],
    }
    return d


def _user_out(r) -> dict:
    return {
        "id": r["id"],
        "username": r["username"],
        "email": r["email"],
        "full_name": r["full_name"] if "full_name" in r.keys() else "",
        "role": r["role"] if "role" in r.keys() else "user",
        "is_active": bool(r["is_active"]) if "is_active" in r.keys() else True,
        "created_at": r["created_at"],
        "record_count": r["record_count"] if "record_count" in r.keys() else 0,
        "malignant_count": (r["malignant_count"] or 0)
        if "malignant_count" in r.keys() else 0,
    }


def _model_status() -> dict:
    """模型状态（延迟 import，避免循环依赖）"""
    try:
        from .services.predictor import Predictor
        return Predictor.get().status()
    except Exception as e:
        return {"ready": False, "error": str(e)}


def _type_model_status() -> dict:
    try:
        from .services.type_classifier import TypeClassifier
        tc = TypeClassifier.get()
        return {"ready": tc.ready, "backend": getattr(tc, "backend", "—")}
    except Exception as e:
        return {"ready": False, "error": str(e)}


def _ollama_models() -> dict:
    """探测 Ollama 及各问答模型（供系统状态页展示全部模型）"""
    try:
        from .services import llm
        st = llm.ollama_ready(timeout=3)
        return {
            "online": bool(st.get("ok")),
            "endpoint": llm.OLLAMA_URL,
            "text_model": llm.TEXT_MODEL,
            "vision_model": llm.VISION_MODEL,
            "installed": st.get("models", []),
            "text_ready": bool(st.get("text_model_ready")),
            "vision_ready": bool(st.get("vision_model_ready")),
        }
    except Exception as e:
        return {"online": False, "error": str(e)}


def _all_models() -> list:
    """全站模型清单 —— 系统实际加载/依赖的所有模型（不止图像检测那一个）

    清单来源三处：
      1. 图像良恶性主判定：pytorch 集成（config.ENSEMBLE_MODELS，可为单模型）
      2. 7 类病变类型参考：ONNX INT8（services.type_classifier）
      3. 医疗问答：Ollama 的文本模型（医疗微调）与视觉模型（看图）
    """
    items = []

    # ---- 1. 图像良恶性主判定 ----
    m = _model_status()
    ens_members = getattr(config, "ENSEMBLE_MODELS", []) or []
    is_ens = bool(m.get("ensemble"))
    role = "图像 · 良恶性主判定"
    if is_ens:
        names = [it[0] for it in ens_members if it] or \
                [str(x) for x in (m.get("ensemble_members") or [])]
        for i, name in enumerate(names):
            files = [it[1] for it in ens_members if it and it[0] == name]
            items.append({
                "role": role,
                "name": name + ("/" + files[0] if files else ""),
                "backend": m.get("backend", "—"),
                "device": m.get("device", "—"),
                "detail": f"集成成员 {i + 1}/{len(names)}"
                          + ("（集成阈值 " + str(getattr(config, 'ENSEMBLE_THRESHOLD', '—')) + "）" if i == 0 else ""),
                "ready": bool(m.get("ready")),
                "group": "image",
            })
    else:
        items.append({
            "role": role,
            "name": m.get("model_path") or m.get("arch", "—"),
            "backend": m.get("backend", "—"),
            "device": m.get("device", "—"),
            "detail": f"{m.get('arch', '—')} · {m.get('img_size', '—')}×{m.get('img_size', '—')}",
            "ready": bool(m.get("ready")),
            "group": "image",
        })

    # ---- 2. 7 类病变类型参考 ----
    # ⚠️ config 没有 TYPE_NUM_CLASSES，类数从 TypeClassifier 实例取（取不到则退回 7）
    t = _type_model_status()
    try:
        from .services.type_classifier import TypeClassifier
        num_cls = len(getattr(TypeClassifier.get(), "classes", []) or []) or 7
    except Exception:
        num_cls = 7
    onnx_path = getattr(config, "TYPE_ONNX_PATH", "") or ""
    try:  # 展示相对路径更短更可读
        onnx_show = os.path.relpath(onnx_path, config.PROJ_ROOT) if onnx_path else "—"
    except Exception:
        onnx_show = onnx_path or "—"
    items.append({
        "role": "图像 · 7 类病变类型参考",
        "name": onnx_show,
        "backend": t.get("backend", "—"),
        "device": "cpu",
        "detail": f"{num_cls} 类细分（黑色素瘤 / 痣 / 基底细胞癌 等）· ONNX INT8 量化",
        "ready": bool(t.get("ready")),
        "group": "image",
    })

    # ---- 3. 医疗问答（Ollama）----
    o = _ollama_models()
    if not o.get("online"):
        items.append({
            "role": "医疗问答 · 文本问答",
            "name": o.get("text_model", "—"),
            "backend": "ollama",
            "device": "gpu/cpu",
            "detail": "Ollama 未运行" + ("（" + o["error"] + "）" if o.get("error") else ""),
            "ready": False,
            "group": "chat",
        })
    else:
        items.append({
            "role": "医疗问答 · 文本问答",
            "name": o.get("text_model", "—"),
            "backend": "ollama",
            "device": "gpu/cpu",
            "detail": "5000 条医疗数据微调 · 医疗知识问答",
            "ready": bool(o.get("text_ready")),
            "group": "chat",
        })
        items.append({
            "role": "医疗问答 · 看图问答",
            "name": o.get("vision_model", "—"),
            "backend": "ollama",
            "device": "gpu/cpu",
            "detail": "支持带图提问（皮肤病变照片）",
            "ready": bool(o.get("vision_ready")),
            "group": "chat",
        })

    return items


# ==================== 1. 数据看板 ====================
@router.get("/stats", summary="数据看板统计")
def admin_stats(
    grain: str = Query("day", description="趋势粒度: day / week / month"),
    source: str = Query("record", description="趋势数据源: record(图像) / chat(问答) / all(合计)"),
    admin=Depends(get_current_admin),
):
    """全站统计：用户数/记录数/良恶性分布/今日新增/趋势/Top用户 + 问答数据

    ⚠️ 口径说明（重要，勿混）：
      · total_records / malignant / benign / malignant_rate —— 全部【仅图像检测】
        问答没有良恶性标签，混入分母会让占比失真，故恒定只用 records 表。
      · chat —— 问答独立统计（会话数/消息数/提问数），单独展示。
      · trend —— 由 grain + source 决定粒度与数据源，前端可切换。
    """
    data = database.admin_stats()
    data["chat"] = database.admin_chat_stats()
    data["trend"] = database.admin_trend(grain, source)
    data["trend_grain"] = grain
    data["trend_source"] = source
    data["model"] = _model_status()
    data["uptime_seconds"] = int(time.time() - _START_TS)
    return data


# ==================== 2. 检测记录管理 ====================
@router.get("/records", summary="检测记录列表")
def admin_records(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    label: Optional[str] = Query(None, description="筛选: benign / malignant"),
    keyword: Optional[str] = Query(None, description="搜索文件名/用户名/备注"),
    username: Optional[str] = Query(None, description="按用户名精确筛选"),
    admin=Depends(get_current_admin),
):
    if label and label not in config.CLASSES:
        raise HTTPException(400, f"label 必须是 {config.CLASSES} 之一")
    rows, total = database.admin_list_records(limit, offset, label, keyword, username)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_record_out(r) for r in rows],
    }


@router.get("/records/{record_id}", summary="记录详情")
def admin_record_detail(record_id: int, admin=Depends(get_current_admin)):
    r = database.admin_get_record(record_id)
    if not r:
        raise HTTPException(404, "记录不存在")
    d = _record_out(r)
    d["advice"] = config.ADVICE.get(r["label"], {})
    d["disclaimer"] = config.DISCLAIMER
    return d


@router.delete("/records/{record_id}", summary="删除记录")
def admin_record_delete(record_id: int, request: Request,
                        admin=Depends(get_current_admin)):
    r = database.admin_get_record(record_id)
    if not r:
        # 守卫：不存在时 deleted:0，不误报成功
        return {"deleted": 0, "message": "记录不存在"}
    try:
        if os.path.isfile(r["stored_path"]):
            os.remove(r["stored_path"])
    except Exception:
        pass
    ok = database.admin_delete_record(record_id)
    mark_action(request, "record.delete", target_type="record", target_id=record_id,
                target_name=r["filename"] if r["filename"] else f"#{record_id}",
                detail=f"删除检测记录（{r['label_cn'] if 'label_cn' in r.keys() else ''}）")
    return {"deleted": 1 if ok else 0,
            "message": "删除成功" if ok else "删除失败", "id": record_id}


# ==================== 2.5 问答记录管理 ====================
# 问答数据与图像检测分表存放，管理端独立接口。
def _chat_out(r) -> dict:
    """会话行 → 前端 dict"""
    return {
        "id": r["id"],
        "user_id": r["user_id"],
        "username": r["username"] if "username" in r.keys() else "—",
        "title": r["title"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "msg_count": r["msg_count"] if "msg_count" in r.keys() else 0,
        "first_q": (r["first_q"] or "") if "first_q" in r.keys() else "",
    }


@router.get("/chats", summary="问答记录列表")
def admin_chats(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    keyword: Optional[str] = Query(None, description="搜索会话标题/用户名"),
    username: Optional[str] = Query(None, description="按用户名精确筛选"),
    admin=Depends(get_current_admin),
):
    rows, total = database.admin_list_chats(limit, offset, keyword, username)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_chat_out(r) for r in rows],
    }


@router.get("/chats/{session_id}", summary="问答会话详情（含消息）")
def admin_chat_detail(session_id: int, admin=Depends(get_current_admin)):
    d = database.admin_get_chat(session_id)
    if not d:
        raise HTTPException(404, "会话不存在")
    s, msgs = d["session"], d["messages"]
    out = _chat_out(s)
    out["messages"] = [
        {
            "id": m["id"],
            "role": m["role"],
            "content": m["content"],
            "model": m["model"] if "model" in m.keys() else "",
            "elapsed_ms": m["elapsed_ms"] if "elapsed_ms" in m.keys() else 0,
            "has_image": bool(m["image_path"] if "image_path" in m.keys() else ""),
            "image_url": f"/api/chat/image/{os.path.basename(m['image_path'])}"
            if ("image_path" in m.keys() and m["image_path"]) else "",
            "created_at": m["created_at"],
        }
        for m in msgs
    ]
    out["disclaimer"] = config.DISCLAIMER
    return out


@router.delete("/chats/{session_id}", summary="删除问答会话")
def admin_chat_delete(session_id: int, request: Request,
                      admin=Depends(get_current_admin)):
    d = database.admin_get_chat(session_id)
    if not d:
        # 与记录删除保持一致：不存在时返回 deleted:0，不误报成功
        return {"deleted": 0, "message": "会话不存在"}
    s = d["session"]
    n = database.admin_delete_chat(session_id)
    mark_action(request, "chat.delete", target_type="chat", target_id=session_id,
                target_name=s["title"] or f"#{session_id}",
                detail=f"删除问答会话（{s['username']} · {len(d['messages'])} 条消息）")
    return {"deleted": 1, "messages": n, "message": "删除成功", "id": session_id}


# ==================== 3. 用户管理 ====================
@router.get("/users", summary="用户列表")
def admin_users(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    keyword: Optional[str] = Query(None, description="搜索用户名/邮箱/姓名"),
    role: Optional[str] = Query(None, description="筛选: user / admin"),
    admin=Depends(get_current_admin),
):
    if role and role not in ("user", "admin"):
        raise HTTPException(400, "role 必须是 user 或 admin")
    rows, total = database.admin_list_users(limit, offset, keyword, role)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_user_out(r) for r in rows],
    }


@router.get("/users/{user_id}", summary="用户详情")
def admin_user_detail(user_id: int, admin=Depends(get_current_admin)):
    u = database.admin_get_user(user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    rows = database.list_records(user_id, limit=10, offset=0)
    d = _user_out(u)
    d["recent_records"] = [
        {"id": r["id"], "filename": r["filename"], "label_cn": r["label_cn"],
         "probability": r["probability"], "created_at": r["created_at"]}
        for r in rows
    ]
    return d


@router.post("/users/{user_id}/role", summary="调整用户角色")
def admin_set_role(user_id: int, req: RoleReq, request: Request,
                   admin=Depends(get_current_admin)):
    # 审计标注放在守卫之前：即使操作被拒绝（400），日志里也能看到「谁试图改谁的角色」
    mark_action(request, "user.role", target_type="user", target_id=user_id,
                target_name=req.role, detail=f"请求角色：{req.role}")
    if req.role not in ("user", "admin"):
        raise HTTPException(400, "role 必须是 user 或 admin")
    u = database.admin_get_user(user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    # 防自降级：不能把自己降成普通用户（否则后台失联）
    if user_id == admin["id"] and req.role != "admin":
        raise HTTPException(400, "不能降级自己的账号，请用其他管理员操作")
    # 防最后一个管理员被降级
    if req.role != "admin" and u["role"] == "admin" and database.count_admins() <= 1:
        raise HTTPException(400, "系统必须保留至少一名管理员")
    database.set_user_role(user_id, req.role)
    mark_action(request, "user.role", target_type="user", target_id=user_id,
                target_name=u["username"], detail=f"角色：{u['role']} → {req.role}")
    return {"message": f"角色已改为 {req.role}", "id": user_id, "role": req.role}


@router.post("/users/{user_id}/password", summary="重置用户密码")
def admin_reset_password(user_id: int, req: PasswordReq, request: Request,
                         admin=Depends(get_current_admin)):
    u = database.admin_get_user(user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    database.set_user_password(user_id, hash_password(req.password))
    mark_action(request, "user.password", target_type="user", target_id=user_id,
                target_name=u["username"], detail="重置登录密码")
    return {"message": "密码已重置", "id": user_id,
            "note": "密码哈希不可逆查看，请通知用户使用新密码登录"}


@router.post("/users/{user_id}/active", summary="启用/禁用账号")
def admin_set_active(user_id: int, req: ActiveReq, request: Request,
                     admin=Depends(get_current_admin)):
    u = database.admin_get_user(user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    if user_id == admin["id"] and not req.is_active:
        raise HTTPException(400, "不能禁用自己的账号")
    if (not req.is_active and u["role"] == "admin"
            and database.count_admins() <= 1):
        raise HTTPException(400, "系统必须保留至少一名可用管理员")
    database.set_user_active(user_id, req.is_active)
    mark_action(request, "user.active", target_type="user", target_id=user_id,
                target_name=u["username"],
                detail="启用账号" if req.is_active else "禁用账号")
    return {"message": "已启用" if req.is_active else "已禁用",
            "id": user_id, "is_active": req.is_active}


@router.delete("/users/{user_id}/records", summary="清空用户检测记录")
def admin_clear_user_records(user_id: int, request: Request,
                             admin=Depends(get_current_admin)):
    u = database.admin_get_user(user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    n = database.delete_user_records(user_id)
    mark_action(request, "user.records.clear", target_type="user", target_id=user_id,
                target_name=u["username"], detail=f"清空 {n} 条检测记录")
    return {"deleted": n, "message": f"已清空 {n} 条记录", "id": user_id}


# ==================== 4. 系统状态 ====================
def _probe_mysql(timeout: int = 3) -> dict:
    """
    探测 MySQL 是否可用（供管理后台提示"可切换"）。
    只做 TCP 连通性检查，不建连接池、不写数据，失败也不抛异常。
    """
    import socket
    try:
        s = socket.create_connection((config.MYSQL_HOST, config.MYSQL_PORT), timeout)
        s.close()
        return {"reachable": True, "host": config.MYSQL_HOST,
                "port": config.MYSQL_PORT, "database": config.MYSQL_DATABASE}
    except Exception as e:
        return {"reachable": False, "host": config.MYSQL_HOST,
                "port": config.MYSQL_PORT, "reason": str(e)}


@router.get("/system", summary="系统状态")
def admin_system(admin=Depends(get_current_admin)):
    """系统运行状态：模型/数据库/磁盘/配置（优雅降级）"""
    disk = {}
    try:
        import shutil
        total, used, free = shutil.disk_usage(config.PROJ_ROOT)
        disk = {
            "total_gb": round(total / 1024 ** 3, 1),
            "used_gb": round(used / 1024 ** 3, 1),
            "free_gb": round(free / 1024 ** 3, 1),
            "used_percent": round(used / total * 100, 1),
        }
    except Exception as e:
        disk = {"error": str(e)}

    uploads = {}
    try:
        files = [f for f in os.listdir(config.UPLOAD_DIR)
                 if os.path.isfile(os.path.join(config.UPLOAD_DIR, f))]
        size = sum(os.path.getsize(os.path.join(config.UPLOAD_DIR, f))
                   for f in files)
        uploads = {"count": len(files), "size_mb": round(size / 1024 ** 2, 1)}
    except Exception as e:
        uploads = {"error": str(e)}

    db_size = 0
    try:
        db_size = round(os.path.getsize(config.DB_PATH) / 1024 ** 2, 2)
    except Exception:
        pass

    # ---------- 当前数据库后端（双模式）----------
    # 说明：DB_BACKEND 在服务启动时读取，运行期不可热切换（改配置需重启）
    backend = "mysql" if getattr(database, "USE_MYSQL", False) else "sqlite"
    if backend == "mysql":
        database_info = {
            "backend": "mysql",
            "label": "MySQL",
            "host": config.MYSQL_HOST,
            "port": config.MYSQL_PORT,
            "name": config.MYSQL_DATABASE,
            "user": config.MYSQL_USER,
            # 展示用连接串（不含密码，避免泄露）
            "dsn": f"{config.MYSQL_USER}@{config.MYSQL_HOST}:{config.MYSQL_PORT}/{config.MYSQL_DATABASE}",
            "size_mb": None,      # MySQL 不统计单文件大小
            "path": f"{config.MYSQL_HOST}:{config.MYSQL_PORT}/{config.MYSQL_DATABASE}",
            "switch_cmd": "bash start.sh --sqlite",
            "switch_to": "sqlite",
            "note": "数据存放在 Windows 侧 MySQL 8.0.29，独立库 skin_cancer（与医小喵隔离）",
        }
    else:
        database_info = {
            "backend": "sqlite",
            "label": "SQLite",
            "host": "",
            "port": 0,
            "name": os.path.basename(config.DB_PATH),
            "user": "",
            "dsn": config.DB_PATH,
            "size_mb": db_size,
            "path": config.DB_PATH,
            "switch_cmd": "bash start.sh --mysql",
            "switch_to": "mysql",
            "note": "零配置单文件数据库，数据在 backend/skin_cancer.db（答辩演示首选）",
        }
    database_info["users"] = database.count_users()
    database_info["records"] = sum(
        database.admin_stats()[k] for k in ("benign", "malignant"))

    # 另一个库的可用性探测（供前端提示"可切换"）
    database_info["mysql_available"] = _probe_mysql()
    database_info["sqlite_exists"] = os.path.isfile(config.DB_PATH)

    return {
        "service": {
            "name": "皮肤癌图像检测系统",
            "version": "1.1.0",
            "uptime_seconds": int(time.time() - _START_TS),
            "uptime_human": _human_uptime(time.time() - _START_TS),
            "started_at": datetime.fromtimestamp(_START_TS).strftime(
                "%Y-%m-%d %H:%M:%S"),
        },
        "model": _model_status(),
        "type_model": _type_model_status(),
        # 全站模型清单（图像主判定 / 7 类参考 / 问答文本 / 问答看图）
        "ollama": _ollama_models(),
        "all_models": _all_models(),
        "ensemble": {
            "enabled": getattr(config, "ENABLE_ENSEMBLE", False),
            # ⚠️ ENSEMBLE_MODELS 每项是 (目录, 文件名[, 权重]) 三元组 ——
            #    早期写成 `for d, f in ...` 只解 2 个值，枚举到第三项就 ValueError 500。
            #    这里按"目录/文件/权重"完整解析，权重缺省视为 1.0。
            "models": [
                {
                    "dir": it[0],
                    "file": it[1] if len(it) > 1 else "",
                    "weight": it[2] if len(it) > 2 else 1.0,
                    "label": f"{it[0]}/{it[1]}" if len(it) > 1 else str(it[0]),
                }
                for it in (getattr(config, "ENSEMBLE_MODELS", []) or [])
            ],
            "threshold": getattr(config, "ENSEMBLE_THRESHOLD", None),
        },
        "database": database_info,
        "storage": {"disk": disk, "uploads": uploads},
        "config": {
            "use_onnx": getattr(config, "USE_ONNX", False),
            "type_predict": getattr(config, "ENABLE_TYPE_PREDICT", False),
            "max_upload_mb": getattr(config, "MAX_UPLOAD_MB", 0),
            "allowed_ext": sorted(getattr(config, "ALLOWED_EXT", [])),
            "threshold_presets": getattr(config, "THRESHOLD_PRESETS", {}),
        },
    }


def _human_uptime(sec: float) -> str:
    s = int(sec)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if d:
        return f"{d}天{h}小时{m}分"
    if h:
        return f"{h}小时{m}分"
    return f"{m}分{s}秒"


# ==================== 5. 操作日志（审计） ====================
@router.get("/logs", summary="操作日志列表")
def admin_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None, description="动作筛选，如 user.role"),
    admin_id: Optional[int] = Query(None, description="按操作者筛选"),
    target_type: Optional[str] = Query(None, description="目标类型：user / record"),
    keyword: Optional[str] = Query(None, description="关键词（操作者/目标/详情/路径）"),
    admin=Depends(get_current_admin),
):
    """管理员操作日志（倒序分页）。记录由中间件自动落库，管理员无法关闭。"""
    rows, total = database.list_admin_logs(
        limit=limit, offset=offset, action=action, admin_id=admin_id,
        target_type=target_type, keyword=keyword,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": r["id"],
                "admin_id": r["admin_id"],
                "admin_name": r["admin_name"] or "（未知）",
                "action": r["action"],
                "action_label": action_label(r["action"]),
                "method": r["method"],
                "path": r["path"],
                "target_type": r["target_type"],
                "target_id": r["target_id"],
                "target_name": r["target_name"],
                "detail": r["detail"],
                "status_code": r["status_code"],
                "ok": 200 <= (r["status_code"] or 0) < 300,
                "ip": r["ip"],
                "elapsed_ms": round(r["elapsed_ms"] or 0, 1),
                "created_at": r["created_at"],
            }
            for r in rows
        ],
    }


@router.get("/logs/actions", summary="操作日志：可筛选的动作类型")
def admin_log_actions(admin=Depends(get_current_admin)):
    """返回出现过的动作类型及次数（供前端筛选下拉），并附带中文名。"""
    items = database.admin_log_actions()
    for it in items:
        it["label"] = action_label(it["action"])
    return {"items": items, "all_labels": ACTION_LABELS}


# ==================== 6. 模型管理与推理统计 ====================
@router.get("/model/stats", summary="模型推理统计")
def admin_model_stats(
    days: int = Query(14, ge=1, le=90, description="趋势天数"),
    admin=Depends(get_current_admin),
):
    """基于检测记录聚合的推理统计：耗时分布、每日趋势、判定分布。"""
    stats = database.infer_stats(days=days)

    # 模型与运行环境信息
    model_info = _model_status()
    type_info = _type_model_status()

    # 当前生效的配置（阈值、集成成员）
    presets = {}
    for k, v in (getattr(config, "THRESHOLD_PRESETS", {}) or {}).items():
        presets[k] = {"name": v.get("name", k), "value": v.get("value"),
                      "desc": v.get("desc", "")}

    ensemble = [
        {"name": n, "weight": w}
        for n, _f, w in (getattr(config, "ENSEMBLE_MODELS", []) or [])
    ]

    return {
        "stats": stats,
        "days": days,
        "model": model_info,
        "type_model": type_info,
        "runtime": {
            # 尺寸/设备等取自 Predictor.status()（真实运行值，不重复定义）
            "img_size": model_info.get("img_size") or model_info.get("input_size"),
            "device": model_info.get("device", ""),
            "backend": model_info.get("backend", ""),
            "load_ms": model_info.get("load_ms"),
            "load_error": model_info.get("load_error", "") or model_info.get("error", ""),
            # 集成与阈值取自 config
            "ensemble_enabled": getattr(config, "ENABLE_ENSEMBLE", False),
            "ensemble_members": ensemble,
            "threshold": getattr(config, "ENSEMBLE_THRESHOLD", None),
            "use_onnx": getattr(config, "USE_ONNX", False),
            "type_predict": getattr(config, "ENABLE_TYPE_PREDICT", False),
        },
        "presets": presets,
    }
