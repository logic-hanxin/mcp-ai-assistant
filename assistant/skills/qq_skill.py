"""QQ 消息 Skill - 通过 NapCat 给指定 QQ 用户发送消息"""

import os
import httpx
from assistant.skills.base import BaseSkill, ToolDefinition, register

NAPCAT_API_URL = os.getenv("NAPCAT_API_URL", "http://127.0.0.1:3000")


class QQMessageSkill(BaseSkill):
    name = "qq_message"
    description = "通过QQ给指定用户或群发送消息"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="send_qq_message",
                description=(
                    "给指定QQ号的用户发送一条私聊消息。"
                    "可用于主动通知、转达消息等场景。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "qq_number": {
                            "type": "string",
                            "description": "接收消息的QQ号",
                        },
                        "content": {
                            "type": "string",
                            "description": "消息内容",
                        },
                    },
                    "required": ["qq_number", "content"],
                },
                handler=self._send_private,
                metadata={
                    "category": "notify",
                    "side_effect": "external_message",
                    "blackboard_reads": ["target_user"],
                    "blackboard_writes": ["last_target_qq"],
                    "required_all": ["content"],
                    "required_any": [["qq_number"]],
                    "store_args": {"qq_number": "last_target_qq", "content": "last_shared_result"},
                },
                result_parser=self._parse_send_private_result,
                keywords=["私聊发送", "发QQ消息", "通知某人", "发私信"],
                intents=["send_private_message"],
            ),
            ToolDefinition(
                name="send_qq_group_message",
                description=(
                    "在指定QQ群发送一条消息，可选@某个群成员。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "group_id": {
                            "type": "string",
                            "description": "QQ群号",
                        },
                        "content": {
                            "type": "string",
                            "description": "消息内容",
                        },
                        "at_qq": {
                            "type": "string",
                            "description": "要@的QQ号（可选）",
                            "default": "",
                        },
                    },
                    "required": ["group_id", "content"],
                },
                handler=self._send_group,
                metadata={
                    "category": "notify",
                    "side_effect": "external_message",
                    "blackboard_reads": ["target_group", "target_user"],
                    "blackboard_writes": ["last_target_group", "last_target_qq"],
                    "required_all": ["content"],
                    "required_any": [["group_id"]],
                    "store_args": {
                        "group_id": "last_target_group",
                        "at_qq": "last_target_qq",
                        "content": "last_shared_result",
                    },
                },
                result_parser=self._parse_send_group_result,
                keywords=["群消息", "发群通知", "群里发送", "艾特群成员"],
                intents=["send_group_message"],
            ),
        ]

    def _send_private(self, qq_number: str, content: str) -> str:
        """同步发送私聊消息（MCP 工具在同步上下文中运行）"""
        try:
            resp = httpx.post(
                f"{NAPCAT_API_URL}/send_private_msg",
                json={
                    "user_id": int(qq_number),
                    "message": [{"type": "text", "data": {"text": content}}],
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "ok" or data.get("retcode") == 0:
                return f"消息已发送给 QQ:{qq_number}"
            return f"发送失败: {data.get('message', data.get('wording', '未知错误'))}"
        except Exception as e:
            return f"发送失败: {e}"

    def _send_group(self, group_id: str, content: str, at_qq: str = "") -> str:
        """同步发送群消息"""
        try:
            message = []
            if at_qq:
                message.append({"type": "at", "data": {"qq": at_qq}})
                message.append({"type": "text", "data": {"text": " "}})
            message.append({"type": "text", "data": {"text": content}})

            resp = httpx.post(
                f"{NAPCAT_API_URL}/send_group_msg",
                json={"group_id": int(group_id), "message": message},
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "ok" or data.get("retcode") == 0:
                at_str = f"(@{at_qq})" if at_qq else ""
                return f"消息已发送到群 {group_id} {at_str}"
            return f"发送失败: {data.get('message', data.get('wording', '未知错误'))}"
        except Exception as e:
            return f"发送失败: {e}"

    def _parse_send_private_result(self, args: dict, result: str) -> dict | None:
        return {
            "target_type": "private",
            "qq_number": str(args.get("qq_number", "")).strip(),
            "content": str(args.get("content", "")).strip(),
            "delivered": "已发送" in result,
            "result": result[:300],
        }

    def _parse_send_group_result(self, args: dict, result: str) -> dict | None:
        return {
            "target_type": "group",
            "group_id": str(args.get("group_id", "")).strip(),
            "at_qq": str(args.get("at_qq", "")).strip(),
            "content": str(args.get("content", "")).strip(),
            "delivered": "已发送" in result,
            "result": result[:300],
        }


register(QQMessageSkill)
