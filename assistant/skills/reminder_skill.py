"""定时提醒 Skill - 设置提醒，到时间自动通知"""

import datetime
from assistant.skills.base import BaseSkill, ToolDefinition, register
from assistant.agent import db


class ReminderSkill(BaseSkill):
    name = "reminder"
    description = "定时提醒，设定时间后自动提醒用户"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="create_reminder",
                description=(
                    "创建一个定时提醒。到达指定时间后会自动通过QQ发送提醒消息给用户。"
                    "支持设置具体时间（如 '15:30'、'2025-03-17 09:00'）"
                    "或相对时间（如 '30分钟后'、'2小时后'）。"
                    "如果知道用户的QQ号，请务必填写 notify_qq 参数。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "提醒内容，如 '开会'、'吃药'、'给妈妈打电话'",
                        },
                        "time_str": {
                            "type": "string",
                            "description": (
                                "提醒时间。支持以下格式:\n"
                                "- 绝对时间: '15:30'(今天15:30), '2025-03-17 09:00'\n"
                                "- 相对时间: '30m'(30分钟后), '2h'(2小时后), '1h30m'(1小时30分钟后)"
                            ),
                        },
                        "notify_qq": {
                            "type": "string",
                            "description": "接收提醒的QQ号。从对话上下文中获取当前用户的QQ号填入。",
                            "default": "",
                        },
                        "notify_group_id": {
                            "type": "string",
                            "description": "如果是群聊场景，填入群号以在群内@提醒。留空则私聊提醒。",
                            "default": "",
                        },
                    },
                    "required": ["message", "time_str"],
                },
                handler=self._create_reminder,
            ),
            ToolDefinition(
                name="list_reminders",
                description="列出所有待执行的提醒。",
                parameters={"type": "object", "properties": {}},
                handler=self._list_reminders,
            ),
            ToolDefinition(
                name="delete_reminder",
                description="根据提醒ID删除一个提醒。",
                parameters={
                    "type": "object",
                    "properties": {
                        "reminder_id": {
                            "type": "integer",
                            "description": "提醒ID",
                        },
                    },
                    "required": ["reminder_id"],
                },
                handler=self._delete_reminder,
            ),
        ]

    def _parse_time(self, time_str: str) -> datetime.datetime | None:
        """解析时间字符串，支持绝对时间和相对时间"""
        import re

        now = datetime.datetime.now()
        s = time_str.strip()

        # 相对时间: 30m, 2h, 1h30m, 90s
        relative = re.match(r'^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$', s)
        if relative and any(relative.groups()):
            hours = int(relative.group(1) or 0)
            minutes = int(relative.group(2) or 0)
            seconds = int(relative.group(3) or 0)
            delta = datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds)
            return now + delta

        # 中文相对时间: "30分钟后", "2小时后", "1小时30分钟后"
        cn_match = re.match(r'^(?:(\d+)\s*小时)?(?:(\d+)\s*分钟?)?后?$', s)
        if cn_match and any(cn_match.groups()):
            hours = int(cn_match.group(1) or 0)
            minutes = int(cn_match.group(2) or 0)
            return now + datetime.timedelta(hours=hours, minutes=minutes)

        # 绝对时间: HH:MM (今天)
        try:
            t = datetime.datetime.strptime(s, "%H:%M")
            target = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
            if target <= now:
                target += datetime.timedelta(days=1)  # 如果已过，设为明天
            return target
        except ValueError:
            pass

        # 绝对时间: YYYY-MM-DD HH:MM
        try:
            return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M")
        except ValueError:
            pass

        # 绝对时间: MM-DD HH:MM (今年)
        try:
            t = datetime.datetime.strptime(s, "%m-%d %H:%M")
            return t.replace(year=now.year)
        except ValueError:
            pass

        return None

    def _create_reminder(self, message: str, time_str: str, notify_qq: str = "", notify_group_id: str = "") -> str:
        target_time = self._parse_time(time_str)
        if target_time is None:
            return (
                f"无法解析时间 '{time_str}'。支持的格式:\n"
                f"- 相对时间: 30m, 2h, 1h30m\n"
                f"- 绝对时间: 15:30, 2025-03-17 09:00"
            )

        now = datetime.datetime.now()
        if target_time <= now:
            return f"提醒时间 {target_time.strftime('%Y-%m-%d %H:%M')} 已经过去了，请设置一个未来的时间。"

        try:
            rid = db.reminder_create(
                message=message,
                target_time=target_time.strftime("%Y-%m-%d %H:%M:%S"),
                notify_qq=notify_qq,
                notify_group_id=notify_group_id,
            )
        except Exception as e:
            return f"创建提醒失败: {e}"

        delta = target_time - now
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes = remainder // 60

        time_display = target_time.strftime("%Y-%m-%d %H:%M")
        if hours > 0:
            delta_str = f"{hours}小时{minutes}分钟后"
        elif minutes > 0:
            delta_str = f"{minutes}分钟后"
        else:
            delta_str = "即将"

        return (
            f"提醒已创建！\n"
            f"  ID: {rid}\n"
            f"  内容: {message}\n"
            f"  时间: {time_display} ({delta_str})"
        )

    def _list_reminders(self) -> str:
        try:
            pending = db.reminder_get_all_pending()
        except Exception as e:
            return f"查询提醒失败: {e}"

        if not pending:
            return "暂无待执行的提醒。"

        now = datetime.datetime.now()
        lines = []
        for r in pending:
            target = r["target_time"]
            if isinstance(target, str):
                target = datetime.datetime.fromisoformat(target)
            delta = target - now
            if delta.total_seconds() > 0:
                hours, remainder = divmod(int(delta.total_seconds()), 3600)
                minutes = remainder // 60
                if hours > 0:
                    remaining = f"还有 {hours}小时{minutes}分钟"
                else:
                    remaining = f"还有 {minutes}分钟"
            else:
                remaining = "已到时间"
            lines.append(
                f"[{r['id']}] {r['message']}  "
                f"时间: {target.strftime('%m-%d %H:%M')}  ({remaining})"
            )
        return "\n".join(lines)

    def _delete_reminder(self, reminder_id: int) -> str:
        try:
            ok = db.reminder_delete(reminder_id)
        except Exception as e:
            return f"删除提醒失败: {e}"
        if not ok:
            return f"未找到 ID 为 {reminder_id} 的提醒。"
        return f"提醒 {reminder_id} 已删除。"


register(ReminderSkill)
