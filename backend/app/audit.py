"""管理端操作审计：中间件（自动捕获）+ 业务标注（语义信息）

设计思路
--------
中间件只能看到「POST /admin/api/users/3/role → 200」这种技术信息，
拿不到业务语义（改的是谁、改成什么）。所以采用两段式：

  ① 路由里用 `mark_action(...)` 往 request.state 塞语义
  ② 中间件统一落库（含 IP / 状态码 / 耗时 / 操作者）

这样既不会漏掉任何一个写操作（中间件兜底），
又能让日志带上人类可读的含义（业务标注）。

用法：
    from ..audit import mark_action

    @router.post("/users/{user_id}/role")
    def admin_set_role(user_id: int, req: RoleReq, request: Request, admin=Depends(get_current_admin)):
        user = database.admin_get_user(user_id)
        mark_action(request, "user.role", target_type="user",
                    target_id=user_id, target_name=user["username"] if user else "",
                    detail=f"role: {old} → {req.role}")
        ...
"""
from __future__ import annotations

from fastapi import Request

# 动作 → 中文名（前端筛选下拉 / 表格展示用）
ACTION_LABELS = {
    "user.role": "调整用户角色",
    "user.password": "重置用户密码",
    "user.active": "启用/禁用账号",
    "user.records.clear": "清空用户记录",
    "record.delete": "删除检测记录",
    "chat.delete": "删除问答会话",
    "admin.login": "管理员登录",
    "admin.logout": "管理员登出",
    "system.config": "修改系统配置",
}

# 需要审计的 HTTP 方法（只记写操作；GET 类查询不记，避免噪音）
AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# 需要审计的路径前缀（仅管理端 API；前台业务不记）
AUDITED_PREFIX = "/admin/api"

# 永不审计的路径（登录接口单独在业务里记，避免记录密码字段；健康检查等噪音也排除）
EXEMPT_PATHS = {"/admin/api/health", "/admin/api/ping"}


def mark_action(request: Request, action: str, target_type: str = "",
                target_id=None, target_name: str = "", detail: str = "") -> None:
    """在路由里标注本次请求的业务语义（供中间件落库）。

    重复调用会覆盖前一次标注（以最后一次为准）。
    """
    try:
        request.state.audit = {
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "target_name": target_name or "",
            "detail": detail or "",
        }
    except Exception:  # pragma: no cover - state 不可写时静默跳过
        pass


def derive_action(method: str, path: str) -> str:
    """没被业务标注时，按「方法 + 路径」推导一个兜底动作名。

    保证任何写操作都有记录，不会因为漏标注而丢失审计线索。
    路径形如：
        /admin/api/users/3/role      → user.role
        /admin/api/records/12        → record.delete
        /admin/api/users/5/records   → user.records
    """
    p = path.replace("/admin/api", "", 1).strip("/")
    parts = [x for x in p.split("/") if x and not x.isdigit()]
    if not parts:
        return f"admin.{method.lower()}"

    # 单数化：users → user, records → record
    singular = {"users": "user", "records": "record", "logs": "log"}
    head = singular.get(parts[0], parts[0])

    # 路径里出现过的动作关键词（比 HTTP 方法更贴近业务语义）
    verbs = [x for x in parts[1:] if x in
             ("role", "password", "active", "records", "clear", "export", "stats")]
    if verbs:
        tail = ".".join(verbs)
        return f"{head}.{tail}"
    if len(parts) >= 2:
        return f"{head}.{parts[-1]}"
    return f"{head}.{method.lower()}"


def action_label(action: str) -> str:
    """动作的中文名（未知动作回退为原字符串）"""
    return ACTION_LABELS.get(action, action)
