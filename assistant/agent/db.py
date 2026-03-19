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
    `description` TEXT DEFAULT '' COMMENT '自然语言描述',
    `steps` JSON NOT NULL COMMENT '步骤定义 [{tool, args}, ...]',
    `schedule` VARCHAR(200) NOT NULL COMMENT '调度规则: daily:08:00 / interval:30m / weekly:1,3,5:09:00 / once:2026-03-20 15:00',
    `enabled` TINYINT DEFAULT 1,
    `created_by` VARCHAR(50) DEFAULT '' COMMENT '创建者QQ号',
    `notify_qq` VARCHAR(50) DEFAULT '' COMMENT '结果通知QQ号',
    `notify_group_id` VARCHAR(50) DEFAULT '' COMMENT '结果通知群号',
    `last_run` DATETIME DEFAULT NULL,
    `next_run` DATETIME DEFAULT NULL,
    `run_count` INT DEFAULT 0,
    `last_result` TEXT DEFAULT '' COMMENT '上次执行结果摘要',
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


# ============================================================
# 小彩云守则
# ============================================================
def save_rule(title: str, content: str) -> int:
    """保存一条守则，返回 ID"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO memory_lessons (category, title, content, severity) "
                "VALUES ('rule', %s, %s, 3)",
                (title, content),
            )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def load_rules() -> list[dict]:
    """加载所有守则"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, content, created_at FROM memory_lessons "
                "WHERE category = 'rule' ORDER BY id ASC"
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def delete_rule(rule_id: int) -> bool:
    """删除一条守则，返回是否成功"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM memory_lessons WHERE id = %s AND category = 'rule'",
                (rule_id,),
            )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def load_rules_text() -> str:
    """加载守则并格式化为文本，供注入 system prompt"""
    rules = load_rules()
    if not rules:
        return ""
    lines = [f"{i+1}. {r['title']}: {r['content']}" for i, r in enumerate(rules)]
    return "【小彩云守则】你必须严格遵守以下守则:\n" + "\n".join(lines)


# ============================================================
# 笔记
# ============================================================
def note_create(title: str, content: str, tags: str = "", user_id: str = "") -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_notes (user_id, title, content, tags) VALUES (%s,%s,%s,%s)",
                (user_id, title, content, tags),
            )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def note_list(user_id: str = "", tag: str = "") -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            conds, params = [], []
            if user_id:
                conds.append("user_id = %s")
                params.append(user_id)
            if tag:
                conds.append("FIND_IN_SET(%s, tags) > 0")
                params.append(tag)
            where = " AND ".join(conds) if conds else "1=1"
            cur.execute(
                f"SELECT id, title, content, tags, created_at FROM app_notes "
                f"WHERE {where} ORDER BY id DESC LIMIT 100",
                params,
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def note_search(query: str) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            like = f"%{query}%"
            cur.execute(
                "SELECT id, title, content, tags, created_at FROM app_notes "
                "WHERE title LIKE %s OR content LIKE %s ORDER BY id DESC LIMIT 50",
                (like, like),
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def note_delete(note_id: int) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM app_notes WHERE id = %s", (note_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ============================================================
# 通讯录 - 用户
# ============================================================
def contact_upsert_user(qq: str, nickname: str = "", name: str = ""):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_contacts_users (qq, nickname, name, msg_count) "
                "VALUES (%s, %s, %s, 1) "
                "ON DUPLICATE KEY UPDATE "
                "nickname = IF(%s != '', %s, nickname), "
                "name = IF(%s != '', %s, name), "
                "msg_count = msg_count + 1, "
                "last_seen = NOW()",
                (qq, nickname, name, nickname, nickname, name, name),
            )
        conn.commit()
    finally:
        conn.close()


def contact_set_user_name(qq: str, name: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_contacts_users (qq, name) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE name = %s",
                (qq, name, name),
            )
        conn.commit()
    finally:
        conn.close()


def contact_get_users() -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app_contacts_users ORDER BY last_seen DESC")
            return list(cur.fetchall())
    finally:
        conn.close()


def contact_get_user(qq: str) -> dict | None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app_contacts_users WHERE qq = %s", (qq,))
            return cur.fetchone()
    finally:
        conn.close()


def contact_get_user_display_name(qq: str) -> str:
    """获取用户显示名称: 优先自定义名 > QQ昵称 > 空"""
    u = contact_get_user(qq)
    if not u:
        return ""
    return u.get("name") or u.get("nickname") or ""


# ============================================================
# 通讯录 - 群
# ============================================================
def contact_upsert_group(group_id: str, group_name: str = "", name: str = ""):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_contacts_groups (group_id, group_name, name, msg_count) "
                "VALUES (%s, %s, %s, 1) "
                "ON DUPLICATE KEY UPDATE "
                "group_name = IF(%s != '', %s, group_name), "
                "name = IF(%s != '', %s, name), "
                "msg_count = msg_count + 1, "
                "last_seen = NOW()",
                (group_id, group_name, name, group_name, group_name, name, name),
            )
        conn.commit()
    finally:
        conn.close()


def contact_set_group_name(group_id: str, name: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_contacts_groups (group_id, name) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE name = %s",
                (group_id, name, name),
            )
        conn.commit()
    finally:
        conn.close()


def contact_get_groups() -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app_contacts_groups ORDER BY last_seen DESC")
            return list(cur.fetchall())
    finally:
        conn.close()


# ============================================================
# 提醒
# ============================================================
def reminder_create(message: str, target_time: str, notify_qq: str = "",
                    notify_group_id: str = "") -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_reminders (message, target_time, notify_qq, notify_group_id) "
                "VALUES (%s, %s, %s, %s)",
                (message, target_time, notify_qq, notify_group_id),
            )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def reminder_get_pending() -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM app_reminders WHERE triggered = 0 AND target_time <= NOW()"
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def reminder_get_all_pending() -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM app_reminders WHERE triggered = 0 ORDER BY target_time ASC"
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def reminder_mark_triggered(reminder_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE app_reminders SET triggered = 1 WHERE id = %s", (reminder_id,))
        conn.commit()
    finally:
        conn.close()


def reminder_delete(reminder_id: int) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM app_reminders WHERE id = %s", (reminder_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ============================================================
# 网站监控
# ============================================================
def monitor_add_site(url: str, name: str = "", notify_qq: str = "") -> dict:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_monitor_sites (url, name, notify_qq) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE name = IF(%s != '', %s, name), "
                "notify_qq = IF(%s != '', %s, notify_qq)",
                (url, name, notify_qq, name, name, notify_qq, notify_qq),
            )
        conn.commit()
        # 返回刚插入/更新的记录
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app_monitor_sites WHERE url = %s", (url,))
            return cur.fetchone() or {}
    finally:
        conn.close()


def monitor_remove_site(url: str) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM app_monitor_sites WHERE url = %s", (url,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def monitor_get_sites() -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app_monitor_sites ORDER BY id ASC")
            return list(cur.fetchall())
    finally:
        conn.close()


def monitor_update_site(url: str, **kwargs):
    """更新监控站点状态字段"""
    if not kwargs:
        return
    conn = get_connection()
    try:
        sets = []
        params = []
        for k, v in kwargs.items():
            sets.append(f"`{k}` = %s")
            params.append(v)
        params.append(url)
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE app_monitor_sites SET {', '.join(sets)} WHERE url = %s",
                params,
            )
        conn.commit()
    finally:
        conn.close()


# ============================================================
# GitHub 仓库监控
# ============================================================
def github_watch_add(repo: str, branch: str = "main", notify_qq: str = "") -> dict:
    """添加/更新一个监控仓库，返回记录"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_github_watches (repo, branch, notify_qq) "
                "VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE notify_qq = %s",
                (repo, branch, notify_qq, notify_qq),
            )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM app_github_watches WHERE repo = %s AND branch = %s",
                (repo, branch),
            )
            return cur.fetchone() or {}
    finally:
        conn.close()


