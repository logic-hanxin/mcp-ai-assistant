"""
Planner - 任务规划模块

对复杂请求进行任务分解:
用户: "帮我查一下北京天气，然后记到笔记里"
Planner:
  Step 1: 调用 get_weather 获取北京天气
  Step 2: 调用 take_note 将天气信息保存为笔记
  Step 3: 向用户汇报结果

支持分层规划:
- Master Planner: 将复杂需求拆解为里程碑(Milestones)
- 每个里程碑关联一个领域专家 Agent
- Sub-Planner: 子任务执行器，生成具体 Tool Call 序列
"""

from dataclasses import dataclass, field
from enum import Enum


# ============ 任务状态机 ============

class TaskState(Enum):
    """任务执行状态"""
    PENDING = "pending"      # 待处理
    PLANNING = "planning"    # 规划中
    EXECUTING = "executing"  # 执行中
    REVIEWING = "reviewing"  # 审查中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败


# ============ 基础数据模型 ============

@dataclass
class PlanStep:
    """计划中的一个步骤"""
    step_id: int
    description: str
    tool_hint: str = ""       # 建议使用的工具名
    status: str = "pending"   # pending / running / done / failed
    result: str = ""
    sub_steps: list['PlanStep'] = field(default_factory=list)  # 子步骤（嵌套）

    def mark_done(self, result: str = ""):
        self.status = "done"
        self.result = result

    def mark_failed(self, reason: str = ""):
        self.status = "failed"
        self.result = reason

    def has_sub_steps(self) -> bool:
        return len(self.sub_steps) > 0


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


# ============ 分层规划模块 ============

# 领域专家映射
EXPERT_MAPPING = {
    "code": ["run_cpp_code", "get_leetcode_problem", "search_code"],
    "query": ["web_search", "get_hot_news", "search_knowledge", "query_database", "list_tables", "get_table_schema"],
    "task": ["take_note", "create_reminder", "add_rule", "create_workflow", "send_qq_message", "send_qq_group_message"],
    "chat": ["get_weather", "translate_text", "get_current_time", "search_music"],
    "general": [],  # 所有工具
}


@dataclass
class Milestone:
    """
    里程碑 - 分层规划的核心概念

    一个复杂的用户请求会被拆解为多个里程碑，
    每个里程碑关联一个特定的领域专家 Agent。
    """
    milestone_id: int
    title: str                        # 里程碑标题
    description: str                  # 详细描述
    expert_type: str                  # 领域专家: code/query/task/chat/general
    expert_hint: str = ""             # 专家提示词
    steps: list[PlanStep] = field(default_factory=list)  # 子步骤
    status: str = "pending"           # pending/planning/executing/completed/failed
    result: str = ""

    def mark_completed(self, result: str = ""):
        self.status = "completed"
        self.result = result

    def mark_failed(self, reason: str = ""):
        self.status = "failed"
        self.result = reason

    def next_pending_step(self) -> PlanStep | None:
        for s in self.steps:
            if s.status == "pending":
                return s
        return None


@dataclass
class HierarchicalPlan:
    """分层执行计划 - 包含多个里程碑"""
    goal: str                         # 顶层目标
    milestones: list[Milestone] = field(default_factory=list)
    current_milestone_index: int = 0
    is_complete: bool = False

    def current_milestone(self) -> Milestone | None:
        if 0 <= self.current_milestone_index < len(self.milestones):
            return self.milestones[self.current_milestone_index]
        return None

    def advance(self):
        """移动到下一个里程碑"""
        current = self.current_milestone()
        if current and current.status == "completed":
            self.current_milestone_index += 1

    def summary(self) -> str:
        lines = [f"🎯 顶层目标: {self.goal}\n"]
        for i, m in enumerate(self.milestones):
            icon = {
                "pending": "⬜",
                "planning": "📋",
                "executing": "🔄",
                "completed": "✅",
                "failed": "❌",
            }.get(m.status, "⬜")
            expert_emoji = {"code": "💻", "query": "🔍", "task": "📝", "chat": "💬", "general": "🧠"}.get(m.expert_type, "📌")
            lines.append(f"{icon} Milestone {i+1}: [{expert_emoji}{m.expert_type}] {m.title}")
            for s in m.steps:
                step_icon = {"pending": "○", "running": "◐", "done": "●", "failed": "×"}.get(s.status, "○")
                lines.append(f"   {step_icon} {s.description}")
        return "\n".join(lines)


