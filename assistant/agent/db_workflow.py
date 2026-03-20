"""
工作流领域数据访问
"""

from __future__ import annotations

from assistant.agent.db_core import get_connection


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
                cur.execute("SELECT * FROM app_workflows WHERE enabled = 1 ORDER BY id ASC")
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