def github_watch_remove(repo: str) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM app_github_watches WHERE repo = %s", (repo,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def github_watch_list() -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app_github_watches ORDER BY id ASC")
            return list(cur.fetchall())
    finally:
        conn.close()


def github_watch_update_sha(repo: str, branch: str, sha: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE app_github_watches SET last_commit_sha = %s "
                "WHERE repo = %s AND branch = %s",
                (sha, repo, branch),
            )
        conn.commit()
    finally:
        conn.close()


# ============================================================
# 新闻推送状态
# ============================================================
def news_state_get(key: str) -> str:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM app_news_state WHERE key_name = %s", (key,))
            row = cur.fetchone()
            return row["value"] if row else ""
    finally:
        conn.close()


def news_state_set(key: str, value: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_news_state (key_name, value) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE value = %s",
                (key, value, value),
            )
        conn.commit()
    finally:
        conn.close()


# ============================================================
# 工作流
# ============================================================
def workflow_create(name: str, steps: str, schedule: str,
                    description: str = "", created_by: str = "",
                    notify_qq: str = "", notify_group_id: str = "",
                    next_run: str = "") -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_workflows "
                "(name, description, steps, schedule, created_by, notify_qq, notify_group_id, next_run) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (name, description, steps, schedule, created_by,
                 notify_qq, notify_group_id, next_run or None),
            )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def workflow_list(enabled_only: bool = False) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if enabled_only:
                cur.execute(
                    "SELECT * FROM app_workflows WHERE enabled = 1 ORDER BY id ASC"
                )
            else:
                cur.execute("SELECT * FROM app_workflows ORDER BY id ASC")
            return list(cur.fetchall())
    finally:
        conn.close()


