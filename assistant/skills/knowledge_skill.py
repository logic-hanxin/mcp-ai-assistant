"""
知识库 Skill - RAG 检索增强生成

用户可以向知识库添加文档（规章制度、FAQ、教程等），
提问时自动检索相关内容辅助回答。

支持:
- 直接输入文本加入知识库
- 搜索知识库获取相关信息
- 管理已有文档（列表、删除）
"""

import datetime
from assistant.skills.base import BaseSkill, ToolDefinition, register
from assistant.agent import db
from assistant.agent.rag import ingest_document, search_knowledge


class KnowledgeSkill(BaseSkill):
    name = "knowledge"
    description = "RAG 知识库，存储协会文档和资料，提问时智能检索"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="add_knowledge",
                description=(
                    "将一段文本加入知识库。适用于协会规章制度、FAQ、流程说明、会议纪要等。"
                    "文本会被自动分块存储，之后提问相关内容时可以检索到。"
                    "支持长文本，系统会自动分块处理。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "文档标题，如 '彩云协会入会流程'、'2024年活动安排'",
                        },
                        "content": {
                            "type": "string",
                            "description": "文档内容（纯文本）",
                        },
                        "source": {
                            "type": "string",
                            "description": "来源说明，如 '协会规章制度第3章'、'群聊整理'",
                            "default": "",
                        },
                    },
                    "required": ["title", "content"],
                },
                handler=self._add_knowledge,
            ),
            ToolDefinition(
                name="search_knowledge",
                description=(
                    "搜索知识库，查找与问题相关的内容。"
                    "当用户问到协会相关的规章、流程、历史信息时，应先搜索知识库。"
                    "返回最相关的知识片段，可作为回答依据。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索问题，如 '入会流程'、'活动报名方式'、'会费标准'",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "返回结果数量，默认5",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
                handler=self._search_knowledge,
            ),
            ToolDefinition(
                name="list_knowledge_docs",
                description="列出知识库中的所有文档。",
                parameters={"type": "object", "properties": {}},
                handler=self._list_docs,
            ),
            ToolDefinition(
                name="delete_knowledge_doc",
                description="从知识库中删除一个文档及其所有分块。",
                parameters={
                    "type": "object",
                    "properties": {
                        "doc_id": {
                            "type": "integer",
                            "description": "文档ID",
                        },
                    },
                    "required": ["doc_id"],
                },
                handler=self._delete_doc,
            ),
        ]

    def _add_knowledge(self, title: str, content: str, source: str = "") -> str:
        if not content.strip():
            return "内容不能为空。"

        if len(content) < 10:
            return "内容太短，至少需要10个字符。"

        try:
            result = ingest_document(
                title=title,
                content=content,
                source=source,
                doc_type="text",
            )
        except Exception as e:
            return f"入库失败: {e}"

        if result["chunk_count"] == 0:
            return "文档内容为空，未能入库。"

        emb_str = "✅ 已生成向量嵌入" if result["has_embedding"] else "⚠️ 未配置嵌入模型，仅支持关键词检索"
        return (
            f"知识已入库！\n"
            f"  文档ID: {result['doc_id']}\n"
            f"  标题: {title}\n"
            f"  分块数: {result['chunk_count']}\n"
            f"  嵌入: {emb_str}"
        )

    def _search_knowledge(self, query: str, top_k: int = 5) -> str:
        try:
            results = search_knowledge(query, top_k=top_k)
        except Exception as e:
            return f"搜索失败: {e}"

        if not results:
            return f"未找到与「{query}」相关的知识。"

        lines = [f"找到 {len(results)} 条相关知识:"]
        for i, r in enumerate(results, 1):
            title = r.get("doc_title", "")
            score = r.get("score", 0)
            content = r["content"]
            # 截取显示
            if len(content) > 300:
                content = content[:300] + "..."

            header = f"\n[{i}]"
            if title:
                header += f" 来源: {title}"
            if score:
                header += f" (相关度: {score:.2f})"
            lines.append(header)
            lines.append(content)

        return "\n".join(lines)

    def _list_docs(self) -> str:
        try:
            docs = db.knowledge_list_docs()
        except Exception as e:
            return f"查询失败: {e}"

        if not docs:
            return "知识库为空，还没有添加任何文档。"

        lines = [f"知识库共 {len(docs)} 个文档:"]
        for d in docs:
            created = d.get("created_at")
            if isinstance(created, datetime.datetime):
                date_str = created.strftime("%m-%d %H:%M")
            else:
                date_str = str(created)[:16] if created else ""

            lines.append(
                f"  [{d['id']}] {d['title']}"
                f"  ({d['chunk_count']}块"
                f"  {d.get('doc_type', 'text')}"
                f"  {date_str})"
            )

        return "\n".join(lines)

    def _delete_doc(self, doc_id: int) -> str:
        try:
            ok = db.knowledge_delete_doc(doc_id)
        except Exception as e:
            return f"删除失败: {e}"
        if not ok:
            return f"未找到 ID 为 {doc_id} 的文档。"
        return f"文档 {doc_id} 及其所有分块已删除。"


register(KnowledgeSkill)
