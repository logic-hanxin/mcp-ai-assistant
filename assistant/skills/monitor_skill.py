"""网站监控 Skill - 添加/移除/查看网站监控"""

from __future__ import annotations

from assistant.skills.base import BaseSkill, ToolDefinition, register


class MonitorSkill(BaseSkill):
    name = "monitor"
    description = "网站可用性监控，站点挂了自动通知"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="add_site_monitor",
                description=(
                    "添加一个网站到监控列表。添加后系统会每60秒自动检测网站是否可访问，"
                    "连续3次失败会通过QQ私聊通知。恢复后也会通知。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "要监控的网站地址，如 http://example.com",
                        },
                        "name": {
                            "type": "string",
                            "description": "站点名称，方便识别（如: 协会官网）",
                        },
                        "notify_qq": {
                            "type": "string",
                            "description": "告警通知的QQ号，不填则通知管理员",
                        },
                    },
                    "required": ["url"],
                },
                handler=self._add_monitor,
            ),
            ToolDefinition(
                name="remove_site_monitor",
                description="从监控列表中移除一个网站。",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "要移除的网站地址",
                        },
                    },
                    "required": ["url"],
                },
                handler=self._remove_monitor,
            ),
            ToolDefinition(
                name="list_site_monitors",
                description="查看当前所有监控中的网站及其状态。",
                parameters={
                    "type": "object",
                    "properties": {},
                },
                handler=self._list_monitors,
            ),
        ]

    def _add_monitor(self, url: str, name: str = "", notify_qq: str = "") -> str:
        try:
            from assistant.agent.site_checker import add_site
            site = add_site(url, name=name, notify_qq=notify_qq)
            return f"已添加监控:\n  名称: {site['name']}\n  地址: {url}\n  通知: {notify_qq or '管理员'}\n每60秒自动检测，连续3次失败会告警。"
        except Exception as e:
            return f"添加失败: {e}"

    def _remove_monitor(self, url: str) -> str:
        try:
            from assistant.agent.site_checker import remove_site
            if remove_site(url):
                return f"已移除监控: {url}"
            return f"未找到该监控: {url}"
        except Exception as e:
            return f"移除失败: {e}"

    def _list_monitors(self) -> str:
        try:
            from assistant.agent.site_checker import list_sites
            sites = list_sites()
            if not sites:
                return "当前没有监控任何网站。"
            lines = [f"当前监控 {len(sites)} 个站点:"]
            for s in sites:
                status_icon = {"up": "✅", "down": "❌", "unknown": "❓"}.get(s["status"], "❓")
                line = f"  {status_icon} {s['name']} ({s['url']})"
                if s.get("last_check"):
                    line += f"\n     最后检测: {s['last_check']} | 状态码: {s['last_status_code']}"
                if s["status"] == "down" and s.get("down_since"):
                    line += f"\n     故障开始: {s['down_since']} | 连续失败: {s['fail_count']}次"
                lines.append(line)
            return "\n".join(lines)
        except Exception as e:
            return f"查询失败: {e}"


register(MonitorSkill)
