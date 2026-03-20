"""时间日期 Skill"""

import datetime
from assistant.skills.base import BaseSkill, ToolDefinition, register


class TimeSkill(BaseSkill):
    name = "time"
    description = "获取当前日期、时间和星期信息"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_current_time",
                description="获取当前日期和时间。可以指定时区。",
                parameters={
                    "type": "object",
                    "properties": {
                        "timezone": {
                            "type": "string",
                            "description": "时区名称，如 Asia/Shanghai、America/New_York，默认 Asia/Shanghai",
                            "default": "Asia/Shanghai",
                        }
                    },
                },
                handler=self._get_current_time,
                metadata={
                    "category": "read",
                },
                keywords=["时间", "现在几点", "当前日期", "当前时间"],
                intents=["get_current_time"],
            ),
        ]

    def _get_current_time(self, timezone: str = "Asia/Shanghai") -> str:
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(timezone)
            now = datetime.datetime.now(tz)
        except Exception:
            now = datetime.datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S %A (时区: {})").format(timezone)


register(TimeSkill)
