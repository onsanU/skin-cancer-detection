-- ============================================================
--  皮肤癌图像检测系统 · MySQL 建表脚本
--  库: skin_cancer
--  执行: mysql.exe -u root -p123456 --default-character-set=utf8mb4 < 02_create_tables.sql
--
--  ⚠️ SQLite → MySQL 关键差异（已处理）:
--      AUTOINCREMENT           → AUTO_INCREMENT
--      INTEGER PRIMARY KEY     → INT ... AUTO_INCREMENT PRIMARY KEY
--      TEXT 存时间             → DATETIME（便于排序/统计）
--      TEXT DEFAULT ''         → MySQL 允许字面量默认值（TEXT 不能有默认值！）
--                                → VARCHAR 承载短文本，长文本用 TEXT 且不给默认值
--      REAL                    → DOUBLE
-- ============================================================

USE skin_cancer;

-- ---------- users ----------
CREATE TABLE IF NOT EXISTS users (
  id            INT           NOT NULL AUTO_INCREMENT,
  username      VARCHAR(64)   NOT NULL,
  email         VARCHAR(128)  NOT NULL,
  password_hash VARCHAR(255)  NOT NULL COMMENT 'PBKDF2-SHA256 哈希，与原 SQLite 格式完全一致',
  full_name     VARCHAR(64)   NOT NULL DEFAULT '',
  created_at    DATETIME      NOT NULL,
  is_active     TINYINT(1)    NOT NULL DEFAULT 1,
  role          VARCHAR(16)   NOT NULL DEFAULT 'user' COMMENT 'user / admin',
  PRIMARY KEY (id),
  UNIQUE KEY uk_users_username (username),
  UNIQUE KEY uk_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
  COMMENT='用户表（含管理员角色，管理后台靠 role 鉴权）';

-- ---------- records ----------
CREATE TABLE IF NOT EXISTS records (
  id             INT           NOT NULL AUTO_INCREMENT,
  user_id        INT           NOT NULL,
  filename       VARCHAR(255)  NOT NULL COMMENT '原始文件名',
  stored_path    VARCHAR(512)  NOT NULL COMMENT '服务器存储路径（WSL 路径）',
  label          VARCHAR(16)   NOT NULL COMMENT 'benign / malignant',
  label_cn       VARCHAR(16)   NOT NULL,
  probability    DOUBLE        NOT NULL COMMENT '判定类别置信度',
  malignant_prob DOUBLE        NOT NULL,
  benign_prob    DOUBLE        NOT NULL,
  threshold      DOUBLE        NOT NULL DEFAULT 0.5,
  infer_ms       DOUBLE        NOT NULL DEFAULT 0,
  note           VARCHAR(512)  NOT NULL DEFAULT '',
  created_at     DATETIME      NOT NULL,
  PRIMARY KEY (id),
  KEY idx_records_user (user_id, created_at DESC),
  KEY idx_records_label (label),
  CONSTRAINT fk_records_user FOREIGN KEY (user_id)
    REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
  COMMENT='检测历史记录';

-- ---------- admin_logs（管理员操作审计） ----------
CREATE TABLE IF NOT EXISTS admin_logs (
  id          INT           NOT NULL AUTO_INCREMENT,
  admin_id    INT           NULL COMMENT '操作者 ID（账号删除后置 NULL）',
  admin_name  VARCHAR(64)   NOT NULL DEFAULT '' COMMENT '操作者用户名（冗余保存，保证可追溯）',
  action      VARCHAR(64)   NOT NULL COMMENT '语义动作：user.role / user.password / user.active 等',
  method      VARCHAR(8)    NOT NULL COMMENT 'HTTP 方法',
  path        VARCHAR(255)  NOT NULL COMMENT '请求路径',
  target_type VARCHAR(32)   NOT NULL DEFAULT '' COMMENT 'user / record / system',
  target_id   INT           NULL COMMENT '目标对象 ID',
  target_name VARCHAR(128)  NOT NULL DEFAULT '' COMMENT '目标对象名称',
  detail      VARCHAR(512)  NOT NULL DEFAULT '' COMMENT '变更详情',
  status_code INT           NOT NULL DEFAULT 0,
  ip          VARCHAR(64)   NOT NULL DEFAULT '',
  elapsed_ms  DOUBLE        NOT NULL DEFAULT 0,
  created_at  DATETIME      NOT NULL,
  PRIMARY KEY (id),
  KEY idx_admin_logs_time (created_at DESC),
  KEY idx_admin_logs_admin (admin_id, created_at DESC),
  KEY idx_admin_logs_action (action),
  CONSTRAINT fk_admin_logs_admin FOREIGN KEY (admin_id)
    REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
  COMMENT='管理员操作日志（审计追踪）';

-- ---------- chat_sessions（医疗问答会话） ----------
CREATE TABLE IF NOT EXISTS chat_sessions (
  id         INT           NOT NULL AUTO_INCREMENT,
  user_id    INT           NOT NULL,
  title      VARCHAR(128)  NOT NULL DEFAULT '新对话' COMMENT '取首条提问的前若干字',
  created_at DATETIME      NOT NULL,
  updated_at DATETIME      NOT NULL,
  PRIMARY KEY (id),
  KEY idx_chat_sessions_user (user_id, updated_at DESC),
  CONSTRAINT fk_chat_sessions_user FOREIGN KEY (user_id)
    REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
  COMMENT='医疗问答会话';

-- ---------- chat_messages（问答消息） ----------
CREATE TABLE IF NOT EXISTS chat_messages (
  id         INT           NOT NULL AUTO_INCREMENT,
  session_id INT           NOT NULL,
  role       VARCHAR(16)   NOT NULL COMMENT 'user / assistant',
  content    MEDIUMTEXT    NOT NULL COMMENT '消息正文（AI 回答可能较长）',
  image_path VARCHAR(512)  NOT NULL DEFAULT '' COMMENT '用户上传图片的磁盘路径',
  model      VARCHAR(64)   NOT NULL DEFAULT '' COMMENT '实际使用的模型名',
  elapsed_ms DOUBLE        NOT NULL DEFAULT 0,
  created_at DATETIME      NOT NULL,
  PRIMARY KEY (id),
  KEY idx_chat_messages_sess (session_id, id),
  CONSTRAINT fk_chat_messages_sess FOREIGN KEY (session_id)
    REFERENCES chat_sessions (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
  COMMENT='医疗问答消息';

SELECT '=== 建表完成 ===' AS info;
SHOW TABLES;
