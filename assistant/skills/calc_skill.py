"""数学计算 Skill"""

from assistant.skills.base import BaseSkill, ToolDefinition, register


class CalcSkill(BaseSkill):
    name = "calculator"
    description = "安全的数学表达式计算"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="calculate",
                description="计算数学表达式。支持基本运算和数学函数如 sqrt、sin、cos、log 等。",
                parameters={
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": '数学表达式，如 "2+3*4"、"sqrt(16)"、"sin(3.14/6)"',
                        }
                    },
                    "required": ["expression"],
                },
                handler=self._calculate,
                metadata={
                    "category": "read",
                    "required_all": ["expression"],
                },
                keywords=["计算", "数学", "表达式求值", "算一下"],
                intents=["calculate_expression"],
            ),
        ]

    def _calculate(self, expression: str) -> str:
        import math
        allowed = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}
        allowed.update({"abs": abs, "round": round, "min": min, "max": max})
        try:
            result = eval(expression, {"__builtins__": {}}, allowed)
            return f"{expression} = {result}"
        except Exception as e:
            return f"计算出错: {e}"


register(CalcSkill)
