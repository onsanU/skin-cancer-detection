# -*- coding: utf-8 -*-
"""医疗问答的 LLM 调用封装（Ollama）

模型分工（自动切换）：
  · 纯文本提问  → TEXT_MODEL（qwen3.5:4b-med3，5000 条医疗数据微调，医疗知识更扎实）
  · 带图片提问  → VISION_MODEL（qwen2.5vl:3b，支持读图）

设计要点：
  · 单次调用超时保护（默认 180s），失败返回可读提示而不是抛异常打断对话
  · qwen3 系默认会"长思考"，用 think=False 关闭，避免耗时与预算失控
  · num_predict 限制输出长度，防止极端情况下生成过长内容
  · 不依赖 langchain —— 直接用 urllib 调 Ollama HTTP 接口，少一层依赖更稳
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request

OLLAMA_URL = "http://127.0.0.1:11434"
TEXT_MODEL = "qwen3.5:4b-med3"      # 医疗微调版（与医小咪同款）
VISION_MODEL = "qwen2.5vl:3b"       # 看图问答

# 医疗系统提示词：约束范围 + 强制免责 + 遇危险信号提示就医
SYSTEM_PROMPT = """你是"皮肤健康助手"，为皮肤癌图像检测系统的用户提供健康科普与就医指引。

回答要求：
1. 用通俗易懂的中文，条理清晰，必要时分点说明
2. 只做健康科普与就医建议，不做确诊；涉及具体病情时提示"需由医生面诊判断"
3. 不给具体药物名称与剂量，只写"遵医嘱用药"
4. 遇到用户描述的危险信号（快速增大、破溃出血、颜色不均、边缘不规则、久不愈合等），必须明确提示尽快就医
5. 不编造医学事实；不确定的内容就说"这点建议咨询医生"
6. 回答简洁，控制在 400 字以内，除非用户要求展开

注意：本系统的图像检测结果仅供参考，不构成医疗诊断。"""


def _post_json(url: str, payload: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ollama_ready(timeout: int = 3) -> dict:
    """探测 Ollama 是否可用 + 已安装的模型列表（供前端提示）"""
    try:
        with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = [m.get("name", "") for m in data.get("models", [])]
        return {
            "ok": True,
            "models": names,
            "text_model_ready": any(TEXT_MODEL.split(":")[0] in n for n in names),
            "vision_model_ready": any(VISION_MODEL.split(":")[0] in n for n in names),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "models": [],
                "text_model_ready": False, "vision_model_ready": False}


def _image_to_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def chat(question: str, image_path: str = "", history: list | None = None,
         timeout: int = 180) -> dict:
    """向模型提问。

    @param question    用户提问文本
    @param image_path  可选：本地图片路径（有则走视觉模型）
    @param history     可选：历史消息 [{"role":"user"/"assistant","content":"..."}]
    @returns {"ok":bool, "text":str, "model":str, "elapsed_ms":float, "error":str}
    """
    use_vision = bool(image_path)
    model = VISION_MODEL if use_vision else TEXT_MODEL

    # 组装消息：系统提示 + 历史（最多带最近 10 条，避免上下文过长变慢）+ 本次提问
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in (history or [])[-10:]:
        role = h.get("role")
        content = h.get("content") or ""
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})

    user_msg = {"role": "user", "content": question or ""}
    if use_vision:
        try:
            user_msg["images"] = [_image_to_b64(image_path)]
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "text": "", "model": model, "elapsed_ms": 0,
                    "error": f"图片读取失败：{e}"}
    msgs.append(user_msg)

    payload = {
        "model": model,
        "messages": msgs,
        "stream": False,
        "options": {
            "temperature": 0.3,      # 医疗问答：偏低温度，减少发挥
            "num_predict": 900,
        },
        # qwen3 系默认长思考，关掉以控制耗时（医小咪 OCR 通道踩过的坑）
        "think": False,
    }

    t0 = time.time()
    try:
        data = _post_json(OLLAMA_URL + "/api/chat", payload, timeout=timeout)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:200]
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "text": "", "model": model,
                "elapsed_ms": (time.time() - t0) * 1000,
                "error": f"模型调用失败（HTTP {e.code}）{detail}"}
    except urllib.error.URLError as e:
        return {"ok": False, "text": "", "model": model,
                "elapsed_ms": (time.time() - t0) * 1000,
                "error": f"无法连接模型服务（请确认 Ollama 已启动）：{e.reason}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "text": "", "model": model,
                "elapsed_ms": (time.time() - t0) * 1000, "error": str(e)}

    if "error" in data:
        return {"ok": False, "text": "", "model": model,
                "elapsed_ms": (time.time() - t0) * 1000, "error": str(data["error"])}

    text = ((data.get("message") or {}).get("content") or "").strip()
    if not text:
        return {"ok": False, "text": "", "model": model,
                "elapsed_ms": (time.time() - t0) * 1000, "error": "模型返回了空内容"}

    return {
        "ok": True,
        "text": text,
        "model": model,
        "elapsed_ms": round((time.time() - t0) * 1000, 1),
        "error": "",
    }
