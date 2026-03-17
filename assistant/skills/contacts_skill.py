"""通讯录 Skill - QQ号关联用户名、群号关联群名"""

import json
from pathlib import Path
from assistant.skills.base import BaseSkill, ToolDefinition, register

CONTACTS_DIR = Path.home() / ".ai_assistant" / "contacts"
USERS_FILE = CONTACTS_DIR / "users.json"
GROUPS_FILE = CONTACTS_DIR / "groups.json"


def _load(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(path: Path, data: dict):
    CONTACTS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class ContactsSkill(BaseSkill):
    name = "contacts"
    description = "通讯录管理，QQ号关联用户名、群号关联群名"

    def on_load(self):
        CONTACTS_DIR.mkdir(parents=True, exist_ok=True)

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="set_user_name",
                description="设置QQ号对应的用户名称。以后提到该用户时会显示名称而非QQ号。",
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
                description="根据QQ号查询用户名称。",
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
                description="列出所有已保存的用户和群信息。",
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
        users = _load(USERS_FILE)
        users[qq_number] = name
        _save(USERS_FILE, users)
        return f"已保存: QQ {qq_number} -> {name}"

    def _get_user(self, qq_number: str) -> str:
        users = _load(USERS_FILE)
        name = users.get(qq_number)
        if name:
            return f"QQ {qq_number} 的用户名称是: {name}"
        return f"未找到 QQ {qq_number} 的记录。"

    def _set_group(self, group_id: str, name: str) -> str:
        groups = _load(GROUPS_FILE)
        groups[group_id] = name
        _save(GROUPS_FILE, groups)
        return f"已保存: 群 {group_id} -> {name}"

    def _list_contacts(self) -> str:
        users = _load(USERS_FILE)
        groups = _load(GROUPS_FILE)
        lines = []
        if users:
            lines.append("用户列表:")
            for qq, name in users.items():
                lines.append(f"  QQ {qq} -> {name}")
        else:
            lines.append("暂无用户记录。")
        if groups:
            lines.append("群列表:")
            for gid, name in groups.items():
                lines.append(f"  群 {gid} -> {name}")
        else:
            lines.append("暂无群记录。")
        return "\n".join(lines)

    def _find_qq(self, name: str) -> str:
        users = _load(USERS_FILE)
        results = [(qq, n) for qq, n in users.items() if name.lower() in n.lower()]
        if not results:
            return f"未找到名称包含 '{name}' 的用户。"
        lines = [f"  QQ {qq} -> {n}" for qq, n in results]
        return "找到以下用户:\n" + "\n".join(lines)


register(ContactsSkill)
