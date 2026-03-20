"""
通讯录领域数据访问
"""

from __future__ import annotations

from assistant.agent.db_core import get_connection


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
    u = contact_get_user(qq)
    if not u:
        return ""
    return u.get("name") or u.get("nickname") or ""


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
