"""天气查询 Skill"""

from assistant.skills.base import BaseSkill, ToolDefinition, register


class WeatherSkill(BaseSkill):
    name = "weather"
    description = "查询城市天气信息"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_weather",
                description="查询指定城市的天气信息。目前为模拟数据，可替换为真实天气API（如 OpenWeatherMap）。",
                parameters={
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市名称，如 北京、上海、San Francisco",
                        }
                    },
                    "required": ["city"],
                },
                handler=self._get_weather,
            ),
        ]

    def _get_weather(self, city: str) -> str:
        import random
        conditions = ["晴", "多云", "阴", "小雨", "大雨", "雪"]
        temp = random.randint(-5, 38)
        humidity = random.randint(20, 95)
        condition = random.choice(conditions)
        return (
            f"城市: {city}\n"
            f"天气: {condition}\n"
            f"温度: {temp}°C\n"
            f"湿度: {humidity}%\n"
            f"(模拟数据，如需真实天气请在 WeatherSkill 中配置API)"
        )


register(WeatherSkill)
