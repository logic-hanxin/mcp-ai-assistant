"""通讯录 Skill - QQ号关联用户名、群号关联群名"""

from assistant.skills.base import BaseSkill, ToolDefinition, register
from assistant.agent.contacts_db import (
    load_users, save_users, load_groups, save_groups,
    get_user_display_name, _ensure_dir,
)


class ContactsSkill(BaseSkill):
    name = "contacts"
    description = "通讯录管理，QQ号关联用户名、群号关联群名，自动记录交流对象"

    def on_load(self):
        _ensure_dir()

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="set_user_name",
                description="设置QQ号对应的用户名称（昵称）。以后提到该用户时会显示名称而非QQ号。",
                parameters={
                    "type": "object",
                    "properties": {
                        "qq_number": {"type": "string", "description": "QQ号"},
                        "name": {"type": "string", "description": "用户名称/昵称"},
                    },
                    "required": ["qq_number", "name"],
                },
                handler=self._set_user,
            ),
            ToolDefinition(
                name="get_user_name",
                description="根据QQ号查询用户名称和交互记录。",
                parameters={
                    "type": "object",
                    "properties": {
                        "qq_number": {"type": "string", "description": "QQ号"},
                    },
                    "required": ["qq_number"],
                },
                handler=self._get_user,
            ),
            ToolDefinition(
                name="set_group_name",
                description="设置群号对应的群名称。",
                parameters={
                    "type": "object",
                    "properties": {
                        "group_id": {"type": "string", "description": "群号"},
                        "name": {"type": "string", "description": "群名称"},
                    },
                    "required": ["group_id", "name"],
                },
                handler=self._set_group,
            ),
            ToolDefinition(
                name="list_contacts",
                description="列出所有已保存的用户和群信息，包含交互统计。",
                parameters={"type": "object", "properties": {}},
                handler=self._list_contacts,
            ),
            ToolDefinition(
                name="find_qq_by_name",
                description="根据用户名称查找对应的QQ号。",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "要查找的用户名称"},
                    },
                    "required": ["name"],
                },
                handler=self._find_qq,
            ),
        ]

    def _set_user(self, qq_number: str, name: str) -> str:
        users = load_users()
        if qq_number in users:
            users[qq_number]["name"] = name
        else:
            users[qq_number] = {
                "name": name, "nickname": "", "first_seen": "", "last_seen": "", "msg_count": 0,
            }
        save_users(users)
        return f"已保存: QQ {qq_number} -> {name}"

    def _get_user(self, qq_number: str) -> str:
        users = load_users()
        user = users.get(qq_number)
        if not user:
            return f"未找到 QQ {qq_number} 的记录。"
        display = user.get("name") or user.get("nickname") or "未命名"
        lines = [f"QQ {qq_number} 的信息:"]
        lines.append(f"  名称: {display}")
        if user.get("nickname"):
            lines.append(f"  QQ昵称: {user['nickname']}")
        if user.get("first_seen"):
            lines.append(f"  首次交流: {user['first_seen']}")
        if user.get("last_seen"):
            lines.append(f"  最近交流: {user['last_seen']}")
        lines.append(f"  消息数量: {user.get('msg_count', 0)}")
        return "\n".join(lines)

    def _set_group(self, group_id: str, name: str) -> str:
        groups = load_groups()
        if group_id in groups:
            groups[group_id]["name"] = name
        else:
            groups[group_id] = {
                "name": name, "group_name": "", "first_seen": "", "last_seen": "", "msg_count": 0,
            }
        save_groups(groups)
        return f"已保存: 群 {group_id} -> {name}"

    def _list_contacts(self) -> str:
        users = load_users()
        groups = load_groups()
        lines = []

        if users:
            lines.append(f"用户列表 ({len(users)} 人):")
            # 按最近交流时间排序
            sorted_users = sorted(
                users.items(),
                key=lambda x: x[1].get("last_seen", ""),
                reverse=True,
            )
            for qq, info in sorted_users:
                display = info.get("name") or info.get("nickname") or "未命名"
                count = info.get("msg_count", 0)
                last = info.get("last_seen", "")
                if last:
                    last = last[:16].replace("T", " ")
                lines.append(f"  QQ {qq} | {display} | {count}条消息 | 最近:{last}")
        else:
            lines.append("暂无用户记录。")

        if groups:
            lines.append(f"\n群列表 ({len(groups)} 个):")
            sorted_groups = sorted(
                groups.items(),
                key=lambda x: x[1].get("last_seen", ""),
                reverse=True,
            )
            for gid, info in sorted_groups:
                display = info.get("name") or info.get("group_name") or "未命名"
                count = info.get("msg_count", 0)
                lines.append(f"  群 {gid} | {display} | {count}条消息")
        else:
            lines.append("\n暂无群记录。")

        return "\n".join(lines)

    def _find_qq(self, name: str) -> str:
        users = load_users()
        results = []
        for qq, info in users.items():
            uname = info.get("name", "")
            nickname = info.get("nickname", "")
            if name.lower() in uname.lower() or name.lower() in nickname.lower():
                display = uname or nickname
                results.append((qq, display))
        if not results:
            return f"未找到名称包含 '{name}' 的用户。"
        lines = [f"  QQ {qq} -> {n}" for qq, n in results]
        return "找到以下用户:\n" + "\n".join(lines)


register(ContactsSkill)
