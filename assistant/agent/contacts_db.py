"""
通讯录数据层 - 用户和群的持久化存储 (MySQL)

对外接口保持不变，内部改为 DB 存储。
DB 不可用时自动降级到文件存储。
"""

from __future__ import annotations

_db_ok = True
try:
    from assistant.agent.db import (
        contact_upsert_user, contact_upsert_group,
        contact_set_user_name, contact_set_group_name,
        contact_get_users, contact_get_groups,
        contact_get_user, contact_get_user_display_name as _db_display_name,
    )
except Exception:
    _db_ok = False


def record_user_interaction(qq_number: str, nickname: str = ""):
    """记录一次用户交互（每次收到消息时调用）"""
    if _db_ok:
        try:
            contact_upsert_user(qq_number, nickname=nickname)
            return
        except Exception as e:
            print(f"[通讯录] DB写入失败: {e}")


def record_group_interaction(group_id: str, group_name: str = ""):
    """记录一次群交互（每次收到群消息时调用）"""
    if _db_ok:
        try:
            contact_upsert_group(group_id, group_name=group_name)
            return
        except Exception as e:
            print(f"[通讯录] DB写入失败: {e}")


def get_user_display_name(qq_number: str) -> str:
    """获取用户显示名称，优先级: 自定义名称 > QQ昵称 > QQ号"""
    if _db_ok:
        try:
            name = _db_display_name(qq_number)
            return name or qq_number
        except Exception:
            pass
    return qq_number


def load_users() -> dict:
    """加载所有用户，返回 {qq: {name, nickname, ...}} 兼容旧格式"""
    if _db_ok:
        try:
            rows = contact_get_users()
            return {
                r["qq"]: {
                    "name": r.get("name", ""),
                    "nickname": r.get("nickname", ""),
                    "first_seen": str(r.get("first_seen", "")),
                    "last_seen": str(r.get("last_seen", "")),
                    "msg_count": r.get("msg_count", 0),
                }
                for r in rows
            }
        except Exception:
            pass
    return {}


def load_groups() -> dict:
    """加载所有群，返回 {group_id: {name, group_name, ...}} 兼容旧格式"""
    if _db_ok:
        try:
            rows = contact_get_groups()
            return {
                r["group_id"]: {
                    "name": r.get("name", ""),
                    "group_name": r.get("group_name", ""),
                    "first_seen": str(r.get("first_seen", "")),
                    "last_seen": str(r.get("last_seen", "")),
                    "msg_count": r.get("msg_count", 0),
                }
                for r in rows
            }
        except Exception:
            pass
    return {}


def save_users(data: dict):
    """批量保存用户（兼容旧接口）"""
    if _db_ok:
        for qq, info in data.items():
            try:
                contact_upsert_user(
                    qq,
                    nickname=info.get("nickname", ""),
                    name=info.get("name", ""),
                )
            except Exception:
                pass


def save_groups(data: dict):
    """批量保存群（兼容旧接口）"""
    if _db_ok:
        for gid, info in data.items():
            try:
                contact_upsert_group(
                    gid,
                    group_name=info.get("group_name", ""),
                    name=info.get("name", ""),
                )
            except Exception:
                pass
