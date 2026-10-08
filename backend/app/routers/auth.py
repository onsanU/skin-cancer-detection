#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户认证路由：注册 / 登录 / 当前用户"""

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr, Field
from typing import Optional

from .. import database
from ..services import auth as auth_svc

router = APIRouter(prefix="/api/auth", tags=["用户认证"])


# ---------- Schemas ----------
class RegisterReq(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    full_name: str = Field("", max_length=64, description="姓名（可选）")


class LoginReq(BaseModel):
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: str = "user"
    created_at: str


def _user_out(u) -> dict:
    # sqlite3.Row 没有 .get()，role 可能来自老连接（迁移前）→ 用 keys() 判断
    role = u["role"] if "role" in u.keys() else "user"
    return {
        "id": u["id"], "username": u["username"], "email": u["email"],
        "full_name": u["full_name"], "role": role,
        "created_at": u["created_at"],
    }


# ---------- 依赖：从 Authorization 头取当前用户 ----------
def get_current_user(authorization: str = Header(None, alias="Authorization")):
    if not authorization:
        raise HTTPException(401, "未提供认证信息，请先登录")
    token = authorization.replace("Bearer ", "").strip()
    user = auth_svc.user_from_token(token)
    if not user:
        raise HTTPException(401, "登录已过期或凭证无效，请重新登录")
    return user


def resolve_optional_user(authorization: str = Header(None, alias="Authorization")):
    """可选登录（游客也能用检测，但记录不保存）"""
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "").strip()
    return auth_svc.user_from_token(token)


def get_current_admin(user=Depends(get_current_user)):
    """管理员守卫：非 admin 角色一律 403（管理后台专用）"""
    if (user["role"] if "role" in user.keys() else "user") != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


# ---------- 接口 ----------
@router.post("/register", summary="用户注册")
def register(req: RegisterReq):
    uid, err = auth_svc.register(req.username, req.email, req.password, req.full_name)
    if err:
        raise HTTPException(400, err)
    user = database.get_user_by_id(uid)
    token = auth_svc.create_token(user["id"], user["username"])
    return {"message": "注册成功", "token": token, "token_type": "bearer",
            "user": _user_out(user)}


@router.post("/login", summary="用户登录")
def login(req: LoginReq):
    token, user, err = auth_svc.login(req.username, req.password)
    if err:
        raise HTTPException(401, err)
    return {"message": "登录成功", "token": token, "token_type": "bearer",
            "user": _user_out(user)}


@router.get("/me", summary="获取当前用户信息")
def me(user=Depends(get_current_user)):
    st = database.stats(user["id"])
    u = _user_out(user)
    return {"user": u, "stats": st, "is_admin": u["role"] == "admin"}
