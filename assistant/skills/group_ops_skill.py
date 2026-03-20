"""群运营 Skill - 高层联系人/群通知动作"""

from __future__ import annotations

import os
from datetime import datetime

import httpx

from assistant.agent.contacts_db import load_groups, load_users
from assistant.skills.base import BaseSkill, ToolDefinition, register

NAPCAT_API_URL = os.getenv("NAPCAT_API_URL", "http://127.0.0.1:3000")


def _find_contact_by_name(name: str) -> tuple[str, str] | None:
    keyword = name.strip().lower()
    if not keyword:
        return None
    for qq, info in load_users().items():
        custom_name = str(info.get("name", "")).strip()
        nickname = str(info.get("nickname", "")).strip()
        haystacks = [custom_name.lower(), nickname.lower()]
        if any(keyword in h for h in haystacks if h):
            return qq, custom_name or nickname or qq
    return None


def _find_group_by_name(name: str) -> tuple[str, str] | None:
    keyword = name.strip().lower()
    if not keyword:
        return None
    for group_id, info in load_groups().items():
        custom_name = str(info.get("name", "")).strip()
        group_name = str(info.get("group_name", "")).strip()
        haystacks = [custom_name.lower(), group_name.lower()]
        if any(keyword in h for h in haystacks if h):
            return group_id, custom_name or group_name or group_id
    return None


def _find_recent_contact() -> tuple[str, str] | None:
    best = None
    best_key = ("", -1)
    for qq, info in load_users().items():
        display = str(info.get("name", "")).strip() or str(info.get("nickname", "")).strip() or qq
        last_seen = str(info.get("last_seen", "")).strip()
        msg_count = int(info.get("msg_count", 0) or 0)
        sort_key = (last_seen, msg_count)
        if best is None or sort_key > best_key:
            best = (qq, display)
            best_key = sort_key
    return best


