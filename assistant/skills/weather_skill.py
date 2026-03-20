"""天气查询 Skill - 基于 wttr.in 的真实天气数据"""

from typing import Optional

import httpx
from assistant.skills.base import BaseSkill, ToolDefinition, register


def _query_wttr(city: str) -> Optional[dict]:
    """调用 wttr.in 获取天气 JSON"""
    try:
        resp = httpx.get(
            f"https://wttr.in/{city}?format=j1&lang=zh",
            timeout=10,
            headers={"User-Agent": "curl/7.0"},
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


class WeatherSkill(BaseSkill):
    name = "weather"
    description = "查询城市真实天气信息（当前天气+未来三天预报）"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_weather",
                description=(
                    "查询指定城市的真实天气信息，包含当前天气和未来三天预报。"
                    "支持中文城市名（如 北京、上海）和英文城市名。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市名称，如 北京、上海、Tokyo、London",
                        }
                    },
                    "required": ["city"],
                },
                handler=self._get_weather,
                metadata={
                    "category": "read",
                    "blackboard_reads": ["last_city"],
                    "blackboard_writes": ["last_city", "last_weather"],
                    "required_all": ["city"],
                    "store_args": {"city": "last_city"},
                    "store_result": ["last_weather"],
                },
                result_parser=self._parse_weather_result,
                keywords=["天气", "查天气", "今天天气", "天气预报"],
                intents=["get_weather"],
            ),
        ]

    def _get_weather(self, city: str) -> str:
        data = _query_wttr(city)
        if not data:
            return f"获取 {city} 天气失败，请检查城市名是否正确。"

        try:
            cur = data["current_condition"][0]

            # 当前天气描述（优先中文）
            desc_list = cur.get("lang_zh", [])
            desc = desc_list[0]["value"] if desc_list else cur["weatherDesc"][0]["value"]

            lines = [
                f"📍 {city} 当前天气",
                f"  天气: {desc}",
                f"  温度: {cur['temp_C']}°C (体感 {cur['FeelsLikeC']}°C)",
                f"  湿度: {cur['humidity']}%",
                f"  风速: {cur['windspeedKmph']} km/h {cur.get('winddir16Point', '')}",
                f"  能见度: {cur.get('visibility', '?')} km",
            ]

            # 未来预报
            weather_list = data.get("weather", [])
            if weather_list:
                lines.append("")
                lines.append("未来预报:")
                for day in weather_list[:3]:
                    date = day.get("date", "")
                    low = day.get("mintempC", "?")
                    high = day.get("maxtempC", "?")
                    # 获取当天天气描述
                    hourly = day.get("hourly", [{}])
                    mid = hourly[len(hourly) // 2] if hourly else {}
                    day_desc_list = mid.get("lang_zh", [])
                    day_desc = day_desc_list[0]["value"] if day_desc_list else ""
                    lines.append(f"  {date}: {low}~{high}°C {day_desc}")

            return "\n".join(lines)

        except (KeyError, IndexError) as e:
            return f"解析 {city} 天气数据出错: {e}"

    def _parse_weather_result(self, args: dict, result: str) -> dict | None:
        city = str(args.get("city", "")).strip()
        if city:
            return {"city": city, "weather": result[:300]}
        return None


register(WeatherSkill)
