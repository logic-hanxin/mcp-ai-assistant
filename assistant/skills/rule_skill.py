"""守则管理 Skill - 小彩云的行为守则"""

from __future__ import annotations

import os

from assistant.runtime_context import get_current_user_qq
from assistant.skills.base import BaseSkill, ToolDefinition, register


# 管理员QQ号，可以修改守则
RULE_ADMIN_QQ = os.getenv("RULE_ADMIN_QQ", os.getenv("QQ_ADMIN", ""))


class RuleSkill(BaseSkill):
    name = "rule"
    description = "管理小彩云的行为守则"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="add_rule",
                description=(
                    "添加一条守则。当用户告诉你需要遵守某个规则、行为准则、注意事项时，"
                    "主动调用此工具将其写入守则。守则一旦写入，你之后的所有回复都必须遵守。"
                    "⚠️ 只有管理员才能添加守则。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "守则标题，简短概括（如: 不讨论政治、称呼规范）",
                        },
                        "content": {
                            "type": "string",
                            "description": "守则的详细内容和要求",
                        },
                    },
                    "required": ["title", "content"],
                },
                handler=self._add_rule,
                metadata={
                    "category": "admin",
                    "side_effect": "admin_operation",
                    "blackboard_reads": ["target_user"],
                    "required_all": ["title", "content"],
                    "session_required": True,
                },
                keywords=["添加规则", "写入守则", "新增准则"],
                intents=["add_rule"],
            ),
            ToolDefinition(
                name="list_rules",
                description="查看当前所有守则列表。所有人都可以使用。",
                parameters={
                    "type": "object",
                    "properties": {},
                },
                handler=self._list_rules,
                metadata={
                    "category": "read",
                },
                keywords=["查看守则", "规则列表", "当前准则"],
                intents=["list_rules"],
            ),
            ToolDefinition(
                name="delete_rule",
                description="删除一条守则。需要提供守则的 ID 号。⚠️ 只有管理员才能删除守则。",
                parameters={
                    "type": "object",
                    "properties": {
                        "rule_id": {
                            "type": "integer",
                            "description": "要删除的守则 ID",
                        },
                    },
                    "required": ["rule_id"],
                },
                handler=self._delete_rule,
                metadata={
                    "category": "admin",
                    "side_effect": "admin_operation",
                    "blackboard_reads": ["target_user"],
                    "required_all": ["rule_id"],
                    "session_required": True,
                },
                keywords=["删除规则", "移除守则"],
                intents=["delete_rule"],
            ),
        ]

    def _check_admin(self, user_qq: str = "") -> bool:
        """检查是否是管理员"""
        if not RULE_ADMIN_QQ:
            # 没配置管理员，任何人都可以修改（但这不安全）
            return True
        admins = [a.strip() for a in RULE_ADMIN_QQ.split(",") if a.strip()]
        return user_qq in admins

    def _add_rule(self, title: str, content: str, user_qq: str = "") -> str:
        """添加守则"""
        current_user = get_current_user_qq(user_qq)

        if not self._check_admin(current_user):
            return f"❌ 只有管理员才能添加守则。你的QQ号: {current_user}"

        try:
            from assistant.agent.db_misc import save_rule
            rule_id = save_rule(title, content)
            return f"守则已添加 (ID: {rule_id}):\n标题: {title}\n内容: {content}"
        except Exception as e:
            return f"守则添加失败: {e}"

    def _list_rules(self) -> str:
        """列出守则"""
        try:
            from assistant.agent.db_misc import load_rules
            rules = load_rules()
            if not rules:
                return "当前没有任何守则。"
            lines = []
            for r in rules:
                lines.append(f"[ID:{r['id']}] {r['title']}: {r['content']}")
            return f"当前共 {len(rules)} 条守则:\n" + "\n".join(lines)
        except Exception as e:
            return f"查询守则失败: {e}"

    def _delete_rule(self, rule_id: int, user_qq: str = "") -> str:
        """删除守则"""
        current_user = get_current_user_qq(user_qq)

        if not self._check_admin(current_user):
            return f"❌ 只有管理员才能删除守则。你的QQ号: {current_user}"

        try:
            from assistant.agent.db_misc import delete_rule
            if delete_rule(rule_id):
                return f"守则 ID:{rule_id} 已删除。"
            return f"未找到 ID:{rule_id} 的守则。"
        except Exception as e:
            return f"删除守则失败: {e}"


register(RuleSkill)
