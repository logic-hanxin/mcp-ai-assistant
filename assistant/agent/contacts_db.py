"""
通讯录数据层 - 用户和群的持久化存储

数据结构:
  users.json: {
    "QQ号": {
      "name": "自定义名称",
      "nickname": "QQ昵称（自动获取）",
      "first_seen": "2025-03-17T08:00:00",
      "last_seen": "2025-03-17T12:30:00",
      "msg_count": 42
    }
  }

  groups.json: {
    "群号": {
      "name": "自定义群名",
      "group_name": "QQ群名称（自动获取）",
      "first_seen": "2025-03-17T08:00:00",
      "last_seen": "2025-03-17T12:30:00",
      "msg_count": 100
    }
  }
"""

import json
import datetime
from pathlib import Path

CONTACTS_DIR = Path.home() / ".ai_assistant" / "contacts"
USERS_FILE = CONTACTS_DIR / "users.json"
GROUPS_FILE = CONTACTS_DIR / "groups.json"


def _ensure_dir():
    CONTACTS_DIR.mkdir(parents=True, exist_ok=True)


def _load(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # 兼容旧格式: 如果值是字符串，自动升级为新结构
            upgraded = {}
            for key, val in data.items():
                if isinstance(val, str):
                    upgraded[key] = {
                        "name": val,
                        "nickname": "",
                        "first_seen": "",
                        "last_seen": "",
                        "msg_count": 0,
                    }
                else:
                    upgraded[key] = val
            return upgraded
        except Exception:
            return {}
    return {}


def _save(path: Path, data: dict):
    _ensure_dir()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_users() -> dict:
    return _load(USERS_FILE)


def save_users(data: dict):
    _save(USERS_FILE, data)


def load_groups() -> dict:
    return _load(GROUPS_FILE)


def save_groups(data: dict):
    _save(GROUPS_FILE, data)


def record_user_interaction(qq_number: str, nickname: str = ""):
    """记录一次用户交互（每次收到消息时调用）"""
    users = load_users()
    now = datetime.datetime.now().isoformat(timespec="seconds")

    if qq_number in users:
        user = users[qq_number]
        user["last_seen"] = now
        user["msg_count"] = user.get("msg_count", 0) + 1
        # 如果有新的昵称且当前没有自定义名称，更新昵称
        if nickname and not user.get("nickname"):
            user["nickname"] = nickname
        elif nickname and nickname != user.get("nickname"):
            user["nickname"] = nickname
    else:
        users[qq_number] = {
            "name": "",
            "nickname": nickname,
            "first_seen": now,
            "last_seen": now,
            "msg_count": 1,
        }

    save_users(users)


def record_group_interaction(group_id: str, group_name: str = ""):
    """记录一次群交互（每次收到群消息时调用）"""
    groups = load_groups()
    now = datetime.datetime.now().isoformat(timespec="seconds")

    if group_id in groups:
        grp = groups[group_id]
        grp["last_seen"] = now
        grp["msg_count"] = grp.get("msg_count", 0) + 1
        if group_name and group_name != grp.get("group_name"):
            grp["group_name"] = group_name
    else:
        groups[group_id] = {
            "name": "",
            "group_name": group_name,
            "first_seen": now,
            "last_seen": now,
            "msg_count": 1,
        }

    save_groups(groups)


def get_user_display_name(qq_number: str) -> str:
    """获取用户显示名称，优先级: 自定义名称 > QQ昵称 > QQ号"""
    users = load_users()
    user = users.get(qq_number, {})
    return user.get("name") or user.get("nickname") or qq_number
