"""
知识库领域数据访问
"""

from __future__ import annotations

from assistant.agent.db_core import get_connection


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
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    finally:
        conn.close()


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
