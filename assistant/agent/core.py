"""
Agent Core - 高级 Agent 核心循环

集成:
- Planner: 复杂任务分步规划
- Memory: 短期 + 长期记忆
- Reflection: 工具调用后自我反思
- MCP Client: 工具执行
- DeepSeek LLM: 决策引擎

执行流程:
  用户输入
    → Planner 判断是否需要分步计划
    → [有计划] 按步骤执行，每步调用 LLM 决策 + 工具
    → [无计划] 直接进入 ReAct 循环
    → 每次工具调用后 Reflection 评估结果
    → Memory 持久化记忆
    → 返回最终回复
"""

import json
from openai import OpenAI
from assistant.mcp.client import MCPClient
from assistant.agent.memory import Memory
from assistant.agent.planner import Planner
from assistant.agent.reflection import Reflection


SYSTEM_PROMPT = """你是「美萌robot」，一个活泼可爱的私人AI助手！
性格特点: 热情开朗、语气亲切、偶尔卖萌但不过度、回答专业靠谱。

你的能力:
- 查询真实天气（当前天气+三天预报，支持中英文城市名）
- 管理个人笔记（创建、搜索、删除）
- 数学计算
- 读取本地文件和浏览目录
- 设定定时提醒（到时自动通过QQ通知用户）
- 给指定QQ用户或群发送消息
- 通讯录管理（QQ号关联用户名、群号关联群名）
- GitHub 仓库监控（查看分支/提交、监控新提交并QQ通知）
- 热点新闻（获取微博/知乎/百度热搜，每天8点自动推送，也可手动触发）
- 多语言翻译（中英日韩法德等语言互译）
- 快递物流查询（顺丰、中通、圆通、韵达等主流快递）
- 网页搜索（搜索互联网获取实时信息）
- 音乐搜索和推荐（搜歌、热歌榜、新歌榜等）

{session_context}

{user_facts}

{plan_context}

重要规则:
- 请用中文回复，保持活泼友好的语气，但不要每句都加表情。
- 当需要使用工具时请主动调用。
- 创建提醒时，如果知道用户的QQ号，务必将QQ号填入 notify_qq 参数。
- 如果知道用户的名字（通讯录中有），用名字称呼用户而非QQ号。
- 监控 GitHub 仓库时，将用户QQ号填入 notify_qq。
- 如果工具调用失败，请尝试其他方式或如实告知用户。"""


