#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQLite → MySQL 数据迁移（皮肤癌图像检测系统）
- 读 sqlite3（源，只读不改）
- 写 pymysql（目标，skin_cancer 库）
- 保持 id 不变（用显式 id 插入），迁移后校对行数与抽样内容
用法: ~/shixun-venv/bin/python migrate_sqlite_to_mysql.py [--host 172.30.160.1]
"""
import argparse, os, sqlite3, sys, subprocess

P = "/mnt/d/Project/JXprojiect/Hermes-project/project/皮肤癌图像系统"
SQLITE_DB = os.path.join(P, "backend/skin_cancer.db")

ap = argparse.ArgumentParser()
ap.add_argument("--host", default=None, help="MySQL 主机（默认自动取 WSL 网关）")
ap.add_argument("--port", type=int, default=3306)
ap.add_argument("--user", default="skin_cancer")
ap.add_argument("--password", default="skc123456")
ap.add_argument("--database", default="skin_cancer")
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()

if not args.host:
    gw = subprocess.run("ip route | grep default | awk '{print $3}'",
                        shell=True, capture_output=True, text=True).stdout.strip()
    args.host = gw or "172.30.160.1"
print("目标 MySQL: %s:%d/%s (user=%s)" % (args.host, args.port, args.database, args.user))

try:
    import pymysql
except ImportError:
    print("缺少 pymysql，正在安装…")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pymysql"], check=True)
    import pymysql

# ---------- 读 SQLite ----------
src = sqlite3.connect(SQLITE_DB)
src.row_factory = sqlite3.Row
users = [dict(r) for r in src.execute("SELECT * FROM users ORDER BY id")]
records = [dict(r) for r in src.execute("SELECT * FROM records ORDER BY id")]
src.close()
print("源 SQLite: users=%d, records=%d" % (len(users), len(records)))

if args.dry_run:
    print("[dry-run] 只读不写，退出")
    sys.exit(0)

# ---------- 写 MySQL ----------
conn = pymysql.connect(host=args.host, port=args.port, user=args.user,
                       password=args.password, database=args.database,
                       charset="utf8mb4", autocommit=False)
cur = conn.cursor()

# 先清空（幂等：可重复执行）—— 只动本库的两张表
cur.execute("SET FOREIGN_KEY_CHECKS=0")
cur.execute("TRUNCATE TABLE records")
cur.execute("TRUNCATE TABLE users")
cur.execute("SET FOREIGN_KEY_CHECKS=1")

# users：显式 id 保持与 SQLite 一致（records.user_id 才能对上）
u_cols = ["id", "username", "email", "password_hash", "full_name", "created_at", "is_active", "role"]
u_sql = "INSERT INTO users (%s) VALUES (%s)" % (",".join(u_cols), ",".join(["%s"] * len(u_cols)))
cur.executemany(u_sql, [tuple(u.get(c) for c in u_cols) for u in users])
print("  写入 users: %d 行" % cur.rowcount)

# records
r_cols = ["id", "user_id", "filename", "stored_path", "label", "label_cn", "probability",
          "malignant_prob", "benign_prob", "threshold", "infer_ms", "note", "created_at"]
r_sql = "INSERT INTO records (%s) VALUES (%s)" % (",".join(r_cols), ",".join(["%s"] * len(r_cols)))
cur.executemany(r_sql, [tuple(r.get(c) for c in r_cols) for r in records])
print("  写入 records: %d 行" % cur.rowcount)

conn.commit()

# ---------- 校对 ----------
print("\n=== 校对 ===")
cur.execute("SELECT COUNT(*) FROM users"); nu = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM records"); nr = cur.fetchone()[0]
print("  MySQL users=%d (源 %d) %s" % (nu, len(users), "✔" if nu == len(users) else "✘"))
print("  MySQL records=%d (源 %d) %s" % (nr, len(records), "✔" if nr == len(records) else "✘"))

# admin 账号核对
cur.execute("SELECT id, username, role, is_active, password_hash FROM users WHERE username='admin'")
a = cur.fetchone()
if a:
    ok_hash = a[4] == [u for u in users if u["username"] == "admin"][0]["password_hash"]
    print("  admin: id=%s role=%s is_active=%s 哈希一致=%s" % (a[0], a[2], a[3], "✔" if ok_hash else "✘"))
else:
    print("  ✘ 未找到 admin 账号")

# 时间类型核对（MySQL DATETIME → python datetime）
cur.execute("SELECT created_at FROM users ORDER BY id LIMIT 1")
print("  created_at 类型: %s（应为 datetime）" % type(cur.fetchone()[0]).__name__)

# 记录抽样
cur.execute("SELECT id, filename, label_cn, ROUND(malignant_prob,4), created_at FROM records ORDER BY id DESC LIMIT 3")
print("  最新3条记录:")
for row in cur.fetchall():
    print("    ", row)

cur.close(); conn.close()
print("\n迁移完成 ✔")
