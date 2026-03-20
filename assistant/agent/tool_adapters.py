"""
Tool Adapter 层

负责把特定工具的结果结构化后写入黑板，
避免这些解析逻辑散落在 AgentCore 中。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


@dataclass
class ToolEvent:
    tool_name: str
    tool_args: dict
    tool_result: str
    structured_result: dict | None = None


class ToolAdapter:
    """工具适配器基类"""

    tool_names: tuple[str, ...] = ()

    def supports(self, tool_name: str) -> bool:
        return tool_name in self.tool_names

    def apply(self, core, event: ToolEvent):
        raise NotImplementedError


class ContactToolAdapter(ToolAdapter):
    tool_names = ("set_user_name", "find_qq_by_name", "list_contacts", "get_user_name")

    def apply(self, core, event: ToolEvent):
        parsed = _parse_structured_result(core, event)
        if parsed and parsed.get("contacts"):
            for item in parsed["contacts"]:
                qq = str(item.get("qq", "")).strip()
                name = str(item.get("name", "")).strip()
                if qq and name:
                    core.blackboard.write_entity(
                        "contact",
                        core._bb_scoped_key(f"contact:{qq}"),
                        {"qq": qq, "name": name},
                        event.tool_name,
                        0.9,
                    )
            return

        if event.tool_name == "set_user_name":
            qq = str(event.tool_args.get("qq_number", "")).strip()
            name = str(event.tool_args.get("name", "")).strip()
            if qq and name:
                core.blackboard.write_entity(
                    "contact",
                    core._bb_scoped_key(f"contact:{qq}"),
                    {"qq": qq, "name": name},
                    event.tool_name,
                    0.95,
                )
            return

        if event.tool_name in ("find_qq_by_name", "list_contacts"):
            confidence = 0.85 if event.tool_name == "find_qq_by_name" else 0.75
            for qq, name in _extract_contact_pairs(event.tool_result):
                core.blackboard.write_entity(
                    "contact",
                    core._bb_scoped_key(f"contact:{qq}"),
                    {"qq": qq, "name": name},
                    event.tool_name,
                    confidence,
                )
            return

        if event.tool_name == "get_user_name":
            qq = str(event.tool_args.get("qq_number", "")).strip()
            name = _extract_contact_name(event.tool_result)
            if qq and name:
                core.blackboard.write_entity(
                    "contact",
                    core._bb_scoped_key(f"contact:{qq}"),
                    {"qq": qq, "name": name},
                    event.tool_name,
                    0.8,
                )


class KnowledgeToolAdapter(ToolAdapter):
    tool_names = ("search_knowledge",)

    def apply(self, core, event: ToolEvent):
        parsed = _parse_structured_result(core, event)
        if parsed:
            query = str(parsed.get("query", "")).strip()
            result = str(parsed.get("result", "")).strip()
            if query:
                core.blackboard.write_entity(
                    "knowledge_query",
                    core._bb_scoped_key(f"knowledge:{query}"),
                    {"query": query, "result": result[:500]},
                    event.tool_name,
                    0.8,
                )
                return
        query = str(event.tool_args.get("query", "")).strip()
        if query:
            core.blackboard.write_entity(
                "knowledge_query",
                core._bb_scoped_key(f"knowledge:{query}"),
                {"query": query, "result": event.tool_result[:500]},
                event.tool_name,
                0.8,
            )


class SearchToolAdapter(ToolAdapter):
    tool_names = ("web_search", "search_and_read")

    def apply(self, core, event: ToolEvent):
        parsed = _parse_structured_result(core, event)
        if not parsed:
            return
        query = str(parsed.get("query", "")).strip()
        results = parsed.get("results") if isinstance(parsed.get("results"), list) else []
        if query:
            core.blackboard.write_entity(
                "search_query",
                core._bb_scoped_key(f"search:{query}"),
                {"query": query, "results": results, "result": str(parsed.get("result", ""))[:500]},
                event.tool_name,
                0.8,
            )


class WeatherToolAdapter(ToolAdapter):
    tool_names = ("get_weather",)

    def apply(self, core, event: ToolEvent):
        parsed = _parse_structured_result(core, event)
        if parsed:
            city = str(parsed.get("city", "")).strip()
            weather = str(parsed.get("weather", "")).strip()
            if city:
                core.blackboard.write_entity(
                    "location",
                    core._bb_scoped_key(f"city:{city}"),
                    {"city": city, "weather": weather[:300]},
                    event.tool_name,
                    0.8,
                )
                return
        city = str(event.tool_args.get("city", "")).strip()
        if city:
            core.blackboard.write_entity(
                "location",
                core._bb_scoped_key(f"city:{city}"),
                {"city": city, "weather": event.tool_result[:300]},
                event.tool_name,
                0.8,
            )


class GitHubToolAdapter(ToolAdapter):
    tool_names = (
        "github_watch_repo",
        "github_get_latest_commits",
        "github_get_branches",
        "github_get_repo_overview",
        "github_list_pull_requests",
        "github_list_issues",
    )

    def apply(self, core, event: ToolEvent):
        parsed = _parse_structured_result(core, event)
        repo = str((parsed or {}).get("repo", "")).strip() or str(event.tool_args.get("repo", "")).strip()
        if not repo:
            repo = _extract_repo_from_text(event.tool_result)
        branch = str((parsed or {}).get("branch", "")).strip() or str(event.tool_args.get("branch", "")).strip()
        if repo:
            core.blackboard.write_entity(
                "github_repo",
                core._bb_scoped_key(f"github:{repo}"),
                {"repo": repo, "branch": branch or "main"},
                event.tool_name,
                0.85,
            )


class MessageToolAdapter(ToolAdapter):
    tool_names = ("send_qq_message", "send_qq_group_message", "send_news_to_qq")

    def apply(self, core, event: ToolEvent):
        parsed = _parse_structured_result(core, event)
        if not parsed:
            return
        if event.tool_name == "send_qq_message":
            qq = str(parsed.get("qq_number", "")).strip()
            if qq:
                core.blackboard.write_entity(
                    "message_delivery",
                    core._bb_scoped_key(f"message:qq:{qq}"),
                    parsed,
                    event.tool_name,
                    0.8,
                )
        elif event.tool_name == "send_qq_group_message":
            group_id = str(parsed.get("group_id", "")).strip()
            if group_id:
                core.blackboard.write_entity(
                    "message_delivery",
                    core._bb_scoped_key(f"message:group:{group_id}"),
                    parsed,
                    event.tool_name,
                    0.8,
                )
        else:
            qq = str(parsed.get("qq_number", "")).strip()
            if qq:
                core.blackboard.write_entity(
                    "news_delivery",
                    core._bb_scoped_key(f"news_delivery:{qq}"),
                    parsed,
                    event.tool_name,
                    0.8,
                )


class NewsToolAdapter(ToolAdapter):
    tool_names = ("get_hot_news",)

    def apply(self, core, event: ToolEvent):
        parsed = _parse_structured_result(core, event)
        items = parsed.get("news_items") if parsed and isinstance(parsed.get("news_items"), list) else []
        if items:
            core.blackboard.write_entity(
                "news_digest",
                core._bb_scoped_key("news:latest"),
                {"items": items},
                event.tool_name,
                0.75,
            )


class MonitorToolAdapter(ToolAdapter):
    tool_names = ("add_site_monitor", "list_site_monitors", "check_site_now")

    def apply(self, core, event: ToolEvent):
        parsed = _parse_structured_result(core, event)
        if not parsed:
            return
        monitors = parsed.get("monitors") if isinstance(parsed.get("monitors"), list) else []
        for item in monitors:
            url = str(item.get("url", "")).strip()
            if url:
                core.blackboard.write_entity(
                    "site_monitor",
                    core._bb_scoped_key(f"site:{url}"),
                    item,
                    event.tool_name,
                    0.75,
                )
        if event.tool_name == "add_site_monitor":
            url = str(parsed.get("url", "")).strip()
            if url:
                core.blackboard.write_entity(
                    "site_monitor",
                    core._bb_scoped_key(f"site:{url}"),
                    parsed,
                    event.tool_name,
                    0.85,
                )
            return

        if event.tool_name == "check_site_now":
            url = str(parsed.get("url", "")).strip()
            if url:
                core.blackboard.write_entity(
                    "site_monitor_check",
                    core._bb_scoped_key(f"site_check:{url}"),
                    parsed,
                    event.tool_name,
                    0.8,
                )


class LocationToolAdapter(ToolAdapter):
    tool_names = ("ip_location", "phone_area")

    def apply(self, core, event: ToolEvent):
        parsed = _parse_structured_result(core, event)
        if not parsed:
            return
        if event.tool_name == "ip_location":
            ip = str(parsed.get("ip", "")).strip()
            if ip:
                core.blackboard.write_entity(
                    "ip_lookup",
                    core._bb_scoped_key(f"ip:{ip}"),
                    parsed,
                    event.tool_name,
                    0.75,
                )
        else:
            phone = str(parsed.get("phone", "")).strip()
            if phone:
                core.blackboard.write_entity(
                    "phone_lookup",
                    core._bb_scoped_key(f"phone:{phone}"),
                    parsed,
                    event.tool_name,
                    0.75,
                )


class NoteToolAdapter(ToolAdapter):
    tool_names = ("take_note", "list_notes", "search_notes", "append_note", "summarize_notes")

    def apply(self, core, event: ToolEvent):
        parsed = _parse_structured_result(core, event)
        if not parsed:
            return

        notes = parsed.get("notes") if isinstance(parsed.get("notes"), list) else []
        for item in notes:
            note_id = item.get("id")
            title = str(item.get("title", "")).strip()
            if note_id and title:
                core.blackboard.write_entity(
                    "note",
                    core._bb_scoped_key(f"note:{note_id}"),
                    item,
                    event.tool_name,
                    0.75,
                )

        if event.tool_name in ("take_note", "append_note"):
            note_id = parsed.get("note_id")
            title = str(parsed.get("title", "")).strip()
            if note_id and (title or event.tool_name == "append_note"):
                core.blackboard.write_entity(
                    "note",
                    core._bb_scoped_key(f"note:{note_id}"),
                    {
                        "id": note_id,
                        "title": title or f"note:{note_id}",
                        "tags": str(parsed.get("tags", "")).strip(),
                    },
                    event.tool_name,
                    0.9,
                )


class ReminderToolAdapter(ToolAdapter):
    tool_names = ("create_reminder", "list_reminders")

    def apply(self, core, event: ToolEvent):
        parsed = _parse_structured_result(core, event)
        if not parsed:
            return

        reminders = parsed.get("reminders") if isinstance(parsed.get("reminders"), list) else []
        for item in reminders:
            reminder_id = item.get("id")
            if reminder_id:
                core.blackboard.write_entity(
                    "reminder",
                    core._bb_scoped_key(f"reminder:{reminder_id}"),
                    item,
                    event.tool_name,
                    0.7,
                )

        if event.tool_name == "create_reminder":
            reminder_id = parsed.get("id")
            if reminder_id:
                core.blackboard.write_entity(
                    "reminder",
                    core._bb_scoped_key(f"reminder:{reminder_id}"),
                    parsed,
                    event.tool_name,
                    0.9,
                )


class DatabaseToolAdapter(ToolAdapter):
    tool_names = ("list_tables", "get_table_schema", "query_database")

    def apply(self, core, event: ToolEvent):
        parsed = _parse_structured_result(core, event)
        if not parsed:
            return

        if event.tool_name == "list_tables":
            keyword = str(parsed.get("keyword", "")).strip()
            tables = parsed.get("tables") if isinstance(parsed.get("tables"), list) else []
            if tables or keyword:
                core.blackboard.write_entity(
                    "database_catalog",
                    core._bb_scoped_key(f"db:tables:{keyword or 'all'}"),
                    {"keyword": keyword, "tables": tables},
                    event.tool_name,
                    0.8,
                )
            return

        if event.tool_name == "get_table_schema":
            table_name = str(parsed.get("table_name", "")).strip()
            if table_name:
                core.blackboard.write_entity(
                    "database_schema",
                    core._bb_scoped_key(f"db:schema:{table_name}"),
                    {
                        "table_name": table_name,
                        "fields": parsed.get("fields", []),
                        "result": str(parsed.get("result", ""))[:500],
                    },
                    event.tool_name,
                    0.85,
                )
            return

        sql = str(parsed.get("sql", "")).strip()
        if sql:
            core.blackboard.write_entity(
                "database_query",
                core._bb_scoped_key(f"db:query:{abs(hash(sql))}"),
                {
                    "sql": sql,
                    "columns": parsed.get("columns", []),
                    "rows": parsed.get("rows", []),
                    "result": str(parsed.get("result", ""))[:500],
                },
                event.tool_name,
                0.8,
            )


class WorkflowToolAdapter(ToolAdapter):
    tool_names = (
        "create_workflow",
        "list_workflows",
        "toggle_workflow",
        "run_workflow_now",
        "describe_workflow",
        "clone_workflow",
    )

    def apply(self, core, event: ToolEvent):
        parsed = _parse_structured_result(core, event)
        if not parsed:
            return

        workflows = parsed.get("workflows") if isinstance(parsed.get("workflows"), list) else []
        for item in workflows:
            workflow_id = item.get("id")
            name = str(item.get("name", "")).strip()
            if workflow_id and name:
                core.blackboard.write_entity(
                    "workflow",
                    core._bb_scoped_key(f"workflow:{workflow_id}"),
                    item,
                    event.tool_name,
                    0.75,
                )

        if event.tool_name in ("create_workflow", "clone_workflow"):
            workflow_id = parsed.get("id") or parsed.get("workflow_id")
            name = str(parsed.get("name", "")).strip()
            if workflow_id and name:
                core.blackboard.write_entity(
                    "workflow",
                    core._bb_scoped_key(f"workflow:{workflow_id}"),
                    parsed,
                    event.tool_name,
                    0.9,
                )
            return

        if event.tool_name == "toggle_workflow":
            workflow_id = parsed.get("workflow_id")
            if workflow_id:
                core.blackboard.write_entity(
                    "workflow",
                    core._bb_scoped_key(f"workflow:{workflow_id}"),
                    parsed,
                    event.tool_name,
                    0.7,
                )
            return

        if event.tool_name == "run_workflow_now":
            workflow_id = parsed.get("workflow_id")
            if workflow_id:
                core.blackboard.write_entity(
                    "workflow_run",
                    core._bb_scoped_key(f"workflow_run:{workflow_id}"),
                    parsed,
                    event.tool_name,
                    0.75,
                )


def build_default_tool_adapters() -> list[ToolAdapter]:
    return [
        ContactToolAdapter(),
        KnowledgeToolAdapter(),
        SearchToolAdapter(),
        WeatherToolAdapter(),
        GitHubToolAdapter(),
        MessageToolAdapter(),
        NewsToolAdapter(),
        MonitorToolAdapter(),
        LocationToolAdapter(),
        NoteToolAdapter(),
        ReminderToolAdapter(),
        DatabaseToolAdapter(),
        WorkflowToolAdapter(),
    ]


def dispatch_tool_adapters(core, event: ToolEvent, adapters: list[ToolAdapter]):
    for adapter in adapters:
        if adapter.supports(event.tool_name):
            adapter.apply(core, event)


def _extract_contact_pairs(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in text.splitlines():
        match = re.search(r"QQ\s*([0-9]{5,})\s*(?:->|\|)\s*([^\|\n]+)", line)
        if match:
            qq = match.group(1).strip()
            name = match.group(2).strip()
            if name and name != "未命名":
                pairs.append((qq, name))
    return pairs


def _extract_contact_name(text: str) -> str:
    for line in text.splitlines():
        match = re.search(r"名称:\s*(.+)", line)
        if match:
            return match.group(1).strip()
    return ""


def _extract_repo_from_text(text: str) -> str:
    match = re.search(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", text)
    return match.group(1) if match else ""


def _parse_structured_result(core, event: ToolEvent) -> dict | None:
    if isinstance(event.structured_result, dict):
        return event.structured_result

    definitions = getattr(core, "tool_definitions", {}) or {}
    tool_def = definitions.get(event.tool_name)
    parser = getattr(tool_def, "result_parser", None) if tool_def else None
    if not parser:
        return None
    try:
        parsed = parser(event.tool_args, event.tool_result)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None