class GroupOpsSkill(BaseSkill):
    name = "group_ops"
    description = "联系人/群通知高层动作，减少多步工具链"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="notify_contact_by_name",
                description="按联系人名字查找 QQ 并发送私聊消息。",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "联系人名称或昵称"},
                        "content": {"type": "string", "description": "要发送的消息内容", "default": ""},
                    },
                    "required": ["name"],
                },
                handler=self._notify_contact_by_name,
                metadata={
                    "category": "notify",
                    "side_effect": "external_message",
                    "blackboard_reads": ["last_result", "contact"],
                    "blackboard_writes": ["last_target_qq"],
                    "required_all": ["name", "content"],
                    "store_args": {"content": "last_shared_result"},
                },
                keywords=["联系人", "私聊", "通知", "发消息", "按名字发送"],
                intents=["notify_person", "send_private_message", "contact_lookup"],
            ),
            ToolDefinition(
                name="notify_group_by_name",
                description="按群名称查找群号并发送群消息，可选按联系人名字 @ 某人。",
                parameters={
                    "type": "object",
                    "properties": {
                        "group_name": {"type": "string", "description": "群名称"},
                        "content": {"type": "string", "description": "消息内容", "default": ""},
                        "at_name": {"type": "string", "description": "要@的联系人名称（可选）", "default": ""},
                    },
                    "required": ["group_name"],
                },
                handler=self._notify_group_by_name,
                metadata={
                    "category": "notify",
                    "side_effect": "external_message",
                    "blackboard_reads": ["last_result", "contact"],
                    "blackboard_writes": ["last_target_group", "last_target_qq"],
                    "required_all": ["group_name", "content"],
                    "store_args": {"content": "last_shared_result"},
                },
                keywords=["群通知", "群发", "艾特", "@某人", "按群名发送"],
                intents=["notify_group", "send_group_message", "group_lookup"],
            ),
            ToolDefinition(
                name="broadcast_last_result",
                description="把最近一次结果广播到当前群或指定群，可选 @ 某个 QQ。",
                parameters={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "要广播的内容，留空则由系统补全最近结果", "default": ""},
                        "group_id": {"type": "string", "description": "目标群号，留空则由系统补全", "default": ""},
                        "at_qq": {"type": "string", "description": "要@的QQ号（可选）", "default": ""},
                    },
                },
                handler=self._broadcast_last_result,
                metadata={
                    "category": "notify",
                    "side_effect": "external_message",
                    "blackboard_reads": ["last_result", "target_group", "target_user"],
                    "blackboard_writes": ["last_target_group", "last_target_qq"],
                    "required_all": ["content"],
                    "required_any": [["group_id"]],
                    "store_args": {
                        "group_id": "last_target_group",
                        "at_qq": "last_target_qq",
                        "content": "last_shared_result",
                    },
                },
                keywords=["广播结果", "转发刚才结果", "发到群里", "同步结果"],
                intents=["broadcast_result", "share_last_result"],
            ),
            ToolDefinition(
                name="notify_recent_contact",
                description="给最近互动的联系人发送私聊消息。",
                parameters={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "要发送的消息内容"},
                    },
                    "required": ["content"],
                },
                handler=self._notify_recent_contact,
                metadata={
                    "category": "notify",
                    "side_effect": "external_message",
                    "blackboard_reads": ["contact", "last_result"],
                    "required_all": ["content"],
                    "store_args": {"content": "last_shared_result"},
                },
                keywords=["最近联系人", "通知最近的人", "发给刚聊过的人"],
                intents=["notify_recent_contact"],
            ),
            ToolDefinition(
                name="broadcast_workflow_result",
                description="把某个工作流最近一次执行结果发送到群里。",
                parameters={
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "integer", "description": "工作流ID"},
                        "group_id": {"type": "string", "description": "目标群号，留空则由系统补全", "default": ""},
                        "at_qq": {"type": "string", "description": "要@的QQ号（可选）", "default": ""},
                    },
                    "required": ["workflow_id"],
                },
                handler=self._broadcast_workflow_result,
                metadata={
                    "category": "notify",
                    "side_effect": "external_message",
                    "blackboard_reads": ["workflow", "target_group", "target_user"],
                    "required_all": ["workflow_id"],
                    "required_any": [["group_id"]],
                    "store_args": {
                        "group_id": "last_target_group",
                        "at_qq": "last_target_qq",
                    },
                },
                keywords=["广播工作流结果", "发送自动化结果", "把任务结果发群里"],
                intents=["broadcast_workflow_result"],
            ),
        ]

    def _notify_contact_by_name(self, name: str, content: str = "") -> str:
        if not content.strip():
            return "没有可发送的内容。"
        found = _find_contact_by_name(name)
        if not found:
            return f"未找到名称包含 '{name}' 的联系人。"
        qq, display_name = found

        try:
            resp = httpx.post(
                f"{NAPCAT_API_URL}/send_private_msg",
                json={
                    "user_id": int(qq),
                    "message": [{"type": "text", "data": {"text": content}}],
                },
                timeout=10,
            )
            data = resp.json()
        except Exception as e:
            return f"发送失败: {e}"

        if data.get("status") == "ok" or data.get("retcode") == 0:
            return f"消息已发送给 {display_name} (QQ:{qq})"
        return f"发送失败: {data.get('message', data.get('wording', '未知错误'))}"

    def _notify_group_by_name(self, group_name: str, content: str = "", at_name: str = "") -> str:
        if not content.strip():
            return "没有可发送的内容。"
        found_group = _find_group_by_name(group_name)
        if not found_group:
            return f"未找到名称包含 '{group_name}' 的群。"
        group_id, display_group = found_group

        at_qq = ""
        if at_name.strip():
            found_contact = _find_contact_by_name(at_name)
            if not found_contact:
                return f"未找到名称包含 '{at_name}' 的联系人。"
            at_qq = found_contact[0]

        return self._send_group_message(group_id, content, at_qq=at_qq, display_group=display_group)

    def _broadcast_last_result(self, content: str = "", group_id: str = "", at_qq: str = "") -> str:
        if not group_id.strip():
            return "缺少群号，无法广播。"
        if not content.strip():
            return "没有可广播的内容。"
        return self._send_group_message(group_id, content, at_qq=at_qq, display_group=group_id)

    def _notify_recent_contact(self, content: str) -> str:
        if not content.strip():
            return "没有可发送的内容。"
        found = _find_recent_contact()
        if not found:
            return "暂无最近联系人可通知。"
        qq, display_name = found
        try:
            resp = httpx.post(
                f"{NAPCAT_API_URL}/send_private_msg",
                json={
                    "user_id": int(qq),
                    "message": [{"type": "text", "data": {"text": content}}],
                },
                timeout=10,
            )
            data = resp.json()
        except Exception as e:
            return f"发送失败: {e}"
        if data.get("status") == "ok" or data.get("retcode") == 0:
            return f"消息已发送给最近联系人 {display_name} (QQ:{qq})"
        return f"发送失败: {data.get('message', data.get('wording', '未知错误'))}"

    def _broadcast_workflow_result(self, workflow_id: int, group_id: str = "", at_qq: str = "") -> str:
        if not group_id.strip():
            return "缺少群号，无法广播工作流结果。"
        try:
            from assistant.agent import db_workflow
            wf = db_workflow.workflow_get(workflow_id)
        except Exception as e:
            return f"查询工作流失败: {e}"
        if not wf:
            return f"未找到 ID 为 {workflow_id} 的工作流。"
        content = str(wf.get("last_result", "")).strip()
        if not content:
            return f"工作流 {workflow_id} 暂无最近执行结果。"
        header = f"[工作流结果] {wf.get('name', workflow_id)}\n"
        return self._send_group_message(group_id, header + content[:1200], at_qq=at_qq, display_group=group_id)

    def _send_group_message(self, group_id: str, content: str, at_qq: str = "", display_group: str = "") -> str:
        message = []
        if at_qq:
            message.append({"type": "at", "data": {"qq": at_qq}})
            message.append({"type": "text", "data": {"text": " "}})
        message.append({"type": "text", "data": {"text": content}})

        try:
            resp = httpx.post(
                f"{NAPCAT_API_URL}/send_group_msg",
                json={"group_id": int(group_id), "message": message},
                timeout=10,
            )
            data = resp.json()
        except Exception as e:
            return f"发送失败: {e}"

        if data.get("status") == "ok" or data.get("retcode") == 0:
            at_str = f"，并@QQ:{at_qq}" if at_qq else ""
            return f"消息已发送到群 {display_group or group_id}{at_str}"
        return f"发送失败: {data.get('message', data.get('wording', '未知错误'))}"


register(GroupOpsSkill)
