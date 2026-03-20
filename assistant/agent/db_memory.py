"""
记忆领域数据访问
"""

from __future__ import annotations

import json

from assistant.agent.db_core import get_connection


def save_message(session_id: str, role: str, content: str = None,
                 tool_calls: list = None, tool_call_id: str = None):
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
    conn = get_connection()
    try:
        with conn.cursor() as cur:
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
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM memory_messages WHERE session_id = %s", (session_id,))
        conn.commit()
    finally:
        conn.close()


def save_summary(session_id: str, summary: str, message_count: int = 0):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO memory_summaries (session_id, summary, message_count) "
                "VALUES (%s, %s, %s)",
                (session_id, summary, message_count),
            )
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


def save_fact(user_id: str, key: str, value: str):
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
