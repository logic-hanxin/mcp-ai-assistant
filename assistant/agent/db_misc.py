"""
其他领域数据访问

暂存未进入四大核心领域的表操作：
- lessons / rules
- notes
- reminders
- site monitors
- github watches
- news state
"""

from __future__ import annotations

import os

from assistant.agent.db_core import get_connection


def save_lesson(title: str, content: str, category: str = "general",
                tags: str = "", severity: int = 1):
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


def save_rule(title: str, content: str) -> int:
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
    rules = load_rules()
    if not rules:
        return ""
    lines = [f"{i+1}. {r['title']}: {r['content']}" for i, r in enumerate(rules)]
    return "【小彩云守则】你必须严格遵守以下守则:\n" + "\n".join(lines)


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


def note_get(note_id: int) -> dict | None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, content, tags, created_at FROM app_notes WHERE id = %s",
                (note_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def note_append(note_id: int, extra_content: str) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE app_notes SET content = CONCAT(content, %s) WHERE id = %s",
                (extra_content, note_id),
            )
        conn.commit()
        return cur.rowcount > 0
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
            cur.execute("SELECT * FROM app_reminders WHERE triggered = 0 AND target_time <= NOW()")
            return list(cur.fetchall())
    finally:
        conn.close()


def reminder_get_all_pending() -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app_reminders WHERE triggered = 0 ORDER BY target_time ASC")
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
            cur.execute(f"UPDATE app_monitor_sites SET {', '.join(sets)} WHERE url = %s", params)
        conn.commit()
    finally:
        conn.close()


def github_watch_add(repo: str, branch: str = "main", notify_qq: str = "") -> dict:
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


def sql_database_name() -> str:
    """为 SQL 工具提供统一的数据库名读取入口。"""
    return os.getenv("DB_NAME", "useinfo")