def workflow_get(workflow_id: int) -> dict | None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app_workflows WHERE id = %s", (workflow_id,))
            return cur.fetchone()
    finally:
        conn.close()


def workflow_get_due() -> list[dict]:
    """获取到期需要执行的工作流"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM app_workflows "
                "WHERE enabled = 1 AND next_run IS NOT NULL AND next_run <= NOW()"
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def workflow_update_after_run(workflow_id: int, next_run: str | None,
                              last_result: str = ""):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE app_workflows SET "
                "last_run = NOW(), next_run = %s, run_count = run_count + 1, "
                "last_result = %s WHERE id = %s",
                (next_run, last_result[:2000], workflow_id),
            )
        conn.commit()
    finally:
        conn.close()


def workflow_toggle(workflow_id: int, enabled: bool) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE app_workflows SET enabled = %s WHERE id = %s",
                (1 if enabled else 0, workflow_id),
            )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def workflow_delete(workflow_id: int) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM app_workflows WHERE id = %s", (workflow_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ============================================================
# 知识库 - 文档
# ============================================================
def knowledge_add_doc(title: str, source: str = "", doc_type: str = "text",
                      created_by: str = "") -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_knowledge_docs (title, source, doc_type, created_by) "
                "VALUES (%s, %s, %s, %s)",
                (title, source, doc_type, created_by),
            )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def knowledge_update_doc_chunks(doc_id: int, chunk_count: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE app_knowledge_docs SET chunk_count = %s WHERE id = %s",
                (chunk_count, doc_id),
            )
        conn.commit()
    finally:
        conn.close()


def knowledge_list_docs() -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, source, doc_type, chunk_count, created_by, created_at "
                "FROM app_knowledge_docs ORDER BY id DESC"
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def knowledge_delete_doc(doc_id: int) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM app_knowledge_chunks WHERE doc_id = %s", (doc_id,))
            cur.execute("DELETE FROM app_knowledge_docs WHERE id = %s", (doc_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ============================================================
# 知识库 - 分块
# ============================================================
def knowledge_add_chunk(doc_id: int, chunk_index: int, content: str,
                        embedding: str | None = None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_knowledge_chunks (doc_id, chunk_index, content, embedding) "
                "VALUES (%s, %s, %s, %s)",
                (doc_id, chunk_index, content, embedding),
            )
        conn.commit()
    finally:
        conn.close()


def knowledge_add_chunks_batch(doc_id: int, chunks: list[dict]):
    """批量插入分块: [{"index": 0, "content": "...", "embedding": "...或None"}]"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for c in chunks:
                cur.execute(
                    "INSERT INTO app_knowledge_chunks (doc_id, chunk_index, content, embedding) "
                    "VALUES (%s, %s, %s, %s)",
                    (doc_id, c["index"], c["content"], c.get("embedding")),
                )
        conn.commit()
    finally:
        conn.close()


def knowledge_search_fulltext(query: str, top_k: int = 5) -> list[dict]:
    """全文检索知识库分块"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.id, c.doc_id, c.chunk_index, c.content, "
                "d.title as doc_title, "
                "MATCH(c.content) AGAINST(%s IN NATURAL LANGUAGE MODE) as score "
                "FROM app_knowledge_chunks c "
                "JOIN app_knowledge_docs d ON c.doc_id = d.id "
                "WHERE MATCH(c.content) AGAINST(%s IN NATURAL LANGUAGE MODE) "
                "ORDER BY score DESC LIMIT %s",
                (query, query, top_k),
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def knowledge_search_like(query: str, top_k: int = 5) -> list[dict]:
    """LIKE 模糊搜索 (FULLTEXT 无结果时的降级方案)"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            like = f"%{query}%"
            cur.execute(
                "SELECT c.id, c.doc_id, c.chunk_index, c.content, "
                "d.title as doc_title "
                "FROM app_knowledge_chunks c "
                "JOIN app_knowledge_docs d ON c.doc_id = d.id "
                "WHERE c.content LIKE %s "
                "ORDER BY c.id DESC LIMIT %s",
                (like, top_k),
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def knowledge_get_all_chunks_with_embedding() -> list[dict]:
    """获取所有有嵌入向量的分块 (用于向量检索)"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.id, c.doc_id, c.chunk_index, c.content, c.embedding, "
                "d.title as doc_title "
                "FROM app_knowledge_chunks c "
                "JOIN app_knowledge_docs d ON c.doc_id = d.id "
                "WHERE c.embedding IS NOT NULL"
            )
            return list(cur.fetchall())
    finally:
        conn.close()