#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库访问层（双模式：SQLite / MySQL）
------------------------------------------------------------
- DB_BACKEND = "sqlite"（默认）→ 纯标准库 sqlite3，零配置
- DB_BACKEND = "mysql"          → pymysql + db_mysql 适配层

业务函数只写一套 SQL（用 ? 占位符），由适配层自动翻译成 MySQL 方言。
⚠️ 与医小喵项目完全隔离：本项目只用 skin_cancer 库，绝不触碰 yixiaomiao 库。
"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

from . import config

# 根据配置选择后端（导入失败时回退 SQLite，保证服务总能起来）
USE_MYSQL = (config.DB_BACKEND == "mysql")
if USE_MYSQL:
    try:
        from . import db_mysql
        print(f"[DB] 后端 = MySQL ({config.MYSQL_HOST}:{config.MYSQL_PORT}/{config.MYSQL_DATABASE})", flush=True)
    except Exception as e:
        print(f"[DB] ⚠️ MySQL 适配层加载失败（{e}）→ 回退 SQLite", flush=True)
        USE_MYSQL = False

_local = threading.local()


def _connect():
    """建立底层连接（SQLite 或 MySQL）"""
    if USE_MYSQL:
        return db_mysql.connect()
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_conn():
    """线程内复用连接"""
    if getattr(_local, "conn", None) is None:
        _local.conn = _connect()
    return _local.conn


