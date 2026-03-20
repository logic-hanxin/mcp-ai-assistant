"""
Tool Hydrator 层

负责在工具执行前，结合会话上下文和黑板结果补全缺失参数。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToolHydrationContext:
    tool_name: str
    tool_args: dict
    session_user: str
    session_group: str
    session_image: str
    session_file: str
    bb_user: str
    bb_group: str
    bb_repo: str
    bb_branch: str
    bb_city: str
    bb_image: str
    bb_file: str
    shareable_text: str


class ToolHydrator:
    def supports(self, tool_name: str) -> bool:
        raise NotImplementedError

    def apply(self, ctx: ToolHydrationContext) -> dict:
        raise NotImplementedError


class ReminderHydrator(ToolHydrator):
    def supports(self, tool_name: str) -> bool:
        return tool_name == "create_reminder"

    def apply(self, ctx: ToolHydrationContext) -> dict:
        args = dict(ctx.tool_args)
        _fill_if_empty(args, "notify_qq", ctx.session_user or ctx.bb_user)
        _fill_if_empty(args, "notify_group_id", ctx.session_group or ctx.bb_group)
        return args


class MessageHydrator(ToolHydrator):
    def supports(self, tool_name: str) -> bool:
        return tool_name in ("send_qq_message", "send_qq_group_message")

    def apply(self, ctx: ToolHydrationContext) -> dict:
        args = dict(ctx.tool_args)
        if ctx.tool_name == "send_qq_message":
            _fill_if_empty(args, "qq_number", ctx.bb_user or ctx.session_user)
        else:
            _fill_if_empty(args, "group_id", ctx.session_group or ctx.bb_group)
            _fill_if_empty(args, "at_qq", ctx.session_user or ctx.bb_user)
        return args


class GitHubHydrator(ToolHydrator):
    def supports(self, tool_name: str) -> bool:
        return tool_name in (
            "github_watch_repo",
            "github_get_latest_commits",
            "github_get_branches",
            "github_unwatch_repo",
        )

    def apply(self, ctx: ToolHydrationContext) -> dict:
        args = dict(ctx.tool_args)
        if ctx.tool_name == "github_watch_repo":
            _fill_if_empty(args, "notify_qq", ctx.session_user or ctx.bb_user)
            _fill_if_empty(args, "repo", ctx.bb_repo)
            _fill_if_empty(args, "branch", ctx.bb_branch or "main")
        else:
            _fill_if_empty(args, "repo", ctx.bb_repo)
            if ctx.tool_name == "github_get_latest_commits":
                _fill_if_empty(args, "branch", ctx.bb_branch or "main")
        return args


class WeatherHydrator(ToolHydrator):
    def supports(self, tool_name: str) -> bool:
        return tool_name == "get_weather"

    def apply(self, ctx: ToolHydrationContext) -> dict:
        args = dict(ctx.tool_args)
        _fill_if_empty(args, "city", ctx.bb_city)
        return args


class VisionHydrator(ToolHydrator):
    def supports(self, tool_name: str) -> bool:
        return tool_name in ("ocr_image", "understand_image", "scan_qrcode")

    def apply(self, ctx: ToolHydrationContext) -> dict:
        args = dict(ctx.tool_args)
        _fill_if_empty(args, "image_url", ctx.session_image or ctx.bb_image)
        return args


class DocumentHydrator(ToolHydrator):
    def supports(self, tool_name: str) -> bool:
        return tool_name in ("parse_document", "import_document", "read_file")

    def apply(self, ctx: ToolHydrationContext) -> dict:
        args = dict(ctx.tool_args)
        fallback_file = ctx.session_file or ctx.bb_file
        current_file = str(args.get("file_path", "")).strip()
        if _should_replace_document_path(current_file, fallback_file):
            args["file_path"] = fallback_file
        else:
            _fill_if_empty(args, "file_path", fallback_file)
        return args


class RuleHydrator(ToolHydrator):
    def supports(self, tool_name: str) -> bool:
        return tool_name in ("add_rule", "delete_rule")

    def apply(self, ctx: ToolHydrationContext) -> dict:
        args = dict(ctx.tool_args)
        _fill_if_empty(args, "user_qq", ctx.session_user or ctx.bb_user)
        return args


class GroupOpsHydrator(ToolHydrator):
    def supports(self, tool_name: str) -> bool:
        return tool_name in ("notify_contact_by_name", "notify_group_by_name", "broadcast_last_result")

    def apply(self, ctx: ToolHydrationContext) -> dict:
        args = dict(ctx.tool_args)
        if ctx.tool_name in ("notify_contact_by_name", "notify_group_by_name"):
            _fill_if_empty(args, "content", ctx.shareable_text)
        else:
            _fill_if_empty(args, "content", ctx.shareable_text)
            _fill_if_empty(args, "group_id", ctx.session_group or ctx.bb_group)
            _fill_if_empty(args, "at_qq", ctx.session_user or ctx.bb_user)
        return args


def build_default_tool_hydrators() -> list[ToolHydrator]:
    return [
        ReminderHydrator(),
        MessageHydrator(),
        GitHubHydrator(),
        WeatherHydrator(),
        VisionHydrator(),
        DocumentHydrator(),
        RuleHydrator(),
        GroupOpsHydrator(),
    ]


def hydrate_tool_args(ctx: ToolHydrationContext, hydrators: list[ToolHydrator]) -> dict:
    args = dict(ctx.tool_args)
    for hydrator in hydrators:
        if hydrator.supports(ctx.tool_name):
            next_ctx = ToolHydrationContext(
                tool_name=ctx.tool_name,
                tool_args=args,
                session_user=ctx.session_user,
                session_group=ctx.session_group,
                session_image=ctx.session_image,
                session_file=ctx.session_file,
                bb_user=ctx.bb_user,
                bb_group=ctx.bb_group,
                bb_repo=ctx.bb_repo,
                bb_branch=ctx.bb_branch,
                bb_city=ctx.bb_city,
                bb_image=ctx.bb_image,
                bb_file=ctx.bb_file,
                shareable_text=ctx.shareable_text,
            )
            args = hydrator.apply(next_ctx)
    return args


def _fill_if_empty(args: dict, key: str, value: str):
    if value and not str(args.get(key, "")).strip():
        args[key] = value


def _should_replace_document_path(current_path: str, fallback_path: str) -> bool:
    if not fallback_path:
        return False
    current_path = (current_path or "").strip()
    if not current_path:
        return False
    if current_path.startswith("http://") or current_path.startswith("https://"):
        return False

    suspicious_markers = (
        "/.config/QQ/NapCat/",
        "/app/.config/QQ/NapCat/",
        "NapCat/temp/",
        "\\NapCat\\temp\\",
    )
    return any(marker in current_path for marker in suspicious_markers)
