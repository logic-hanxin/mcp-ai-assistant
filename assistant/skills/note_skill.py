"""笔记管理 Skill - 支持创建、列出、搜索、删除笔记 (MySQL 持久化)"""

from __future__ import annotations

from assistant.skills.base import BaseSkill, ToolDefinition, register


class NoteSkill(BaseSkill):
    name = "note"
    description = "个人笔记管理，支持创建、列出、搜索、删除"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="take_note",
                description="保存一条笔记，可以带标签用于分类。",
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "笔记标题"},
                        "content": {"type": "string", "description": "笔记内容"},
                        "tags": {"type": "string", "description": "标签，多个用逗号分隔", "default": ""},
                    },
                    "required": ["title", "content"],
                },
                handler=self._take_note,
            ),
            ToolDefinition(
                name="list_notes",
                description="列出所有笔记，可选按标签过滤。",
                parameters={
                    "type": "object",
                    "properties": {
                        "tag": {"type": "string", "description": "按标签过滤（可选）", "default": ""},
                    },
                },
                handler=self._list_notes,
            ),
            ToolDefinition(
                name="search_notes",
                description="按关键词搜索笔记标题和内容。",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                    },
                    "required": ["query"],
                },
                handler=self._search_notes,
            ),
            ToolDefinition(
                name="delete_note",
                description="根据笔记ID删除一条笔记。",
                parameters={
                    "type": "object",
                    "properties": {
                        "note_id": {"type": "integer", "description": "笔记ID"},
                    },
                    "required": ["note_id"],
                },
                handler=self._delete_note,
            ),
        ]

    def _take_note(self, title: str, content: str, tags: str = "") -> str:
        from assistant.agent.db import note_create
        note_id = note_create(title, content, tags=tags)
        return f"笔记已保存！ID: {note_id}，标题: {title}"

    def _list_notes(self, tag: str = "") -> str:
        from assistant.agent.db import note_list
        notes = note_list(tag=tag)
        if not notes:
            return "暂无笔记。" if not tag else f"没有标签为 '{tag}' 的笔记。"
        lines = []
        for n in notes:
            lines.append(f"[{n['id']}] {n['title']}  标签: [{n.get('tags', '')}]  {n['created_at']}")
        return "\n".join(lines)

    def _search_notes(self, query: str) -> str:
        from assistant.agent.db import note_search
        results = note_search(query)
        if not results:
            return f"没有找到包含 '{query}' 的笔记。"
        lines = [f"[{n['id']}] {n['title']}: {str(n['content'])[:80]}..." for n in results]
        return "\n".join(lines)

    def _delete_note(self, note_id: int) -> str:
        from assistant.agent.db import note_delete
        if note_delete(note_id):
            return f"笔记 {note_id} 已删除。"
        return f"未找到 ID 为 {note_id} 的笔记。"


register(NoteSkill)
