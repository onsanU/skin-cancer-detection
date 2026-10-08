#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MySQL 适配层（db_mysql.py）
------------------------------------------------------------
目的：让上层业务代码（database.py 的 ~30 个函数）**一行都不用改**，
      就能在 SQLite / MySQL 之间切换。

做法：包装 pymysql，暴露与 sqlite3 相同的调用接口：
  - conn.execute(sql, args) → 返回 Cursor（支持 .fetchone() / .fetchall() / .lastrowid / .rowcount）
  - 行对象支持 r["列名"] 取值（DictCursor）
  - ? 占位符自动转 %s
  - 自动把 SQLite 方言翻译成 MySQL（DATE('now') / substr / LIKE 时间等）
  - executescript 拆成多条执行
  - PRAGMA table_info 用 information_schema 模拟

⚠️ 已知差异（已在翻译层处理）：
  - SQLite 返回 TEXT 时间，MySQL 返回 datetime → 统一由调用方 strftime 处理
    （本项目 auth/records 层已做 str() 兜底；此处额外提供 _norm 归一化）
"""

import re
import threading

import pymysql
from pymysql.cursors import DictCursor

from . import config

_local = threading.local()

# ============================================================
#  SQL 方言翻译（SQLite → MySQL）
# ============================================================
_RE_INSERT_OR_IGNORE = re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.I)

def _translate(sql: str) -> str:
    """把 SQLite 方言的 SQL 翻译成 MySQL 可执行的 SQL"""
    s = sql

    # 1) 占位符 ? → %s（注意不能碰到字符串里的 ?，本项目 SQL 无此情况）
    s = s.replace("?", "%s")

    # 2) 建表相关（init_db 只会在 sqlite 分支执行，这里兜底兼容）
    s = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", "INT AUTO_INCREMENT PRIMARY KEY", s, flags=re.I)
    s = re.sub(r"\bAUTOINCREMENT\b", "AUTO_INCREMENT", s, flags=re.I)
    s = re.sub(r"\bREAL\b", "DOUBLE", s, flags=re.I)
    s = re.sub(r"\bTEXT\s+NOT\s+NULL\s+UNIQUE\b", "VARCHAR(191) NOT NULL UNIQUE", s, flags=re.I)
    if re.search(r"\bCREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\b", s, re.I):
        # MySQL 的 CREATE INDEX 不支持 IF NOT EXISTS，交给调用方 try/except
        pass

    # 3) 时间函数
    s = re.sub(r"date\('now',\s*'-(\d+)\s*days?'\)", r"DATE_SUB(CURDATE(), INTERVAL \1 DAY)", s, flags=re.I)
    s = re.sub(r"date\('now'\)", "CURDATE()", s, flags=re.I)
    s = re.sub(r"datetime\('now'\)", "NOW()", s, flags=re.I)

    # 4) substr(created_at,1,10) → DATE(created_at)（仅用于日期分组）
    s = re.sub(r"substr\(\s*([a-zA-Z_.]+)\s*,\s*1\s*,\s*10\s*\)", r"DATE(\1)", s, flags=re.I)

    # 5) created_at LIKE 'YYYY-MM-DD%' → DATE(created_at) = 'YYYY-MM-DD'
    s = re.sub(
        r"([a-zA-Z_.]+)\s+LIKE\s+%s",
        lambda m: "DATE(%s) = %%s" % m.group(1),
        s, flags=re.I,
    ) if False else s  # 交给下方参数改写，见 Database.execute

    # 6) GROUP BY 别名兼容（MySQL 默认允许，无需处理）
    return s


def _fix_like_date(sql: str, args):
    """
    把 `xxx LIKE %s` 且参数形如 '2026-09-15%' 的模式，
    改写为 `DATE(xxx) = %s` 且参数去掉尾部 %。
    返回 (新sql, 新args)
    """
    if not args:
        return sql, args
    new_args = list(args)
    m = re.findall(r"([a-zA-Z_.]+)\s+LIKE\s+%s", sql)
    if m:
        for i, a in enumerate(new_args):
            if isinstance(a, str) and a.endswith("%") and len(a) == 11 and a[4] == "-" and a[7] == "-":
                new_args[i] = a[:-1]  # 去掉 %
                # 逐一替换 LIKE %s → DATE(col) = %s
                sql = re.sub(
                    r"([a-zA-Z_.]+)\s+LIKE\s+%s",
                    lambda mm: "DATE(%s) = %%s" % mm.group(1),
                    sql, count=1, flags=re.I,
                )
    return sql, tuple(new_args)


# ============================================================
#  行对象：支持 r["列名"] 与 dict(r) / 键访问
#  额外：把 datetime / date 自动转成字符串，
#        与 SQLite 版返回 TEXT 的行为保持一致（避免上层 JSON 序列化炸掉）
# ============================================================
def _norm(v):
    if isinstance(v, str):
        return v
    try:
        from datetime import datetime, date
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(v, date):
            return v.strftime("%Y-%m-%d")
    except Exception:
        pass
    return v


class Row(dict):
    """模拟 sqlite3.Row：支持 r["k"]；额外提供 .keys() 等 dict 能力"""
    def __init__(self, mapping):
        super().__init__({k: _norm(v) for k, v in mapping.items()})

    def __getitem__(self, k):
        if isinstance(k, int):
            return list(self.values())[k]
        return dict.__getitem__(self, k)

    def keys(self):
        return list(dict.keys(self))


# ============================================================
#  游标包装
# ============================================================
class Cursor:
    def __init__(self, cur, conn_wrapper):
        self._cur = cur
        self._conn = conn_wrapper

    def _wrap(self, rows):
        if rows is None:
            return None
        if isinstance(rows, dict):
            return Row(rows)
        return [Row(r) for r in rows]

    def fetchone(self):
        return self._wrap(self._cur.fetchone())

    def fetchall(self):
        return self._wrap(self._cur.fetchall()) or []

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    def __iter__(self):
        return iter(self.fetchall())


# ============================================================
#  连接包装（模拟 sqlite3.Connection）
# ============================================================
class Connection:
    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, args=()):
        sql = _translate(sql)
        sql, args = _fix_like_date(sql, list(args) if args else [])
        cur = self._raw.cursor()
        try:
            cur.execute(sql, args or None)
        except Exception as e:
            # 建表/索引重复等幂等场景由调用方处理
            raise e
        return Cursor(cur, self)

    def executescript(self, script: str):
        """把多语句脚本按 ; 拆开逐条执行（MySQL 不支持一次多语句）"""
        stmts = [s.strip() for s in script.split(";") if s.strip()]
        for st in stmts:
            # 跳过纯注释
            if all(line.strip().startswith("--") or not line.strip() for line in st.split("\n")):
                continue
            try:
                self.execute(st)
            except Exception as e:
                if "already exists" in str(e).lower() or "Duplicate" in str(e):
                    continue
                raise

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        try:
            self._raw.close()
        except Exception:
            pass


# ============================================================
#  对外接口（与 sqlite3 对齐）
# ============================================================
def connect() -> Connection:
    raw = pymysql.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DATABASE,
        charset=config.MYSQL_CHARSET,
        cursorclass=DictCursor,
        autocommit=False,
        connect_timeout=8,
        read_timeout=30,
        write_timeout=30,
    )
    return Connection(raw)


def get_conn() -> Connection:
    """线程内复用连接（与 sqlite 版本同语义）"""
    if getattr(_local, "conn", None) is None:
        _local.conn = connect()
    return _local.conn


def table_columns(conn, table: str) -> set:
    """模拟 PRAGMA table_info(table)：返回列名集合"""
    cur = conn._raw.cursor()
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
        (config.MYSQL_DATABASE, table),
    )
    return {list(r.values())[0] for r in cur.fetchall()}
