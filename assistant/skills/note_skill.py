"""笔记管理 Skill - 支持创建、列出、搜索、删除笔记 (MySQL 持久化)"""

from __future__ import annotations

import re

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
                metadata={
                    "category": "write",
                    "side_effect": "data_write",
                    "blackboard_writes": ["last_note_result"],
                    "required_all": ["title", "content"],
                    "store_result": ["last_note_result"],
                },
                result_parser=self._parse_take_note_result,
                keywords=["记笔记", "保存内容", "记录一下", "写入笔记"],
                intents=["take_note", "save_note"],
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
                metadata={
                    "category": "read",
                    "blackboard_writes": ["last_note_result"],
                    "store_result": ["last_note_result"],
                },
                result_parser=self._parse_list_notes_result,
                keywords=["笔记列表", "查看笔记", "所有笔记"],
                intents=["list_notes"],
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
                metadata={
                    "category": "read",
                    "blackboard_writes": ["last_note_result"],
                    "required_all": ["query"],
                    "store_result": ["last_note_result"],
                },
                result_parser=self._parse_search_notes_result,
                keywords=["搜索笔记", "查笔记", "笔记检索"],
                intents=["search_notes"],
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
                metadata={
                    "category": "write",
                    "side_effect": "data_write",
                },
                result_parser=self._parse_delete_note_result,
                keywords=["删除笔记", "移除笔记"],
                intents=["delete_note"],
            ),
            ToolDefinition(
                name="append_note",
                description="向已有笔记追加内容，适合持续记录进展或补充信息。",
                parameters={
                    "type": "object",
                    "properties": {
                        "note_id": {"type": "integer", "description": "要追加的笔记ID"},
                        "content": {"type": "string", "description": "要追加的内容"},
                    },
                    "required": ["note_id", "content"],
                },
                handler=self._append_note,
                metadata={
                    "category": "write",
                    "side_effect": "data_write",
                    "required_all": ["note_id", "content"],
                    "store_result": ["last_note_result"],
                },
                result_parser=self._parse_append_note_result,
                keywords=["追加笔记", "补充笔记", "继续记录"],
                intents=["append_note"],
            ),
            ToolDefinition(
                name="summarize_notes",
                description="对笔记做简要整理，可按标签或关键词筛选。",
                parameters={
                    "type": "object",
                    "properties": {
                        "tag": {"type": "string", "description": "按标签筛选", "default": ""},
                        "query": {"type": "string", "description": "按关键词筛选", "default": ""},
                        "limit": {"type": "integer", "description": "最多整理多少条笔记，默认10", "default": 10},
                    },
                },
                handler=self._summarize_notes,
                metadata={
                    "category": "read",
                    "store_result": ["last_note_result"],
                },
                result_parser=self._parse_summarize_notes_result,
                keywords=["整理笔记", "总结笔记", "归纳笔记"],
                intents=["summarize_notes"],
            ),
        ]

    def _take_note(self, title: str, content: str, tags: str = "") -> str:
        from assistant.agent.db_misc import note_create
        note_id = note_create(title, content, tags=tags)
        return f"笔记已保存！ID: {note_id}，标题: {title}"

    def _list_notes(self, tag: str = "") -> str:
        from assistant.agent.db_misc import note_list
        notes = note_list(tag=tag)
        if not notes:
            return "暂无笔记。" if not tag else f"没有标签为 '{tag}' 的笔记。"
        lines = []
        for n in notes:
            lines.append(f"[{n['id']}] {n['title']}  标签: [{n.get('tags', '')}]  {n['created_at']}")
        return "\n".join(lines)

    def _search_notes(self, query: str) -> str:
        from assistant.agent.db_misc import note_search
        results = note_search(query)
        if not results:
            return f"没有找到包含 '{query}' 的笔记。"
        lines = [f"[{n['id']}] {n['title']}: {str(n['content'])[:80]}..." for n in results]
        return "\n".join(lines)

    def _delete_note(self, note_id: int) -> str:
        from assistant.agent.db_misc import note_delete
        if note_delete(note_id):
            return f"笔记 {note_id} 已删除。"
        return f"未找到 ID 为 {note_id} 的笔记。"

    def _append_note(self, note_id: int, content: str) -> str:
        from assistant.agent.db_misc import note_append, note_get
        note = note_get(note_id)
        if not note:
            return f"未找到 ID 为 {note_id} 的笔记。"
        extra = "\n" + content.strip()
        if note_append(note_id, extra):
            return f"已向笔记 {note_id} 追加内容。"
        return f"追加失败，未找到 ID 为 {note_id} 的笔记。"

    def _summarize_notes(self, tag: str = "", query: str = "", limit: int = 10) -> str:
        from assistant.agent.db_misc import note_list, note_search
        if query.strip():
            notes = note_search(query)
        else:
            notes = note_list(tag=tag)
        notes = notes[:max(1, limit)]
        if not notes:
            return "没有可整理的笔记。"

        lines = [f"共整理 {len(notes)} 条笔记:"]
        for idx, note in enumerate(notes, 1):
            snippet = str(note.get("content", "")).replace("\n", " ").strip()
            if len(snippet) > 60:
                snippet = snippet[:60] + "..."
            tags = str(note.get("tags", "")).strip()
            tag_text = f" [{tags}]" if tags else ""
            lines.append(f"{idx}. {note['title']}{tag_text}: {snippet}")
        return "\n".join(lines)

    def _parse_take_note_result(self, args: dict, result: str) -> dict | None:
        match = re.search(r"ID:\s*(\d+)", result)
        note_id = int(match.group(1)) if match else None
        return {
            "action": "take_note",
            "note_id": note_id,
            "title": str(args.get("title", "")).strip(),
            "content": str(args.get("content", "")).strip(),
            "tags": str(args.get("tags", "")).strip(),
        }

    def _parse_list_notes_result(self, args: dict, result: str) -> dict | None:
        notes = []
        for line in result.splitlines():
            match = re.match(r"^\[(\d+)\]\s+(.+?)\s+标签:\s+\[(.*)\]\s+(.*)$", line.strip())
            if match:
                notes.append(
                    {
                        "id": int(match.group(1)),
                        "title": match.group(2).strip(),
                        "tags": match.group(3).strip(),
                        "created_at": match.group(4).strip(),
                    }
                )
        return {
            "action": "list_notes",
            "tag": str(args.get("tag", "")).strip(),
            "notes": notes,
        }

    def _parse_search_notes_result(self, args: dict, result: str) -> dict | None:
        notes = []
        for line in result.splitlines():
            match = re.match(r"^\[(\d+)\]\s+(.+?):\s+(.+)$", line.strip())
            if match:
                notes.append(
                    {
                        "id": int(match.group(1)),
                        "title": match.group(2).strip(),
                        "snippet": match.group(3).strip(),
                    }
                )
        return {
            "action": "search_notes",
            "query": str(args.get("query", "")).strip(),
            "notes": notes,
        }

    def _parse_delete_note_result(self, args: dict, result: str) -> dict | None:
        return {
            "action": "delete_note",
            "note_id": args.get("note_id"),
            "deleted": "已删除" in result,
        }

    def _parse_append_note_result(self, args: dict, result: str) -> dict | None:
        return {
            "action": "append_note",
            "note_id": args.get("note_id"),
            "appended": "已向笔记" in result,
        }

    def _parse_summarize_notes_result(self, args: dict, result: str) -> dict | None:
        return {
            "action": "summarize_notes",
            "tag": str(args.get("tag", "")).strip(),
            "query": str(args.get("query", "")).strip(),
            "result": result[:500],
        }


register(NoteSkill)