class AgentCore:
    """高级 Agent 核心"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.llm_client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.mcp = MCPClient()
        self.memory = Memory()
        self.planner = Planner(self.llm_client, self.model)
        self.reflection = Reflection(self.llm_client, self.model)
        # 会话上下文 (QQ号、群号等，由外部注入)
        self.session_context: dict = {}

    async def connect(self, server_script: str):
        """连接 MCP Server"""
        await self.mcp.connect(server_script)
        print(f"[Agent] 已连接，可用工具: {', '.join(self.mcp.tool_names)}")

    async def chat(self, user_input: str) -> str:
        """处理用户输入的完整流程"""
        self.memory.add_message("user", user_input)

        # 1. Planner: 判断是否需要分步执行
        plan = self.planner.create_plan(user_input, self.mcp.tools)

        if plan:
            # 复杂任务: 按计划逐步执行
            print(f"  [规划] 创建了 {len(plan.steps)} 步计划:")
            print(f"  {plan.summary()}")
            reply = await self._execute_with_plan(user_input, plan)
        else:
            # 简单任务: 直接 ReAct 循环
            reply = await self._execute_react(user_input)

        self.memory.add_message("assistant", reply)

        # 记忆压缩检查
        if self.memory.needs_compression():
            await self._compress_memory()

        return reply

    async def _execute_react(self, user_input: str) -> str:
        """标准 ReAct 循环（Reason → Act → Observe）"""
        system = self._build_system_prompt()
        messages = [{"role": "system", "content": system}] + self.memory.get_messages()

        response = self.llm_client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self.mcp.tools or None,
        )
        message = response.choices[0].message

        max_iterations = 8  # 防止无限循环
        iteration = 0

        while message.tool_calls and iteration < max_iterations:
            iteration += 1
            self.memory.add_raw_message(message.model_dump(exclude_none=True))

            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                print(f"  [工具] {func_name}({json.dumps(func_args, ensure_ascii=False)})")

                # 执行工具
                tool_result = await self.mcp.call_tool(func_name, func_args)

                # Reflection: 评估结果
                ref = self.reflection.evaluate(func_name, func_args, tool_result, user_input)
                if ref.should_retry and ref.strategy == "retry_same":
                    print(f"  [反思] 结果异常，重试: {ref.reasoning}")
                    tool_result = await self.mcp.call_tool(func_name, func_args)
                elif ref.strategy == "give_up":
                    print(f"  [反思] 放弃重试: {ref.reasoning}")

                self.memory.add_raw_message({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })

            # 再次调用 LLM
            messages = [{"role": "system", "content": system}] + self.memory.get_messages()
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.mcp.tools or None,
            )
            message = response.choices[0].message

        if iteration >= max_iterations:
            return "操作步骤过多，已停止。请尝试简化你的请求。"

        return message.content or "（无回复）"

    async def _execute_with_plan(self, user_input: str, plan) -> str:
        """按计划逐步执行"""
        for step in plan.steps:
            step.status = "running"
            print(f"  [执行] Step {step.step_id}: {step.description}")

            # 构造带计划上下文的 prompt，让 LLM 执行当前步骤
            step_prompt = (
                f"你正在执行一个多步计划的第 {step.step_id} 步。\n"
                f"总目标: {plan.goal}\n"
                f"当前步骤: {step.description}\n"
                f"建议工具: {step.tool_hint}\n"
                f"请执行这一步。"
            )

            system = self._build_system_prompt(plan_context=plan.summary())
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": step_prompt},
            ]

            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.mcp.tools or None,
            )
            message = response.choices[0].message

            # 处理该步骤的工具调用
            step_iterations = 0
            while message.tool_calls and step_iterations < 3:
                step_iterations += 1
                messages.append(message.model_dump(exclude_none=True))

                for tc in message.tool_calls:
                    fn = tc.function.name
                    args = json.loads(tc.function.arguments)
                    print(f"    [工具] {fn}({json.dumps(args, ensure_ascii=False)})")

                    result = await self.mcp.call_tool(fn, args)

                    # Reflection
                    ref = self.reflection.evaluate(fn, args, result, step.description)
                    if ref.should_retry:
                        print(f"    [反思] 重试: {ref.reasoning}")
                        result = await self.mcp.call_tool(fn, args)

                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

                response = self.llm_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.mcp.tools or None,
                )
                message = response.choices[0].message

            step.mark_done(message.content or "")
            print(f"  [完成] Step {step.step_id}")

        # 最终汇总
        plan.is_complete = True
        summary_prompt = (
            f"你已完成以下计划的所有步骤:\n{plan.summary()}\n\n"
            f"请基于各步骤结果，给用户一个完整的汇总回复。"
        )

        response = self.llm_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": summary_prompt},
            ],
        )
        return response.choices[0].message.content or "任务已完成。"

    async def _compress_memory(self):
        """使用 LLM 压缩对话历史"""
        messages = self.memory.get_messages()
        content = "\n".join(
            f"{m.get('role', '?')}: {m.get('content', '')[:200]}"
            for m in messages[:20]
        )
        response = self.llm_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "请用2-3句话概括以下对话的要点:"},
                {"role": "user", "content": content},
            ],
        )
        summary = response.choices[0].message.content or ""
        self.memory.compress(summary)
        print("  [记忆] 对话已压缩")

    def _build_system_prompt(self, plan_context: str = "") -> str:
        facts = self.memory.get_facts_prompt()
        # 构建会话上下文描述
        ctx_parts = []
        if self.session_context.get("user_qq"):
            ctx_parts.append(f"当前对话用户的QQ号: {self.session_context['user_qq']}")
        if self.session_context.get("group_id"):
            ctx_parts.append(f"当前对话所在群号: {self.session_context['group_id']}")
        session_ctx = "\n".join(ctx_parts) if ctx_parts else ""

        return SYSTEM_PROMPT.format(
            session_context=session_ctx,
            user_facts=facts,
            plan_context=f"当前执行计划:\n{plan_context}" if plan_context else "",
        )

    def save_fact(self, key: str, value: str):
        self.memory.save_fact(key, value)

    def clear_history(self):
        self.memory.save_session()
        self.memory.clear_short_term()
        self.reflection.reset()
        print("对话历史已清空（已保存到长期记忆）。")

    async def close(self):
        self.memory.save_session()
        await self.mcp.close()
