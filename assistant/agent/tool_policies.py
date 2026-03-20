"""
Tool Policy 层

负责工具执行前的统一策略校验。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToolPolicyContext:
    tool_name: str
    tool_args: dict
    tool_metadata: dict
    session_context: dict


class ToolPolicy:
    def apply(self, ctx: ToolPolicyContext) -> str | None:
        raise NotImplementedError


class RequiredFieldsPolicy(ToolPolicy):
    def apply(self, ctx: ToolPolicyContext) -> str | None:
        for required_key in ctx.tool_metadata.get("required_all", []):
            if not str(ctx.tool_args.get(required_key, "")).strip():
                return f"策略阻止执行: 工具 {ctx.tool_name} 缺少参数 {required_key}。"

        for group in ctx.tool_metadata.get("required_any", []):
            if not any(str(ctx.tool_args.get(key, "")).strip() for key in group):
                joined = "/".join(group)
                return f"策略阻止执行: 工具 {ctx.tool_name} 缺少必要参数组 {joined}。"
        return None


class SessionContextPolicy(ToolPolicy):
    def apply(self, ctx: ToolPolicyContext) -> str | None:
        if ctx.tool_metadata.get("session_required"):
            if not str(ctx.tool_args.get("user_qq", "")).strip() and not str(ctx.session_context.get("user_qq", "")).strip():
                return f"策略阻止执行: 工具 {ctx.tool_name} 缺少管理员身份上下文。"
        return None


class ExternalMessagePolicy(ToolPolicy):
    def apply(self, ctx: ToolPolicyContext) -> str | None:
        if ctx.tool_metadata.get("side_effect") == "external_message":
            if not str(ctx.tool_args.get("content", "")).strip():
                return f"策略阻止执行: 工具 {ctx.tool_name} 缺少消息内容。"
        return None


def build_default_tool_policies() -> list[ToolPolicy]:
    return [
        RequiredFieldsPolicy(),
        SessionContextPolicy(),
        ExternalMessagePolicy(),
    ]


def apply_tool_policies(
    tool_name: str,
    tool_args: dict,
    tool_metadata: dict,
    session_context: dict,
    policies: list[ToolPolicy],
) -> str | None:
    ctx = ToolPolicyContext(
        tool_name=tool_name,
        tool_args=tool_args,
        tool_metadata=tool_metadata,
        session_context=session_context,
    )
    for policy in policies:
        result = policy.apply(ctx)
        if result:
            return result
    return None