@contextmanager
def tx():
    """事务上下文（两种后端同语义）"""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    full_name     TEXT    DEFAULT '',
    role          TEXT    NOT NULL DEFAULT 'user',   -- user / admin
    created_at    TEXT    NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS records (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    filename       TEXT    NOT NULL,
    stored_path    TEXT    NOT NULL,
    label          TEXT    NOT NULL,           -- benign / malignant
    label_cn       TEXT    NOT NULL,
    probability    REAL    NOT NULL,           -- 判定类别的置信度
    malignant_prob REAL    NOT NULL,
    benign_prob    REAL    NOT NULL,
    threshold      REAL    NOT NULL DEFAULT 0.5,
    infer_ms       REAL    NOT NULL DEFAULT 0,
    note           TEXT    DEFAULT '',
    created_at     TEXT    NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_records_user   ON records(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_records_label  ON records(label);

-- 管理员操作日志（审计）：谁在何时对谁做了什么
--   由中间件自动落库，覆盖所有写操作（POST/PUT/PATCH/DELETE）的管理端请求
CREATE TABLE IF NOT EXISTS admin_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id    INTEGER,                   -- 操作者 ID（账号被删则为 NULL）
    admin_name  TEXT    NOT NULL DEFAULT '', -- 操作者用户名（冗余，防账号删除后无法追溯）
    action      TEXT    NOT NULL,          -- 语义化动作：user.role / user.password / user.active / ...
    method      TEXT    NOT NULL,          -- HTTP 方法
    path        TEXT    NOT NULL,          -- 请求路径
    target_type TEXT    DEFAULT '',        -- user / record / system
    target_id   INTEGER,                   -- 目标对象 ID
    target_name TEXT    DEFAULT '',        -- 目标对象名称（用户名 / 文件名）
    detail      TEXT    DEFAULT '',        -- 变更详情（如 "user → admin"）
    status_code INTEGER NOT NULL DEFAULT 0,
    ip          TEXT    DEFAULT '',
    elapsed_ms  REAL    NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL,
    FOREIGN KEY(admin_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_admin_logs_time   ON admin_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_logs_admin  ON admin_logs(admin_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_logs_action ON admin_logs(action);

-- 医疗问答：会话（每个用户可有多条会话）
CREATE TABLE IF NOT EXISTS chat_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    title      TEXT    NOT NULL DEFAULT '新对话',   -- 首条用户提问的前若干字
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 医疗问答：消息（含用户提问与 AI 回答）
CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role       TEXT    NOT NULL,          -- user / assistant
    content    TEXT    NOT NULL DEFAULT '',
    image_path TEXT    DEFAULT '',        -- 用户上传图片的磁盘路径（无图为空）
    model      TEXT    DEFAULT '',        -- 实际使用的模型名（便于排查）
    elapsed_ms REAL    NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL,
    FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_sess ON chat_messages(session_id, id);
"""


def init_db():
    """初始化数据库（幂等）+ 轻量迁移"""
    if USE_MYSQL:
        # MySQL：表结构由 backend/sql/02_create_tables.sql 建好（见该项目 README）
        # 这里只做「缺列补列」的轻量迁移，不重复建表（避免差异）
        with tx() as conn:
            _migrate(conn)
        print(f"[DB] 初始化完成: MySQL {config.MYSQL_HOST}:{config.MYSQL_PORT}/{config.MYSQL_DATABASE}", flush=True)
        return

    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    with tx() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
    print(f"[DB] 初始化完成: {config.DB_PATH}", flush=True)


def _columns(conn, table: str) -> set:
    """取表的列名集合（两种后端同语义）"""
    if USE_MYSQL:
        return db_mysql.table_columns(conn, table)
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"] for r in rows}


def _migrate(conn):
    """轻量迁移：缺列则 ALTER TABLE 补上（每次启动幂等执行）"""
    cols = _columns(conn, "users")

    # 2026-09-14 管理后台迭代：users 加 role（user / admin）
    if "role" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        print("[DB] 迁移: users.role 已添加", flush=True)

    # 补齐：如果没有管理员，把最早注册的账号提升为管理员
    row = conn.execute("SELECT COUNT(*) c FROM users WHERE role='admin'").fetchone()
    if row["c"] == 0:
        first = conn.execute(
            "SELECT id, username FROM users ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if first:
            conn.execute("UPDATE users SET role='admin' WHERE id=?", (first["id"],))
            print(f"[DB] 迁移: 首个账号 '{first['username']}' 已提升为管理员", flush=True)


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ==================== 用户 ====================
def create_user(username, email, password_hash, full_name="") -> int:
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO users(username,email,password_hash,full_name,created_at) "
            "VALUES(?,?,?,?,?)",
            (username, email, password_hash, full_name, now_iso()),
        )
        return cur.lastrowid


def get_user_by_username(username):
    return get_conn().execute(
        "SELECT * FROM users WHERE username=?", (username,)
    ).fetchone()


def get_user_by_email(email):
    return get_conn().execute(
        "SELECT * FROM users WHERE email=?", (email,)
    ).fetchone()


def get_user_by_id(uid):
    return get_conn().execute(
        "SELECT * FROM users WHERE id=?", (uid,)
    ).fetchone()


# ==================== 检测记录 ====================
def create_record(user_id, filename, stored_path, label, label_cn,
                  probability, malignant_prob, benign_prob,
                  threshold=0.5, infer_ms=0.0, note="") -> int:
    with tx() as conn:
        cur = conn.execute(
            """INSERT INTO records(user_id,filename,stored_path,label,label_cn,
                                   probability,malignant_prob,benign_prob,
                                   threshold,infer_ms,note,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, filename, stored_path, label, label_cn, probability,
             malignant_prob, benign_prob, threshold, infer_ms, note, now_iso()),
        )
        return cur.lastrowid


def list_records(user_id, limit=50, offset=0, label=None):
    sql = "SELECT * FROM records WHERE user_id=?"
    args = [user_id]
    if label:
        sql += " AND label=?"
        args.append(label)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    return get_conn().execute(sql, args).fetchall()


def count_records(user_id, label=None) -> int:
    sql = "SELECT COUNT(*) c FROM records WHERE user_id=?"
    args = [user_id]
    if label:
        sql += " AND label=?"
        args.append(label)
    return get_conn().execute(sql, args).fetchone()["c"]


def get_record(record_id, user_id):
    return get_conn().execute(
        "SELECT * FROM records WHERE id=? AND user_id=?", (record_id, user_id)
    ).fetchone()


def delete_record(record_id, user_id) -> bool:
    with tx() as conn:
        cur = conn.execute(
            "DELETE FROM records WHERE id=? AND user_id=?", (record_id, user_id)
        )
        return cur.rowcount > 0


def stats(user_id) -> dict:
    """用户检测统计"""
    rows = get_conn().execute(
        "SELECT label, COUNT(*) c FROM records WHERE user_id=? GROUP BY label",
        (user_id,),
    ).fetchall()
    d = {r["label"]: r["c"] for r in rows}
    total = sum(d.values())
    return {
        "total": total,
        "malignant": d.get("malignant", 0),
        "benign": d.get("benign", 0),
    }


# ==================== 账号管理（管理后台用，2026-09-14） ====================
def create_user_ext(username, email, password_hash, full_name="", role="user") -> int:
    """带角色的创建（注册时用：首个账号 role=admin）"""
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO users(username,email,password_hash,full_name,role,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (username, email, password_hash, full_name, role, now_iso()),
        )
        return cur.lastrowid


def count_users() -> int:
    return get_conn().execute("SELECT COUNT(*) c FROM users").fetchone()["c"]


def set_user_role(uid, role) -> bool:
    with tx() as conn:
        cur = conn.execute("UPDATE users SET role=? WHERE id=?", (role, uid))
        return cur.rowcount > 0


def set_user_password(uid, password_hash) -> bool:
    with tx() as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?", (password_hash, uid)
        )
        return cur.rowcount > 0


def set_user_active(uid, active: bool) -> bool:
    with tx() as conn:
        cur = conn.execute(
            "UPDATE users SET is_active=? WHERE id=?", (1 if active else 0, uid)
        )
        return cur.rowcount > 0


# ==================== 管理后台：全局查询 ====================
def admin_stats() -> dict:
    """全站统计数据（管理看板用）"""
    conn = get_conn()
    total_users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    total_records = conn.execute("SELECT COUNT(*) c FROM records").fetchone()["c"]

    by_label = {
        r["label"]: r["c"]
        for r in conn.execute(
            "SELECT label, COUNT(*) c FROM records GROUP BY label"
        ).fetchall()
    }
    # 今日 / 近7日
    today = datetime.now().strftime("%Y-%m-%d")
    today_new = conn.execute(
        "SELECT COUNT(*) c FROM records WHERE created_at LIKE ?", (today + "%",)
    ).fetchone()["c"]
    today_new_users = conn.execute(
        "SELECT COUNT(*) c FROM users WHERE created_at LIKE ?", (today + "%",)
    ).fetchone()["c"]

    # 近 7 天趋势（按日期分组）
    trend = conn.execute(
        """SELECT substr(created_at,1,10) d, COUNT(*) c
           FROM records
           WHERE created_at >= date('now','-6 days')
           GROUP BY d ORDER BY d"""
    ).fetchall()

    # 检测次数 Top 用户
    top_users = conn.execute(
        """SELECT u.username, u.role, COUNT(r.id) c
           FROM users u LEFT JOIN records r ON r.user_id = u.id
           GROUP BY u.id ORDER BY c DESC LIMIT 10"""
    ).fetchall()

    # 平均推理耗时
    avg_ms = conn.execute(
        "SELECT AVG(infer_ms) a FROM records WHERE infer_ms > 0"
    ).fetchone()["a"] or 0

    malignant = by_label.get("malignant", 0)
    return {
        "total_users": total_users,
        "total_records": total_records,
        "malignant": malignant,
        "benign": by_label.get("benign", 0),
        "malignant_rate": round(malignant / total_records * 100, 2) if total_records else 0,
        "today_records": today_new,
        "today_users": today_new_users,
        "avg_infer_ms": round(avg_ms, 1),
        "trend": [{"date": r["d"], "count": r["c"]} for r in trend],
        "top_users": [
            {"username": r["username"], "role": r["role"], "count": r["c"]}
            for r in top_users
        ],
    }


def admin_list_records(limit=20, offset=0, label=None, keyword=None,
                       username=None) -> tuple:
    """全站检测记录（带用户名），返回 (rows, total)"""
    where, args = [], []
    if label:
        where.append("r.label=?")
        args.append(label)
    if username:
        where.append("u.username=?")
        args.append(username)
    if keyword:
        where.append("(r.filename LIKE ? OR u.username LIKE ? OR r.note LIKE ?)")
        args += [f"%{keyword}%"] * 3
    w = ("WHERE " + " AND ".join(where)) if where else ""

    conn = get_conn()
    total = conn.execute(
        f"""SELECT COUNT(*) c FROM records r
            LEFT JOIN users u ON u.id = r.user_id {w}""", args
    ).fetchone()["c"]
    rows = conn.execute(
        f"""SELECT r.*, u.username, u.role
            FROM records r LEFT JOIN users u ON u.id = r.user_id
            {w} ORDER BY r.created_at DESC, r.id DESC LIMIT ? OFFSET ?""",
        args + [limit, offset],
    ).fetchall()
    return rows, total


def admin_get_record(record_id: int):
    return get_conn().execute(
        """SELECT r.*, u.username, u.role
           FROM records r LEFT JOIN users u ON u.id = r.user_id
           WHERE r.id=?""", (record_id,)
    ).fetchone()


def admin_delete_record(record_id: int) -> bool:
    with tx() as conn:
        cur = conn.execute("DELETE FROM records WHERE id=?", (record_id,))
        return cur.rowcount > 0


def admin_list_users(limit=20, offset=0, keyword=None, role=None) -> tuple:
    """用户列表（带检测数），返回 (rows, total)"""
    where, args = [], []
    if keyword:
        where.append("(u.username LIKE ? OR u.email LIKE ? OR u.full_name LIKE ?)")
        args += [f"%{keyword}%"] * 3
    if role:
        where.append("u.role=?")
        args.append(role)
    w = ("WHERE " + " AND ".join(where)) if where else ""

    conn = get_conn()
    total = conn.execute(f"SELECT COUNT(*) c FROM users u {w}", args).fetchone()["c"]
    rows = conn.execute(
        f"""SELECT u.id, u.username, u.email, u.full_name, u.role,
                   u.created_at, u.is_active,
                   COUNT(r.id) record_count,
                   SUM(CASE WHEN r.label='malignant' THEN 1 ELSE 0 END) malignant_count
            FROM users u LEFT JOIN records r ON r.user_id = u.id
            {w} GROUP BY u.id ORDER BY u.id ASC LIMIT ? OFFSET ?""",
        args + [limit, offset],
    ).fetchall()
    return rows, total


def admin_get_user(uid: int):
    return get_conn().execute(
        """SELECT u.*, COUNT(r.id) record_count
           FROM users u LEFT JOIN records r ON r.user_id = u.id
           WHERE u.id=? GROUP BY u.id""", (uid,)
    ).fetchone()


def count_admins() -> int:
    return get_conn().execute(
        "SELECT COUNT(*) c FROM users WHERE role='admin' AND is_active=1"
    ).fetchone()["c"]


def delete_user_records(uid: int) -> int:
    """删除某用户的全部检测记录，返回条数"""
    with tx() as conn:
        cur = conn.execute("DELETE FROM records WHERE user_id=?", (uid,))
        return cur.rowcount


# ==================== 管理员操作日志（审计） ====================
def add_admin_log(admin_id, admin_name, action, method, path, target_type="",
                  target_id=None, target_name="", detail="", status_code=0,
                  ip="", elapsed_ms=0.0) -> int:
    """写入一条管理员操作日志（失败不抛异常 —— 审计日志不应阻断业务）"""
    try:
        with tx() as conn:
            cur = conn.execute(
                """INSERT INTO admin_logs
                   (admin_id, admin_name, action, method, path, target_type,
                    target_id, target_name, detail, status_code, ip, elapsed_ms, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (admin_id, admin_name or "", action, method, path, target_type or "",
                 target_id, target_name or "", detail or "", status_code,
                 ip or "", elapsed_ms or 0.0, now_iso()),
            )
            return cur.lastrowid
    except Exception as e:  # noqa: BLE001
        print(f"[LOG] 写入操作日志失败: {e}", flush=True)
        return 0


def list_admin_logs(limit=50, offset=0, action=None, admin_id=None,
                    target_type=None, keyword=None):
    """查询操作日志（倒序，支持筛选），返回 (rows, total)"""
    w, args = [], []
    if action:
        w.append("action = ?")
        args.append(action)
    if admin_id:
        w.append("admin_id = ?")
        args.append(admin_id)
    if target_type:
        w.append("target_type = ?")
        args.append(target_type)
    if keyword:
        w.append("(admin_name LIKE ? OR target_name LIKE ? OR detail LIKE ? OR path LIKE ?)")
        kw = f"%{keyword}%"
        args += [kw, kw, kw, kw]
    where = f"WHERE {' AND '.join(w)}" if w else ""
    conn = get_conn()
    total = conn.execute(f"SELECT COUNT(*) c FROM admin_logs {where}", args).fetchone()["c"]
    rows = conn.execute(
        f"""SELECT * FROM admin_logs {where}
            ORDER BY id DESC LIMIT ? OFFSET ?""",
        args + [limit, offset],
    ).fetchall()
    return rows, total


def admin_log_actions() -> list:
    """出现过的动作类型（供前端筛选下拉）"""
    rows = get_conn().execute(
        "SELECT action, COUNT(*) c FROM admin_logs GROUP BY action ORDER BY c DESC"
    ).fetchall()
    return [{"action": r["action"], "count": r["c"]} for r in rows]


# ==================== 模型管理与推理统计 ====================
def infer_stats(days: int = 14) -> dict:
    """推理统计（基于 records 表聚合）：
       · 总量 / 平均耗时 / P50 / P95 / 最大
       · 按日期的检测量与平均耗时（近 N 天趋势）
       · 良恶性判定分布
    """
    conn = get_conn()
    row = conn.execute(
        """SELECT COUNT(*) c,
                  AVG(infer_ms) avg_ms,
                  MAX(infer_ms) max_ms,
                  MIN(infer_ms) min_ms
           FROM records WHERE infer_ms > 0"""
    ).fetchone()
    total = row["c"] or 0

    # 分位数：SQLite / MySQL 都没有通用 PERCENTILE，用偏移量取（数据量小，够用）
    p50 = p95 = 0.0
    if total:
        for pct, key in ((50, "p50"), (95, "p95")):
            off = max(0, int(total * pct / 100) - 1)
            r = conn.execute(
                "SELECT infer_ms FROM records WHERE infer_ms > 0 ORDER BY infer_ms ASC LIMIT 1 OFFSET ?",
                (off,),
            ).fetchone()
            if r:
                if key == "p50":
                    p50 = r["infer_ms"]
                else:
                    p95 = r["infer_ms"]

    # 每日趋势
    trend = conn.execute(
        """SELECT substr(created_at,1,10) d,
                  COUNT(*) c,
                  AVG(infer_ms) avg_ms
           FROM records
           WHERE created_at >= date('now', ?) AND infer_ms > 0
           GROUP BY d ORDER BY d""",
        (f"-{int(days)-1} days",),
    ).fetchall()

    # 判定分布
    dist = {
        r["label"]: r["c"]
        for r in conn.execute(
            "SELECT label, COUNT(*) c FROM records GROUP BY label"
        ).fetchall()
    }

    # 耗时直方图（按区间统计）
    buckets = [(0, 150), (150, 200), (200, 250), (250, 300), (300, 400), (400, 10**9)]
    hist = []
    for lo, hi in buckets:
        c = conn.execute(
            "SELECT COUNT(*) c FROM records WHERE infer_ms >= ? AND infer_ms < ?",
            (lo, hi),
        ).fetchone()["c"]
        label = f"{lo}-{hi}" if hi < 10**9 else f"{lo}+"
        hist.append({"range": label, "count": c})

    return {
        "total": total,
        "avg_ms": round(row["avg_ms"] or 0, 1),
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "min_ms": round(row["min_ms"] or 0, 1),
        "max_ms": round(row["max_ms"] or 0, 1),
        "trend": [
            {"date": r["d"], "count": r["c"], "avg_ms": round(r["avg_ms"] or 0, 1)}
            for r in trend
        ],
        "dist": {"malignant": dist.get("malignant", 0), "benign": dist.get("benign", 0)},
        "hist": hist,
    }


# ==================== 医疗问答（会话 + 消息） ====================
def create_chat_session(user_id: int, title: str = "新对话") -> int:
    """新建会话，返回 session_id"""
    now = now_iso()
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO chat_sessions (user_id, title, created_at, updated_at) VALUES (?,?,?,?)",
            (user_id, (title or "新对话")[:60], now, now),
        )
        return cur.lastrowid


def list_chat_sessions(user_id: int, limit: int = 50, offset: int = 0):
    """我的会话列表（按最近更新倒序）。limit 只影响【列表显示】，数据仍全量保留。"""
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(*) c FROM chat_sessions WHERE user_id=?", (user_id,)
    ).fetchone()["c"]
    rows = conn.execute(
        """SELECT s.*, (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id=s.id) msg_count
           FROM chat_sessions s WHERE s.user_id=?
           ORDER BY s.updated_at DESC, s.id DESC LIMIT ? OFFSET ?""",
        (user_id, limit, offset),
    ).fetchall()
    return rows, total


def get_chat_session(sid: int, user_id: int):
    """取单个会话（带归属校验，防越权）"""
    return get_conn().execute(
        "SELECT * FROM chat_sessions WHERE id=? AND user_id=?", (sid, user_id)
    ).fetchone()


def delete_chat_session(sid: int, user_id: int) -> int:
    """删除会话（消息由外键级联删除），返回被删的消息数"""
    with tx() as conn:
        n = conn.execute(
            "SELECT COUNT(*) c FROM chat_messages WHERE session_id=?", (sid,)
        ).fetchone()["c"]
        conn.execute("DELETE FROM chat_sessions WHERE id=? AND user_id=?", (sid, user_id))
        return n


def touch_chat_session(sid: int, title=None):
    """更新会话的 updated_at（可选同时改标题）"""
    with tx() as conn:
        if title:
            conn.execute(
                "UPDATE chat_sessions SET updated_at=?, title=? WHERE id=?",
                (now_iso(), title[:60], sid),
            )
        else:
            conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (now_iso(), sid))


def list_chat_messages(session_id: int, limit: int = 500):
    """会话内的消息（正序）"""
    return get_conn().execute(
        """SELECT * FROM chat_messages WHERE session_id=?
           ORDER BY id ASC LIMIT ?""",
        (session_id, limit),
    ).fetchall()


def add_chat_message(session_id: int, role: str, content: str,
                     image_path: str = "", model: str = "", elapsed_ms: float = 0.0) -> int:
    """追加一条消息，返回 message_id"""
    with tx() as conn:
        cur = conn.execute(
            """INSERT INTO chat_messages
               (session_id, role, content, image_path, model, elapsed_ms, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (session_id, role, content or "", image_path or "", model or "",
             elapsed_ms or 0.0, now_iso()),
        )
        return cur.lastrowid


def count_chat_stats(user_id: int) -> dict:
    """我的问答统计（会话数 / 消息数）"""
    conn = get_conn()
    sess = conn.execute(
        "SELECT COUNT(*) c FROM chat_sessions WHERE user_id=?", (user_id,)
    ).fetchone()["c"]
    msgs = conn.execute(
        """SELECT COUNT(*) c FROM chat_messages m
           JOIN chat_sessions s ON s.id = m.session_id WHERE s.user_id=?""",
        (user_id,),
    ).fetchone()["c"]
    return {"sessions": sess, "messages": msgs}


# ---------- 管理后台：问答（chat）全局查询 ----------
# ⚠️ 问答与图像检测是两套独立数据源：
#      · 图像 → records 表（有 label 良恶性）
#      · 问答 → chat_sessions / chat_messages（无良恶性，故不参与良恶性占比分母）
#    看板的「恶性占比」永远只用 records，避免分母混入问答导致占比失真。

# 趋势粒度 → SQLite 日期分组表达式
#   day   → 2026-09-18
#   week  → 2026-W37（strftime %W 为周序号）
#   month → 2026-09
# 图像与问答两张表都有 created_at 同名列，故共用同一套表达式。
_TREND_EXPR = {
    "day": "substr(created_at,1,10)",
    "week": "strftime('%Y-W%W', created_at)",
    "month": "substr(created_at,1,7)",
}


def _trend_since(grain: str) -> str:
    """趋势回溯窗口：日=近7天 / 周=近8周 / 月=近6月（给足刻度但不至于太挤）"""
    return {"day": "-6 days", "week": "-56 days", "month": "-180 days"}.get(grain, "-6 days")


def admin_chat_stats() -> dict:
    """问答全局统计：会话数 / 消息数 / 今日新增 / 平均回答耗时 / Top 提问用户"""
    conn = get_conn()
    sessions = conn.execute("SELECT COUNT(*) c FROM chat_sessions").fetchone()["c"]
    messages = conn.execute("SELECT COUNT(*) c FROM chat_messages").fetchone()["c"]
    # 只统计用户提问（role='user'），AI 回答条数与之 1:1，统计提问更符合"问答次数"直觉
    questions = conn.execute(
        "SELECT COUNT(*) c FROM chat_messages WHERE role='user'"
    ).fetchone()["c"]

    today = datetime.now().strftime("%Y-%m-%d")
    today_sessions = conn.execute(
        "SELECT COUNT(*) c FROM chat_sessions WHERE created_at LIKE ?", (today + "%",)
    ).fetchone()["c"]

    avg_ms = conn.execute(
        """SELECT AVG(elapsed_ms) a FROM chat_messages
           WHERE role='assistant' AND elapsed_ms > 0"""
    ).fetchone()["a"] or 0

    top = conn.execute(
        """SELECT u.username, u.role, COUNT(s.id) c
           FROM users u JOIN chat_sessions s ON s.user_id = u.id
           GROUP BY u.id ORDER BY c DESC, u.username LIMIT 10"""
    ).fetchall()

    return {
        "sessions": sessions,
        "messages": messages,
        "questions": questions,
        "today_sessions": today_sessions,
        "avg_reply_ms": round(avg_ms, 1),
        "top_users": [
            {"username": r["username"], "role": r["role"], "count": r["c"]} for r in top
        ],
    }


def admin_trend(grain: str = "day", source: str = "record") -> list:
    """趋势序列（看板折线图用）

    grain  : day / week / month —— 日/周/月粒度
    source : record / chat / all —— 图像检测 / 问答 / 全部合计
    返回按时间升序的 [{date, count}]，缺失区间不补零（前端按序列画点）
    """
    grain = grain if grain in ("day", "week", "month") else "day"
    source = source if source in ("record", "chat", "all") else "record"
    since = _trend_since(grain)
    conn = get_conn()

    def series(expr: str, table: str) -> dict:
        rows = conn.execute(
            f"""SELECT {expr} d, COUNT(*) c FROM {table}
                WHERE created_at >= date('now', ?) GROUP BY d""", (since,)
        ).fetchall()
        return {r["d"]: r["c"] for r in rows}

    if source == "record":
        merged = series(_TREND_EXPR[grain], "records")
    elif source == "chat":
        # 问答按「会话」计（一个会话 = 一次问答行为），与看板卡片口径一致
        merged = series(_TREND_EXPR[grain], "chat_sessions")
    else:
        merged = series(_TREND_EXPR[grain], "records")
        for k, v in series(_TREND_EXPR[grain], "chat_sessions").items():
            merged[k] = merged.get(k, 0) + v

    return [{"date": k, "count": merged[k]} for k in sorted(merged)]


def admin_list_chats(limit=20, offset=0, keyword=None, username=None) -> tuple:
    """全站问答会话列表（带用户名与消息数），返回 (rows, total)"""
    where, args = [], []
    if username:
        where.append("u.username=?")
        args.append(username)
    if keyword:
        where.append("(s.title LIKE ? OR u.username LIKE ?)")
        args += ["%" + keyword + "%"] * 2
    w = ("WHERE " + " AND ".join(where)) if where else ""

    conn = get_conn()
    total = conn.execute(
        f"SELECT COUNT(*) c FROM chat_sessions s JOIN users u ON u.id = s.user_id {w}",
        args,
    ).fetchone()["c"]
    rows = conn.execute(
        f"""SELECT s.*, u.username,
                   (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id=s.id) msg_count,
                   (SELECT m.content FROM chat_messages m WHERE m.session_id=s.id
                      AND m.role='user' ORDER BY m.id LIMIT 1) first_q
            FROM chat_sessions s JOIN users u ON u.id = s.user_id
            {w} ORDER BY s.updated_at DESC LIMIT ? OFFSET ?""",
        args + [limit, offset],
    ).fetchall()
    return rows, total


def admin_get_chat(session_id: int):
    """问答会话详情（含全部消息）"""
    conn = get_conn()
    s = conn.execute(
        """SELECT s.*, u.username FROM chat_sessions s
           JOIN users u ON u.id = s.user_id WHERE s.id=?""", (session_id,)
    ).fetchone()
    if not s:
        return None
    msgs = conn.execute(
        "SELECT * FROM chat_messages WHERE session_id=? ORDER BY id", (session_id,)
    ).fetchall()
    return {"session": s, "messages": msgs}


def admin_delete_chat(session_id: int) -> int:
    """删除问答会话（消息由外键 CASCADE 一起删），返回被删的消息数"""
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) c FROM chat_messages WHERE session_id=?", (session_id,)
    ).fetchone()["c"]
    cur = conn.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
    conn.commit()
    return n if cur.rowcount > 0 else 0
