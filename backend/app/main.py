#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""皮肤癌图像检测系统 —— FastAPI 后端主入口"""

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, database
from .services.predictor import Predictor
from .routers import auth, predict, records


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动/关闭钩子"""
    print("=" * 70, flush=True)
    print("皮肤癌图像检测系统 - 后端服务启动中...", flush=True)
    print("=" * 70, flush=True)

    database.init_db()

    p = Predictor.get()          # 触发模型加载
    if p.ready:
        p.warmup()

    # 7 类类型模型（辅助，失败不影响主服务）
    try:
        from .services.type_classifier import TypeClassifier
        tc = TypeClassifier.get()
        if tc.ready:
            tc.warmup()
        print(f"[启动] 类型模型就绪={tc.ready}", flush=True)
    except Exception as e:
        print(f"[启动] 类型模型加载异常（不影响主功能）: {e}", flush=True)

    print(f"[启动] 模型就绪={p.ready} 设备={p.device}", flush=True)
    if p.is_ensemble:
        print(f"[启动] 推理模式=集成({len(p.ensemble)}模型) "
              f"默认阈值={getattr(config, 'ENSEMBLE_THRESHOLD', 0.51)}", flush=True)
    else:
        print(f"[启动] 推理模式=单模型 backend={p.backend}", flush=True)
    print(f"[启动] 上传目录={config.UPLOAD_DIR}", flush=True)
    print("[启动] API文档: http://127.0.0.1:8000/docs", flush=True)
    print("=" * 70, flush=True)
    yield
    print("[关闭] 服务已停止", flush=True)


app = FastAPI(
    title="皮肤癌图像检测系统 API",
    description=(
        "基于深度残差网络（ResNet50）的皮肤病变图像良恶性二分类服务。\n\n"
        "⚠️ 医疗免责声明：本系统仅作为皮肤健康自检的辅助工具，"
        "检测结果仅供参考，不能替代专业医生的诊断。"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS：允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = f"{(time.time()-t0)*1000:.1f}"
    return response


@app.middleware("http")
async def audit_admin_writes(request: Request, call_next):
    """管理端写操作自动落审计日志。

    两段式：路由里 mark_action() 塞语义 → 这里统一落库。
    未被标注的写操作按「方法+路径」推导兜底动作名，保证不漏记。
    日志写入失败绝不影响业务响应。
    """
    from .audit import AUDITED_METHODS, AUDITED_PREFIX, EXEMPT_PATHS, derive_action
    from .services.auth import decode_token          # 解令牌取身份；令牌无效/过期则身份留空（请求本身仍会记录）

    path = request.url.path
    need_audit = (
        request.method in AUDITED_METHODS
        and path.startswith(AUDITED_PREFIX)
        and path not in EXEMPT_PATHS
    )

    t0 = time.time()
    response = await call_next(request)

    if need_audit:
        try:
            elapsed = (time.time() - t0) * 1000
            # 操作者身份：从 Authorization 头解出（payload: sub=用户ID, username=用户名）
            admin_id, admin_name = None, ""
            auth = request.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                payload = decode_token(auth[7:].strip()) or {}
                admin_id = payload.get("sub") or payload.get("uid")
                admin_name = payload.get("username") or payload.get("name") or ""
                try:
                    admin_id = int(admin_id) if admin_id is not None else None
                except (TypeError, ValueError):
                    admin_id = None

            meta = getattr(request.state, "audit", None) or {}
            action = meta.get("action") or derive_action(request.method, path)

            database.add_admin_log(
                admin_id=admin_id,
                admin_name=admin_name,
                action=action,
                method=request.method,
                path=path,
                target_type=meta.get("target_type", ""),
                target_id=meta.get("target_id"),
                target_name=meta.get("target_name", ""),
                detail=meta.get("detail", ""),
                status_code=response.status_code,
                ip=(request.client.host if request.client else "") or "",
                elapsed_ms=elapsed,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[AUDIT] 审计日志记录失败: {e}", flush=True)

    return response


# ---------- 路由 ----------
app.include_router(auth.router)
app.include_router(predict.router)
app.include_router(records.router)
from .routers import chat as chat_router                # noqa: E402
app.include_router(chat_router.router)

# 管理后台 API（必须在下方根 mount 之前注册，否则 404）
from . import admin_api                                    # noqa: E402
app.include_router(admin_api.router, prefix="/admin/api")


@app.get("/api/health", tags=["系统"], summary="健康检查")
def health():
    """返回服务与模型状态"""
    p = Predictor.get()
    return {
        "status": "ok",
        "service": "皮肤癌图像检测系统",
        "version": "1.0.0",
        "model": p.status(),
        "disclaimer": config.DISCLAIMER,
    }


@app.get("/", tags=["系统"], summary="服务信息")
def root():
    return {
        "service": "皮肤癌图像检测系统 API",
        "docs": "/docs",
        "health": "/api/health",
        "message": "喵~ 服务运行中 (=^･ω･^=)",
    }


# ---------- 静态文件（前端构建产物，若存在） ----------
# 管理后台（AdminLTE 纯静态模板，路径必须在下方根挂载之前）
_admin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "admin")
_admin_dir = os.path.abspath(_admin_dir)
if os.path.isdir(_admin_dir):
    class _AdminStatic(StaticFiles):
        """管理后台静态文件：禁用缓存。

        ⚠️ 踩坑：默认 StaticFiles 不带 Cache-Control，浏览器会按默认策略缓存
        admin.js / *.html，导致改了菜单/页面后用户看到的还是旧版（必须手动强刷）。
        后台是内部工具、文件体积小，直接 no-cache 最省心。
        （仅对 vendor/ 下的第三方库放行长期缓存，减少重复下载）
        """

        def file_response(self, full_path, stat_result, scope, status_code=200):
            resp = super().file_response(full_path, stat_result, scope, status_code)
            # vendor/ 下是第三方库（bootstrap/adminlte），可长期缓存；其余禁缓存
            p = str(full_path).replace("\\", "/")
            if "/vendor/" in p or p.startswith("vendor/"):
                resp.headers["Cache-Control"] = "public, max-age=604800"
            else:
                resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                resp.headers["Pragma"] = "no-cache"
                resp.headers["Expires"] = "0"
            return resp

    app.mount("/admin", _AdminStatic(directory=_admin_dir, html=True), name="admin")
    print(f"[启动] 已挂载管理后台: /admin -> {_admin_dir}（已禁用缓存）", flush=True)

_frontend_dist = os.path.join(config.PROJ_ROOT, "frontend", "dist")
if os.path.isdir(_frontend_dist):
    # SPA 前端：静态资源用 StaticFiles，深链接（/app/login、/app/detect）回退到 index.html
    # ⚠️ 直接 mount StaticFiles 会让深链接 404 —— React Router 的路径在后端没有对应文件
    from fastapi.responses import FileResponse
    _index_html = os.path.join(_frontend_dist, "index.html")

    def _no_cache(resp):
        """给 index.html 打上禁用缓存的响应头。

        ⚠️ 必要性：index.html 本身没有内容哈希，浏览器默认会强缓存它。
        一旦用户缓存了旧版 index.html，它引用的旧 assets 就会一直生效，
        即使 dist 已重新构建、页面结构已更新，用户看到的仍是老界面
        （典型症状：登录页 header 布局错乱、按钮位置不对）。
        assets 带内容哈希无需处理，只要保证 index.html 每次回源即可。
        """
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    class _HashedAssets(StaticFiles):
        """assets 目录：文件名带内容哈希，可长期缓存。"""

        def file_response(self, *args, **kwargs):
            resp = super().file_response(*args, **kwargs)
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return resp

    app.mount(
        "/app/assets",
        _HashedAssets(directory=os.path.join(_frontend_dist, "assets")),
        name="frontend-assets",
    )

    @app.get("/app", include_in_schema=False)
    @app.get("/app/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str = ""):
        """SPA fallback：非资源请求一律返回 index.html，交给前端路由处理"""
        candidate = os.path.join(_frontend_dist, full_path)
        # 真实存在的静态文件（favicon、图片等）直接返回
        if full_path and os.path.isfile(candidate):
            return _no_cache(FileResponse(candidate))
        if os.path.isfile(_index_html):
            return _no_cache(FileResponse(_index_html))
        return {"detail": "前端未构建：请在 frontend/ 执行 npm run build"}

    print(f"[启动] 已挂载前端静态文件: /app (SPA fallback) -> {_frontend_dist}", flush=True)

