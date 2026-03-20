"""
RAG 核心引擎 - 检索增强生成

功能:
- 文本分块 (固定大小 + 重叠)
- 向量嵌入 (可选，通过 OpenAI 兼容 API)
- 混合检索 (向量相似度 + MySQL 全文检索)
- 上下文构建 (将检索结果注入 LLM 上下文)

嵌入模型配置 (可选，不配置则仅用全文检索):
  EMBEDDING_API_KEY   - 嵌入 API Key
  EMBEDDING_BASE_URL  - 嵌入 API 地址 (OpenAI 兼容)
  EMBEDDING_MODEL     - 嵌入模型名称
"""

from __future__ import annotations

import os
import json
import math
from typing import Optional

from assistant.agent import db_knowledge as db


# ============================================================
# 文本分块
# ============================================================
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """
    将文本分割为重叠的块。
    优先按段落/句子边界切分，避免在句子中间断开。
    """
    if not text or not text.strip():
        return []

    # 按段落切分
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        # 如果当前段落本身超长，按句子切分
        if len(para) > chunk_size:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            sentences = _split_sentences(para)
            for sent in sentences:
                if len(current_chunk) + len(sent) > chunk_size and current_chunk:
                    chunks.append(current_chunk)
                    # 保留重叠部分
                    current_chunk = current_chunk[-overlap:] if overlap else ""
                current_chunk += sent
        elif len(current_chunk) + len(para) + 1 > chunk_size and current_chunk:
            chunks.append(current_chunk)
            current_chunk = current_chunk[-overlap:] if overlap else ""
            current_chunk += para + "\n"
        else:
            current_chunk += para + "\n"

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def _split_sentences(text: str) -> list[str]:
    """按句子边界切分文本"""
    import re
    # 中文句号、问号、叹号、英文句号
    parts = re.split(r'([。！？.!?\n]+)', text)
    sentences = []
    for i in range(0, len(parts) - 1, 2):
        sentences.append(parts[i] + parts[i + 1])
    if len(parts) % 2 == 1 and parts[-1].strip():
        sentences.append(parts[-1])
    return sentences


# ============================================================
# 向量嵌入 (可选)
# ============================================================
def _get_embedding_client():
    """获取嵌入 API 客户端，未配置返回 None"""
    api_key = os.getenv("EMBEDDING_API_KEY", "")
    base_url = os.getenv("EMBEDDING_BASE_URL", "")
    if not api_key or not base_url:
        return None, None
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        return client, model
    except Exception:
        return None, None


def get_embedding(text: str) -> list[float] | None:
    """获取文本的向量嵌入，未配置嵌入 API 返回 None"""
    client, model = _get_embedding_client()
    if not client:
        return None
    try:
        resp = client.embeddings.create(input=text, model=model)
        return resp.data[0].embedding
    except Exception as e:
        print(f"[RAG] 嵌入失败: {e}")
        return None


def get_embeddings_batch(texts: list[str]) -> list[list[float] | None]:
    """批量获取向量嵌入"""
    client, model = _get_embedding_client()
    if not client:
        return [None] * len(texts)
    try:
        resp = client.embeddings.create(input=texts, model=model)
        return [item.embedding for item in resp.data]
    except Exception as e:
        print(f"[RAG] 批量嵌入失败: {e}")
        return [None] * len(texts)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算余弦相似度"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ============================================================
# 文档入库
# ============================================================
def ingest_document(title: str, content: str, source: str = "",
                    doc_type: str = "text", created_by: str = "",
                    chunk_size: int = 500) -> dict:
    """
    将文档分块、嵌入（可选）并存入知识库。

    Returns:
        {"doc_id": int, "chunk_count": int, "has_embedding": bool}
    """
    # 1. 分块
    chunks = chunk_text(content, chunk_size=chunk_size)
    if not chunks:
        return {"doc_id": 0, "chunk_count": 0, "has_embedding": False}

    # 2. 创建文档记录
    doc_id = db.knowledge_add_doc(
        title=title, source=source, doc_type=doc_type, created_by=created_by
    )

    # 3. 尝试批量嵌入
    embeddings = get_embeddings_batch(chunks)
    has_embedding = any(e is not None for e in embeddings)

    # 4. 存入分块
    chunk_records = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        chunk_records.append({
            "index": i,
            "content": chunk,
            "embedding": json.dumps(emb) if emb else None,
        })
    db.knowledge_add_chunks_batch(doc_id, chunk_records)

    # 5. 更新文档的分块数
    db.knowledge_update_doc_chunks(doc_id, len(chunks))

    return {"doc_id": doc_id, "chunk_count": len(chunks), "has_embedding": has_embedding}


# ============================================================
# 知识检索
# ============================================================
def search_knowledge(query: str, top_k: int = 5) -> list[dict]:
    """
    混合检索知识库:
    1. 如果有嵌入向量 → 向量相似度检索
    2. MySQL FULLTEXT 全文检索
    3. LIKE 模糊搜索 (降级方案)

    返回: [{"content": "...", "doc_title": "...", "score": 0.85}, ...]
    """
    results = []

    # 尝试向量检索
    query_emb = get_embedding(query)
    if query_emb:
        results = _search_by_vector(query_emb, top_k)

    # 向量检索无结果 → 全文检索
    if not results:
        try:
            rows = db.knowledge_search_fulltext(query, top_k)
            results = [
                {
                    "content": r["content"],
                    "doc_title": r.get("doc_title", ""),
                    "score": float(r.get("score", 0)),
                }
                for r in rows
            ]
        except Exception:
            pass

    # 全文检索也无结果 → LIKE 降级
    if not results:
        try:
            rows = db.knowledge_search_like(query, top_k)
            results = [
                {
                    "content": r["content"],
                    "doc_title": r.get("doc_title", ""),
                    "score": 0.5,
                }
                for r in rows
            ]
        except Exception:
            pass

    return results


def _search_by_vector(query_embedding: list[float], top_k: int = 5) -> list[dict]:
    """向量相似度检索"""
    try:
        all_chunks = db.knowledge_get_all_chunks_with_embedding()
    except Exception:
        return []

    if not all_chunks:
        return []

    scored = []
    for chunk in all_chunks:
        emb_data = chunk.get("embedding")
        if not emb_data:
            continue
        if isinstance(emb_data, str):
            emb_data = json.loads(emb_data)
        if not isinstance(emb_data, list):
            continue

        score = cosine_similarity(query_embedding, emb_data)
        scored.append({
            "content": chunk["content"],
            "doc_title": chunk.get("doc_title", ""),
            "score": score,
        })

    # 按相似度降序
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ============================================================
# 上下文构建
# ============================================================
def build_rag_context(query: str, top_k: int = 3) -> str:
    """
    检索相关知识并构建 LLM 上下文片段。
    如果无相关结果返回空字符串。
    """
    results = search_knowledge(query, top_k=top_k)
    if not results:
        return ""

    lines = ["[知识库参考]"]
    for i, r in enumerate(results, 1):
        title = r.get("doc_title", "")
        content = r["content"][:300]
        if title:
            lines.append(f"[{i}] 来源: {title}")
        lines.append(content)
        lines.append("")

    return "\n".join(lines)
