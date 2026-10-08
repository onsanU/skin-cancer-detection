#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""医疗问答路由

接口：
  GET    /api/chat/status                模型服务状态（Ollama 是否就绪）
  POST   /api/chat/sessions              新建会话
  GET    /api/chat/sessions              我的会话列表（分页）
  GET    /api/chat/sessions/{sid}        会话详情 + 消息
  DELETE /api/chat/sessions/{sid}        删除会话
  POST   /api/chat/send                  发消息（文本/图片）→ 得分与 AI 回答
"""
import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import config, database
from ..routers.auth import get_current_user
from ..services import llm

router = APIRouter(prefix="/api/chat", tags=["医疗问答"])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MAX_IMAGE_MB = 10


# ---------- Schemas ----------
class SessionReq(BaseModel):
    title: str = Field("新对话", max_length=60, description="会话标题（可选）")


class SendReq(BaseModel):
    session_id: Optional[int] = Field(None, description="不传则自动新建会话")
    question: str = Field("", max_length=2000, description="提问内容")


def _msg_out(r, with_image: bool = True) -> dict:
    return {
        "id": r["id"],
        "role": r["role"],
        "content": r["content"],
        "has_image": bool(r["image_path"]),
        "image_url": (f"/api/chat/image/{os.path.basename(r['image_path'])}"
                      if with_image and r["image_path"] else None),
        "model": r["model"] or "",
        "elapsed_ms": round(r["elapsed_ms"] or 0, 1),
        "created_at": r["created_at"],
    }


def _session_out(r) -> dict:
    keys = r.keys()
    return {
        "id": r["id"],
        "title": r["title"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "msg_count": r["msg_count"] if "msg_count" in keys else None,
    }


# ==================== 状态 ====================
@router.get("/status", summary="问答模型服务状态")
def chat_status():
    """前端用来判断模型是否就绪（Ollama 未启动时给出提示，而不是等超时）"""
    st = llm.ollama_ready()
    return {
        **st,
        "text_model": llm.TEXT_MODEL,
        "vision_model": llm.VISION_MODEL,
        "disclaimer": "AI 回答仅供参考，不构成医疗诊断；如症状加重请及时就医。",
    }


# ==================== 会话 ====================
@router.post("/sessions", summary="新建会话")
def create_session(req: SessionReq = None, user=Depends(get_current_user)):
    title = (req.title if req else "新对话") or "新对话"
    sid = database.create_chat_session(user["id"], title)
    s = database.get_chat_session(sid, user["id"])
    return {"session": _session_out(s)}


@router.get("/sessions", summary="我的会话列表")
def list_sessions(limit: int = Query(50, ge=1, le=200),
                  offset: int = Query(0, ge=0),
                  user=Depends(get_current_user)):
    """limit 仅限制【列表展示条数】，历史数据不会删除。"""
    rows, total = database.list_chat_sessions(user["id"], limit=limit, offset=offset)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_session_out(r) for r in rows],
        "stats": database.count_chat_stats(user["id"]),
    }


@router.get("/sessions/{sid}", summary="会话详情（含消息）")
def session_detail(sid: int, user=Depends(get_current_user)):
    s = database.get_chat_session(sid, user["id"])
    if not s:
        raise HTTPException(404, "会话不存在")
    msgs = database.list_chat_messages(sid)
    return {"session": _session_out(s), "messages": [_msg_out(m) for m in msgs]}


@router.delete("/sessions/{sid}", summary="删除会话")
def delete_session(sid: int, user=Depends(get_current_user)):
    s = database.get_chat_session(sid, user["id"])
    if not s:
        raise HTTPException(404, "会话不存在")
    # 顺带删除该会话的图片文件
    msgs = database.list_chat_messages(sid)
    for m in msgs:
        p = m["image_path"]
        if p:
            try:
                if os.path.isfile(p):
                    os.remove(p)
            except Exception:  # noqa: BLE001
                pass
    n = database.delete_chat_session(sid, user["id"])
    return {"deleted": True, "messages": n, "id": sid}


# ==================== 图片 ====================
def _chat_img_dir() -> str:
    """问答图片目录：backend/uploads/chat（与检测上传图同级，便于统一清理）"""
    d = os.path.join(config.UPLOAD_DIR, "chat")
    os.makedirs(d, exist_ok=True)
    return d


@router.get("/image/{name}", summary="获取问答上传的图片")
def get_chat_image(name: str, user=Depends(get_current_user)):
    """只允许按文件名读取 chat 目录下的图片，防路径穿越"""
    safe = os.path.basename(name)
    path = os.path.join(_chat_img_dir(), safe)
    if not os.path.isfile(path):
        raise HTTPException(404, "图片不存在")
    return FileResponse(path)


# ==================== 发消息 ====================
@router.post("/send", summary="发送提问（支持图片）")
def send_message(
    question: str = Form(""),
    session_id: Optional[int] = Form(None),
    image: Optional[UploadFile] = File(None),
    user=Depends(get_current_user),
):
    """发一条提问 → 调模型 → 存两侧消息 → 返回 AI 回答。

    图片可选：带图走视觉模型，纯文本走医疗微调模型。
    """
    question = (question or "").strip()
    has_image = image is not None and image.filename

    if not question and not has_image:
        raise HTTPException(400, "请输入问题或上传图片")
    if len(question) > 2000:
        raise HTTPException(400, "问题过长（上限 2000 字）")

    # 1) 会话：不存在则新建，并做归属校验
    if session_id:
        s = database.get_chat_session(session_id, user["id"])
        if not s:
            raise HTTPException(404, "会话不存在")
        sid = session_id
    else:
        title = (question[:20] or "图片提问") if (question or has_image) else "新对话"
        sid = database.create_chat_session(user["id"], title)

    # 2) 保存图片（可选）
    image_path = ""
    if has_image:
        ext = os.path.splitext(image.filename)[1].lower()
        if ext not in ALLOWED_EXT:
            raise HTTPException(400, f"图片格式不支持（允许 {'/'.join(sorted(ALLOWED_EXT))}）")
        raw = image.file.read()
        if len(raw) > MAX_IMAGE_MB * 1024 * 1024:
            raise HTTPException(400, f"图片过大（上限 {MAX_IMAGE_MB}MB）")
        fname = f"chat_{user['id']}_{int(time.time() * 1000)}{ext}"
        image_path = os.path.join(_chat_img_dir(), fname)
        with open(image_path, "wb") as f:
            f.write(raw)

    # 3) 存用户消息
    database.add_chat_message(sid, "user", question, image_path=image_path)

    # 4) 取历史（含刚才这条之前的上下文）→ 调模型
    hist_rows = database.list_chat_messages(sid)
    history = [{"role": m["role"], "content": m["content"]}
               for m in hist_rows[:-1] if m["content"]]

    result = llm.chat(question or "请帮我看看这张图片反映的皮肤情况。",
                      image_path=image_path, history=history)

    if not result["ok"]:
        # 模型失败：仍存一条 assistant 消息，让用户看到原因，且不丢上下文
        err_text = f"⚠️ {result.get('error') or '模型暂时不可用，请稍后重试。'}"
        database.add_chat_message(sid, "assistant", err_text,
                                  model=result.get("model", ""),
                                  elapsed_ms=result.get("elapsed_ms", 0))
        database.touch_chat_session(sid)
        return {
            "ok": False,
            "session_id": sid,
            "error": result.get("error"),
            "assistant": {"role": "assistant", "content": err_text},
        }

    # 5) 存 AI 回答 + 更新会话
    database.add_chat_message(sid, "assistant", result["text"],
                              model=result["model"], elapsed_ms=result["elapsed_ms"])
    # 首轮提问后把标题设为问题摘要（比"新对话"更有辨识度）
    s2 = database.get_chat_session(sid, user["id"])
    if s2 and s2["title"] in ("新对话", "") and question:
        database.touch_chat_session(sid, title=question[:20])
    else:
        database.touch_chat_session(sid)

    fresh = database.list_chat_messages(sid)
    return {
        "ok": True,
        "session_id": sid,
        "session": _session_out(database.get_chat_session(sid, user["id"])),
        "model": result["model"],
        "elapsed_ms": result["elapsed_ms"],
        "user": _msg_out(fresh[-2]) if len(fresh) >= 2 else None,
        "assistant": _msg_out(fresh[-1]),
    }
