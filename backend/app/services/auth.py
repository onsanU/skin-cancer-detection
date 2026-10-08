#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户认证：密码哈希 + JWT 签发/校验"""

import hashlib
import hmac
import json
import os
import base64
import time
from typing import Optional

from .. import config, database


# ==================== 密码（PBKDF2，标准库，无额外依赖） ====================
def hash_password(password: str, salt: bytes = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256$120000${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expect = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk, expect)
    except Exception:
        return False


# ==================== JWT（HS256，手写实现，避免额外依赖） ====================
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_token(user_id: int, username: str, expires_minutes: int = None) -> str:
    exp_min = expires_minutes or config.ACCESS_TOKEN_EXPIRE_MINUTES
    header = {"alg": config.ALGORITHM, "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + exp_min * 60,
    }
    segs = [
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode()),
        _b64url_encode(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segs).encode()
    sig = hmac.new(config.SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
    segs.append(_b64url_encode(sig))
    return ".".join(segs)


def decode_token(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        signing_input = f"{parts[0]}.{parts[1]}".encode()
        expect = hmac.new(config.SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expect, _b64url_decode(parts[2])):
            return None
        payload = json.loads(_b64url_decode(parts[1]))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


# ==================== 认证流程 ====================
def register(username: str, email: str, password: str, full_name: str = ""):
    """注册。返回 (user_id, error)

    首个注册账号自动成为管理员（role=admin），与其他项目账号体系保持一致。
    """
    if len(username) < 3:
        return None, "用户名至少3个字符"
    if len(password) < 6:
        return None, "密码至少6个字符"
    if database.get_user_by_username(username):
        return None, "用户名已被注册"
    if database.get_user_by_email(email):
        return None, "邮箱已被注册"
    # 无任何用户 → 首个注册者即管理员
    role = "admin" if database.count_users() == 0 else "user"
    uid = database.create_user_ext(
        username, email, hash_password(password), full_name, role
    )
    return uid, None


def login(username: str, password: str):
    """登录。返回 (token, user_row, error)"""
    user = database.get_user_by_username(username) or database.get_user_by_email(username)
    if not user:
        return None, None, "用户名或密码错误"
    if not user["is_active"]:
        return None, None, "账号已被禁用"
    if not verify_password(password, user["password_hash"]):
        return None, None, "用户名或密码错误"
    token = create_token(user["id"], user["username"])
    return token, user, None


def user_from_token(token: str):
    payload = decode_token(token)
    if not payload:
        return None
    return database.get_user_by_id(int(payload["sub"]))
