-- ============================================================
--  皮肤癌图像检测系统 · MySQL 独立库初始化
--  ⚠️ 本脚本只创建 skin_cancer 库和专用账号
--     完全不动 yixiaomiao（医小喵）、hospital（课程练习）和系统库
--  执行: mysql.exe -u root -p123456 --default-character-set=utf8mb4 < 01_init_database.sql
-- ============================================================

-- ---------- 1. 独立数据库（utf8mb4，中文/emoji 无乱码）----------
CREATE DATABASE IF NOT EXISTS skin_cancer
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

-- ---------- 2. 专用账号（仅本库权限，绝不用 root）----------
-- 密码与原 SQLite 项目无关联，仅服务本项目
CREATE USER IF NOT EXISTS 'skin_cancer'@'%' IDENTIFIED BY 'skc123456';

-- 只给 skin_cancer 库的权限，不碰其它任何库
GRANT ALL PRIVILEGES ON skin_cancer.* TO 'skin_cancer'@'%';

FLUSH PRIVILEGES;

-- ---------- 3. 验收 ----------
SELECT '=== 数据库 ===' AS info;
SHOW DATABASES;
SELECT '=== skin_cancer 账号权限 ===' AS info;
SHOW GRANTS FOR 'skin_cancer'@'%';