# Master Planner 的 LLM Prompt
MASTER_PLANNER_PROMPT = """你是一个高级任务规划器（Master Planner）。用户会给一个复杂的请求，你需要将其拆解为多个里程碑（Milestones）。

每个里程碑代表一个独立的阶段，可以由特定的领域专家Agent完成。

可用专家类型:
- code: 代码编写、调试、算法问题
- query: 信息查询、搜索、知识检索、数据查询
- task: 任务创建、日程管理、笔记、提醒、发送消息
- chat: 日常闲聊、天气、翻译、时间查询
- general: 其他通用任务

拆解原则:
1. 每个里程碑应该是自包含的，有明确的目标
2. 按逻辑顺序排列里程碑
3. 考虑里程碑之间的依赖关系

用户请求: {user_input}

请返回 JSON:
{{
    "needs_hierarchy": true/false,
    "milestones": [
        {{
            "title": "里程碑标题",
            "description": "详细描述",
            "expert_type": "code/query/task/chat/general",
            "steps": [
                {{"description": "步骤描述", "tool_hint": "建议工具名"}}
            ]
        }}
    ]
}}

只返回 JSON。"""


# Sub Planner 的 LLM Prompt
SUB_PLANNER_PROMPT = """你是一个子任务规划器（Sub-Planner）。Master Planner 给了你一个里程碑任务，请生成具体的工具调用步骤。

里程碑: {milestone_title}
详细描述: {milestone_description}
专家类型: {expert_type}

可用工具:
{available_tools}

请为这个里程碑生成具体的执行步骤。

返回 JSON:
{{
    "steps": [
        {{"description": "步骤描述", "tool_hint": "建议工具名"}}
    ]
}}

只返回 JSON。"""


class HierarchicalPlanner:
    """
    分层规划器

    Master Planner: 将复杂需求拆解为里程碑
    Sub-Planner: 每个里程碑内部生成具体步骤
    """

    def __init__(self, llm_client, model: str):
        self.llm = llm_client
        self.model = model

    def create_hierarchical_plan(self, user_input: str, available_tools: list[dict]) -> HierarchicalPlan | None:
        """
        创建分层执行计划
        """
        # Step 1: Master Planner 拆解里程碑
        try:
            response = self.llm.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个高级任务规划专家。"},
                    {"role": "user", "content": MASTER_PLANNER_PROMPT.format(user_input=user_input)},
                ],
                response_format={"type": "json_object"},
            )

            import json
            result = json.loads(response.choices[0].message.content)

            if not result.get("needs_hierarchy", False):
                return None

            milestones = []
            for i, m in enumerate(result.get("milestones", [])):
                milestone = Milestone(
                    milestone_id=i + 1,
                    title=m.get("title", ""),
                    description=m.get("description", ""),
                    expert_type=m.get("expert_type", "general"),
                )

                # Step 2: Sub-Planner 生成子步骤
                steps = self._plan_sub_steps(
                    milestone_title=m.get("title", ""),
                    milestone_desc=m.get("description", ""),
                    expert_type=m.get("expert_type", "general"),
                    available_tools=available_tools,
                )
                milestone.steps = steps

                milestones.append(milestone)

            if not milestones:
                return None

            return HierarchicalPlan(goal=user_input, milestones=milestones)

        except Exception as e:
            print(f"[HierarchicalPlanner] 创建分层计划失败: {e}")
            return None

    def _plan_sub_steps(
        self,
        milestone_title: str,
        milestone_desc: str,
        expert_type: str,
        available_tools: list[dict],
    ) -> list[PlanStep]:
        """Sub-Planner: 为单个里程碑生成具体步骤"""
        # 筛选该专家可用的工具
        allowed_tools = EXPERT_MAPPING.get(expert_type, [])
        if allowed_tools:
            filtered_tools = [t for t in available_tools if t.get("function", {}).get("name") in allowed_tools]
        else:
            filtered_tools = available_tools

        tool_descriptions = "\n".join(
            f"- {t['function']['name']}: {t['function']['description']}"
            for t in filtered_tools[:30]  # 限制数量避免 token 溢出
        )

        try:
            response = self.llm.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个子任务规划专家。"},
                    {"role": "user", "content": SUB_PLANNER_PROMPT.format(
                        milestone_title=milestone_title,
                        milestone_description=milestone_desc,
                        expert_type=expert_type,
                        available_tools=tool_descriptions,
                    )}
                ],
                response_format={"type": "json_object"},
            )

            import json
            result = json.loads(response.choices[0].message.content)

            steps = []
            for i, s in enumerate(result.get("steps", []), 1):
                steps.append(PlanStep(
                    step_id=i,
                    description=s.get("description", ""),
                    tool_hint=s.get("tool_hint", ""),
                ))

            return steps

        except Exception as e:
            print(f"[HierarchicalPlanner] Sub-Planner 失败: {e}")
            return []
