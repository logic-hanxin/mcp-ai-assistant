"""
Planner - 任务规划模块

对复杂请求进行任务分解:
用户: "帮我查一下北京天气，然后记到笔记里"
Planner:
  Step 1: 调用 get_weather 获取北京天气
  Step 2: 调用 take_note 将天气信息保存为笔记
  Step 3: 向用户汇报结果
"""

from dataclasses import dataclass, field


@dataclass
class PlanStep:
    """计划中的一个步骤"""
    step_id: int
    description: str
    tool_hint: str = ""       # 建议使用的工具名
    status: str = "pending"   # pending / running / done / failed
    result: str = ""

    def mark_done(self, result: str = ""):
        self.status = "done"
        self.result = result

    def mark_failed(self, reason: str = ""):
        self.status = "failed"
        self.result = reason


@dataclass
class Plan:
    """执行计划"""
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    is_complete: bool = False

    def next_step(self) -> PlanStep | None:
        for s in self.steps:
            if s.status == "pending":
                return s
        return None

    def all_done(self) -> bool:
        return all(s.status in ("done", "failed") for s in self.steps)

    def summary(self) -> str:
        lines = [f"目标: {self.goal}"]
        for s in self.steps:
            icon = {"pending": "⬜", "running": "🔄", "done": "✅", "failed": "❌"}[s.status]
            lines.append(f"  {icon} Step {s.step_id}: {s.description}")
            if s.result:
                lines.append(f"       结果: {s.result[:100]}")
        return "\n".join(lines)


PLAN_SYSTEM_PROMPT = """你是一个任务规划器。用户会给你一个目标和可用工具列表。
请分析目标，判断是否需要分步执行。

如果是简单任务（只需一步或直接回答），返回:
{"needs_plan": false}

如果是复杂任务（需要多步操作），返回:
{"needs_plan": true, "steps": [{"description": "步骤描述", "tool_hint": "建议工具名"}]}

只返回 JSON，不要其他内容。"""


class Planner:
    """任务规划器，使用 LLM 进行任务分解"""

    def __init__(self, llm_client, model: str):
        self.llm = llm_client
        self.model = model

    def create_plan(self, user_input: str, available_tools: list[dict]) -> Plan | None:
        """
        分析用户请求，决定是否需要创建执行计划。
        返回 Plan 或 None（简单任务不需要计划）。
        """
        tool_descriptions = "\n".join(
            f"- {t['function']['name']}: {t['function']['description']}"
            for t in available_tools
        )

        response = self.llm.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": PLAN_SYSTEM_PROMPT},
                {"role": "user", "content": f"目标: {user_input}\n\n可用工具:\n{tool_descriptions}"},
            ],
            response_format={"type": "json_object"},
        )

        import json
        try:
            result = json.loads(response.choices[0].message.content)
        except (json.JSONDecodeError, TypeError):
            return None

        if not result.get("needs_plan"):
            return None

        steps = []
        for i, s in enumerate(result.get("steps", []), 1):
            steps.append(PlanStep(
                step_id=i,
                description=s.get("description", ""),
                tool_hint=s.get("tool_hint", ""),
            ))

        if not steps:
            return None

        return Plan(goal=user_input, steps=steps)
