"""
数据库连接与记忆表管理

记忆分层设计:
- messages: 会话消息（短期记忆），按 session_id 隔离
- summaries: 对话摘要（压缩后的历史），按 session_id 隔离
- user_facts: 用户偏好/事实（长期记忆），按 user_id 隔离
- lessons: 经验教训（跨会话共享的知识）
"""

import os
import json
import datetime

import pymysql

# 数据库配置
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


# ============================================================
# 自动建表
# ============================================================
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
"""


def init_tables():
    """初始化记忆相关表，幂等操作"""
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


# ============================================================
# 消息存取
# ============================================================
def save_message(session_id: str, role: str, content: str = None,
                 tool_calls: list = None, tool_call_id: str = None):
    """保存一条消息到数据库"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO memory_messages (session_id, role, content, tool_calls, tool_call_id) "
                "VALUES (%s, %s, %s, %s, %s)",
                (session_id, role, content,
                 json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
                 tool_call_id),
            )
        conn.commit()
    finally:
        conn.close()


def load_recent_messages(session_id: str, limit: int = 30) -> list[dict]:
    """加载最近的消息，返回 OpenAI 消息格式"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content, tool_calls, tool_call_id FROM memory_messages "
                "WHERE session_id = %s ORDER BY id DESC LIMIT %s",
                (session_id, limit),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    # 反转为时间正序
    rows = list(rows)
    rows.reverse()

    messages = []
    for row in rows:
        msg = {"role": row["role"]}
        if row["content"] is not None:
            msg["content"] = row["content"]
        if row["tool_calls"]:
            tc = row["tool_calls"]
            if isinstance(tc, str):
                tc = json.loads(tc)
            msg["tool_calls"] = tc
        if row["tool_call_id"]:
            msg["tool_call_id"] = row["tool_call_id"]
        messages.append(msg)

    return messages


def delete_old_messages(session_id: str, keep_recent: int = 10) -> int:
    """删除旧消息，保留最近 N 条，返回删除数量"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 找到保留边界的 ID
            cur.execute(
                "SELECT id FROM memory_messages WHERE session_id = %s "
                "ORDER BY id DESC LIMIT 1 OFFSET %s",
                (session_id, keep_recent - 1),
            )
            row = cur.fetchone()
            if not row:
                return 0
            cutoff_id = row["id"]

            cur.execute(
                "DELETE FROM memory_messages WHERE session_id = %s AND id < %s",
                (session_id, cutoff_id),
            )
            deleted = cur.rowcount
        conn.commit()
        return deleted
    finally:
        conn.close()


def count_messages(session_id: str) -> int:
    """统计会话消息数量"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as cnt FROM memory_messages WHERE session_id = %s",
                (session_id,),
            )
            return cur.fetchone()["cnt"]
    finally:
        conn.close()


def clear_session_messages(session_id: str):
    """清空某个会话的所有消息"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM memory_messages WHERE session_id = %s", (session_id,))
        conn.commit()
    finally:
        conn.close()


# ============================================================
# 摘要存取
# ============================================================
def save_summary(session_id: str, summary: str, message_count: int = 0):
    """保存对话摘要"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO memory_summaries (session_id, summary, message_count) "
                "VALUES (%s, %s, %s)",
                (session_id, summary, message_count),
            )
            # 只保留最近 20 条摘要
            cur.execute(
                "DELETE FROM memory_summaries WHERE session_id = %s AND id NOT IN "
                "(SELECT id FROM (SELECT id FROM memory_summaries WHERE session_id = %s "
                "ORDER BY id DESC LIMIT 20) t)",
                (session_id, session_id),
            )
        conn.commit()
    finally:
        conn.close()


def load_summaries(session_id: str, limit: int = 3) -> list[dict]:
    """加载最近的摘要"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT summary, created_at FROM memory_summaries "
                "WHERE session_id = %s ORDER BY id DESC LIMIT %s",
                (session_id, limit),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    rows = list(rows)
    rows.reverse()
    return rows


# ============================================================
# 用户事实存取
# ============================================================
def save_fact(user_id: str, key: str, value: str):
    """保存用户偏好/事实 (UPSERT)"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO memory_user_facts (user_id, fact_key, fact_value) "
                "VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE fact_value = VALUES(fact_value)",
                (user_id, key, value),
            )
        conn.commit()
    finally:
        conn.close()


def load_facts(user_id: str) -> dict:
    """加载用户所有事实，返回 {key: value}"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT fact_key, fact_value FROM memory_user_facts WHERE user_id = %s",
                (user_id,),
            )
            return {row["fact_key"]: row["fact_value"] for row in cur.fetchall()}
    finally:
        conn.close()


# ============================================================
# 经验教训存取
# ============================================================
def save_lesson(title: str, content: str, category: str = "general",
                tags: str = "", severity: int = 1):
    """保存一条经验教训"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO memory_lessons (category, title, content, tags, severity) "
                "VALUES (%s, %s, %s, %s, %s)",
                (category, title, content, tags, severity),
            )
        conn.commit()
    finally:
        conn.close()


def search_lessons(keyword: str = "", category: str = "", limit: int = 5) -> list[dict]:
    """搜索经验教训"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            conditions = []
            params = []
            if keyword:
                conditions.append("MATCH(title, content, tags) AGAINST(%s IN BOOLEAN MODE)")
                params.append(keyword)
            if category:
                conditions.append("category = %s")
                params.append(category)

            where = " AND ".join(conditions) if conditions else "1=1"
            cur.execute(
                f"SELECT title, content, category, tags, severity, created_at "
                f"FROM memory_lessons WHERE {where} ORDER BY created_at DESC LIMIT %s",
                (*params, limit),
            )
            return cur.fetchall()
    finally:
        conn.close()
