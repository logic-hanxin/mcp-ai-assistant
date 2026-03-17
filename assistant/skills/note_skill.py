"""笔记管理 Skill - 支持创建、列出、搜索、删除笔记"""

import json
import datetime
from pathlib import Path
from assistant.skills.base import BaseSkill, ToolDefinition, register


class NoteSkill(BaseSkill):
    name = "note"
    description = "个人笔记管理，支持创建、列出、搜索、删除"

    def __init__(self):
        self.notes_dir = Path.home() / ".ai_assistant" / "notes"
        self.notes_file = self.notes_dir / "notes.json"

    def on_load(self):
        self.notes_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        if self.notes_file.exists():
            return json.loads(self.notes_file.read_text(encoding="utf-8"))
        return []

    def _save(self, notes: list[dict]):
        self.notes_file.write_text(
            json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8"
        )

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
        notes = self._load()
        max_id = max((n["id"] for n in notes), default=0)
        note = {
            "id": max_id + 1,
            "title": title,
            "content": content,
            "tags": [t.strip() for t in tags.split(",") if t.strip()],
            "created_at": datetime.datetime.now().isoformat(),
        }
        notes.append(note)
        self._save(notes)
        return f"笔记已保存！ID: {note['id']}，标题: {title}"

    def _list_notes(self, tag: str = "") -> str:
        notes = self._load()
        if tag:
            notes = [n for n in notes if tag in n.get("tags", [])]
        if not notes:
            return "暂无笔记。" if not tag else f"没有标签为 '{tag}' 的笔记。"
        lines = []
        for n in notes:
            tags_str = ", ".join(n.get("tags", []))
            lines.append(f"[{n['id']}] {n['title']}  标签: [{tags_str}]  {n['created_at']}")
        return "\n".join(lines)

    def _search_notes(self, query: str) -> str:
        notes = self._load()
        q = query.lower()
        results = [n for n in notes if q in n["title"].lower() or q in n["content"].lower()]
        if not results:
            return f"没有找到包含 '{query}' 的笔记。"
        lines = [f"[{n['id']}] {n['title']}: {n['content'][:80]}..." for n in results]
        return "\n".join(lines)

    def _delete_note(self, note_id: int) -> str:
        notes = self._load()
        original_len = len(notes)
        notes = [n for n in notes if n["id"] != note_id]
        if len(notes) == original_len:
            return f"未找到 ID 为 {note_id} 的笔记。"
        self._save(notes)
        return f"笔记 {note_id} 已删除。"


register(NoteSkill)
