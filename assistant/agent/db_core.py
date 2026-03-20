"""
数据库基础设施

负责:
- 连接配置
- 统一建表
"""

from __future__ import annotations

import os

import pymysql

_DB_CONFIG = None


def _get_db_config() -> dict:
    global _DB_CONFIG
    if _DB_CONFIG is None:
        _DB_CONFIG = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "3306")),
            "user": os.getenv("DB_USER", "root"),
            "password": os.getenv("DB_PASSWORD", ""),
            "database": os.getenv("DB_NAME", "useinfo"),
            "charset": "utf8mb4",
            "connect_timeout": 5,
            "read_timeout": 10,
            "cursorclass": pymysql.cursors.DictCursor,
        }
    return _DB_CONFIG


def get_connection() -> pymysql.Connection:
    """获取数据库连接"""
    return pymysql.connect(**_get_db_config())


_INIT_SQL = """
CREATE TABLE IF NOT EXISTS `memory_messages` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `session_id` VARCHAR(100) NOT NULL COMMENT '会话ID (QQ号或 group_群号_QQ号)',
    `role` VARCHAR(20) NOT NULL COMMENT 'user/assistant/tool/system',
    `content` LONGTEXT COMMENT '消息内容',
    `tool_calls` JSON COMMENT 'assistant 的工具调用 (JSON)',
    `tool_call_id` VARCHAR(100) COMMENT 'tool 角色的调用ID',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_session` (`session_id`),
    INDEX `idx_session_time` (`session_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话消息 (短期记忆)';

CREATE TABLE IF NOT EXISTS `memory_summaries` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `session_id` VARCHAR(100) NOT NULL COMMENT '会话ID',
    `summary` TEXT NOT NULL COMMENT '对话摘要',
    `message_count` INT DEFAULT 0 COMMENT '被压缩的消息数',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_session` (`session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话摘要 (压缩记忆)';

CREATE TABLE IF NOT EXISTS `memory_user_facts` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `user_id` VARCHAR(100) NOT NULL COMMENT '用户ID (QQ号)',
    `fact_key` VARCHAR(200) NOT NULL COMMENT '事实键',
    `fact_value` TEXT NOT NULL COMMENT '事实值',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE INDEX `idx_user_key` (`user_id`, `fact_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户偏好/事实 (长期记忆)';

CREATE TABLE IF NOT EXISTS `memory_lessons` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `category` VARCHAR(50) NOT NULL DEFAULT 'general' COMMENT '分类: general/bug/tip/decision',
    `title` VARCHAR(200) NOT NULL COMMENT '标题',
    `content` TEXT NOT NULL COMMENT '详细内容',
    `tags` VARCHAR(500) DEFAULT '' COMMENT '检索标签, 逗号分隔',
    `severity` TINYINT DEFAULT 1 COMMENT '重要性: 1=低 2=中 3=高',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_category` (`category`),
    FULLTEXT INDEX `idx_content` (`title`, `content`, `tags`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='经验教训 (知识层)';

CREATE TABLE IF NOT EXISTS `app_notes` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `user_id` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '创建者QQ号',
    `title` VARCHAR(200) NOT NULL COMMENT '标题',
    `content` TEXT NOT NULL COMMENT '内容',
    `tags` VARCHAR(500) DEFAULT '' COMMENT '标签, 逗号分隔',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='笔记';

CREATE TABLE IF NOT EXISTS `app_contacts_users` (
    `qq` VARCHAR(50) NOT NULL COMMENT 'QQ号',
    `name` VARCHAR(100) DEFAULT '' COMMENT '自定义名称',
    `nickname` VARCHAR(100) DEFAULT '' COMMENT 'QQ昵称(自动)',
    `first_seen` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `last_seen` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `msg_count` INT DEFAULT 0,
    PRIMARY KEY (`qq`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户通讯录';

CREATE TABLE IF NOT EXISTS `app_contacts_groups` (
    `group_id` VARCHAR(50) NOT NULL COMMENT '群号',
    `name` VARCHAR(100) DEFAULT '' COMMENT '自定义名称',
    `group_name` VARCHAR(100) DEFAULT '' COMMENT 'QQ群名(自动)',
    `first_seen` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `last_seen` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `msg_count` INT DEFAULT 0,
    PRIMARY KEY (`group_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='群通讯录';

CREATE TABLE IF NOT EXISTS `app_reminders` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `message` VARCHAR(500) NOT NULL COMMENT '提醒内容',
    `target_time` DATETIME NOT NULL COMMENT '目标时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `triggered` TINYINT DEFAULT 0 COMMENT '是否已触发',
    `notify_qq` VARCHAR(50) DEFAULT '' COMMENT '通知QQ号',
    `notify_group_id` VARCHAR(50) DEFAULT '' COMMENT '通知群号',
    PRIMARY KEY (`id`),
    INDEX `idx_pending` (`triggered`, `target_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时提醒';

CREATE TABLE IF NOT EXISTS `app_monitor_sites` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `url` VARCHAR(500) NOT NULL COMMENT '网站地址',
    `name` VARCHAR(200) DEFAULT '' COMMENT '站点名称',
    `notify_qq` VARCHAR(50) DEFAULT '' COMMENT '通知QQ号',
    `status` VARCHAR(20) DEFAULT 'unknown' COMMENT 'unknown/up/down',
    `fail_count` INT DEFAULT 0,
    `last_check` DATETIME DEFAULT NULL,
    `last_status_code` INT DEFAULT 0,
    `last_error` VARCHAR(500) DEFAULT '',
    `down_since` DATETIME DEFAULT NULL,
    PRIMARY KEY (`id`),
    UNIQUE INDEX `idx_url` (`url`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='网站监控';

CREATE TABLE IF NOT EXISTS `app_github_watches` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `repo` VARCHAR(300) NOT NULL COMMENT '仓库全名 owner/repo',
    `branch` VARCHAR(100) NOT NULL DEFAULT 'main' COMMENT '监控分支',
    `notify_qq` VARCHAR(50) DEFAULT '' COMMENT '通知QQ号',
    `last_commit_sha` VARCHAR(100) DEFAULT '' COMMENT '最后已知提交SHA',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE INDEX `idx_repo_branch` (`repo`, `branch`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='GitHub仓库监控';

CREATE TABLE IF NOT EXISTS `app_news_state` (
    `key_name` VARCHAR(100) NOT NULL COMMENT '状态键',
    `value` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '状态值',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`key_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='新闻推送状态';

CREATE TABLE IF NOT EXISTS `app_workflows` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(200) NOT NULL COMMENT '工作流名称',
    `description` TEXT COMMENT '自然语言描述',
    `steps` JSON NOT NULL COMMENT '步骤定义 [{tool, args}, ...]',
    `schedule` VARCHAR(200) NOT NULL COMMENT '调度规则: daily:08:00 / interval:30m / weekly:1,3,5:09:00 / once:2026-03-20 15:00',
    `enabled` TINYINT DEFAULT 1,
    `created_by` VARCHAR(50) DEFAULT '' COMMENT '创建者QQ号',
    `notify_qq` VARCHAR(50) DEFAULT '' COMMENT '结果通知QQ号',
    `notify_group_id` VARCHAR(50) DEFAULT '' COMMENT '结果通知群号',
    `last_run` DATETIME DEFAULT NULL,
    `next_run` DATETIME DEFAULT NULL,
    `run_count` INT DEFAULT 0,
    `last_result` TEXT COMMENT '上次执行结果摘要',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_enabled_next` (`enabled`, `next_run`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='自动化工作流';

CREATE TABLE IF NOT EXISTS `app_knowledge_docs` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `title` VARCHAR(500) NOT NULL COMMENT '文档标题',
    `source` VARCHAR(500) DEFAULT '' COMMENT '来源: 文件路径/URL/手动输入',
    `doc_type` VARCHAR(50) DEFAULT 'text' COMMENT 'text/url/file',
    `chunk_count` INT DEFAULT 0 COMMENT '分块数量',
    `created_by` VARCHAR(50) DEFAULT '',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库文档';

CREATE TABLE IF NOT EXISTS `app_knowledge_chunks` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `doc_id` BIGINT NOT NULL COMMENT '所属文档ID',
    `chunk_index` INT NOT NULL COMMENT '分块序号',
    `content` TEXT NOT NULL COMMENT '分块内容',
    `embedding` JSON DEFAULT NULL COMMENT '向量嵌入(可选)',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_doc` (`doc_id`),
    FULLTEXT INDEX `idx_content` (`content`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库分块';
"""


def init_tables():
    """初始化数据库表，幂等操作"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for stmt in _INIT_SQL.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
        conn.commit()
        print("[DB] 记忆表初始化完成")
    except Exception as e:
        print(f"[DB] 建表失败: {e}")
    finally:
        conn.close()
