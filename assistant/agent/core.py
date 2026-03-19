"""
Agent Core - 多 Agent 路由架构

集成:
- Router: 意图分类，将消息路由到专家 Agent
- Planner: 复杂任务分步规划 (使用全量工具)
- Memory: 短期 + 长期记忆
- Reflection: 工具调用后自我反思
- MCP Client: 工具执行
- DeepSeek LLM: 决策引擎

执行流程:
  用户输入
    → Router 分类意图 → 选择专家档案 (过滤工具 + 专用提示)
    → Planner 判断是否需要分步计划
    → [有计划] 按步骤执行 (全量工具)
    → [无计划] 专家模式 ReAct 循环 (过滤后的工具子集)
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
from assistant.agent.router import Router, EXPERT_PROFILES
from assistant.agent.blackboard import Blackboard


SYSTEM_PROMPT = """你是「小彩云」，彩云协会的智能助手，也是群里的一员。

性格特点: 热情友善、性格活泼、说话自然随意像真实的群友，偶尔幽默但不刻意卖萌，回答专业靠谱。

身份设定:
- 你是彩云协会的 AI 群友，平时就在群里，像一个真实的成员一样参与聊天。
- 你了解协会的各种事务，愿意帮忙解答问题、提供信息。
- 说话风格自然口语化，不要像客服那样机械。可以用"哈哈""嗯嗯""确实"这类口语词。
- 不用每次都很正式地回复，短句、轻松的语气更好。

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
- 定位功能（用户发送QQ位置可解析、IP定位、手机号归属地查询）
- 数据库查询（查询协会管理系统数据）
- 知识库（RAG检索增强：存储协会文档、规章制度、FAQ，提问时自动检索相关内容）
- 自动化工作流（创建定时自动执行的任务链）

{expert_hint}

{session_context}

{user_facts}

{plan_context}

{rules}

群聊行为规则:
- 请用中文回复，保持自然口语化的语气。
- 当需要使用工具时请主动调用。
- 创建提醒时，如果知道用户的QQ号，务必将QQ号填入 notify_qq 参数。
- 如果知道用户的名字（通讯录中有），用名字称呼用户而非QQ号。
- 监控 GitHub 仓库时，将用户QQ号填入 notify_qq。
- 如果工具调用失败，请尝试其他方式或如实告知用户。
- 回复要简洁自然，不要长篇大论，除非用户明确需要详细信息。
- 当用户告诉你一条规则或要求你遵守某个准则时，主动调用 add_rule 工具写入守则。"""


class AgentCore:
    """多 Agent 路由架构核心"""

    def __init__(self, api_key: str, base_url: str, model: str,
                 session_id: str = "default", user_id: str = None):
        self.llm_client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.mcp = MCPClient()
        self.memory = Memory(session_id=session_id, user_id=user_id or session_id)
        self.planner = Planner(self.llm_client, self.model)
        self.reflection = Reflection(self.llm_client, self.model)
        self.router = Router(self.llm_client, self.model)
        # 黑板模式 - 多Agent共享状态
        self.blackboard = Blackboard.get_instance()
        # 会话上下文 (QQ号、群号等，由外部注入)
        self.session_context: dict = {}

    async def connect(self, server_script: str):
        """连接 MCP Server"""
        await self.mcp.connect(server_script)
        print(f"[Agent] 已连接，可用工具: {', '.join(self.mcp.tool_names)}")

    # ----------------------------------------------------------
    # 工具过滤
    # ----------------------------------------------------------
    def _filter_tools(self, tool_names: set | None) -> list | None:
        """根据专家档案过滤工具列表，返回 OpenAI tools 格式"""
        if not tool_names or not self.mcp.tools:
            return self.mcp.tools or None
        filtered = [
            t for t in self.mcp.tools
            if t["function"]["name"] in tool_names
        ]
        return filtered or self.mcp.tools or None

    def _get_recent_context(self, n: int = 3) -> str:
        """获取最近 n 条消息作为路由上下文"""
        msgs = self.memory.short_term[-n:]
        parts = []
        for m in msgs:
            role = m.get("role", "")
            content = m.get("content", "")
            if role in ("user", "assistant") and content:
                parts.append(f"{role}: {content[:100]}")
        return "\n".join(parts)

    # ----------------------------------------------------------
    # 主入口
    # ----------------------------------------------------------
    async def chat(self, user_input: str) -> str:
        """处理用户输入的完整流程"""
        self.memory.add_message("user", user_input)

        # 1. Router: 意图分类
        recent_ctx = self._get_recent_context()
        expert_key = self.router.classify(user_input, recent_ctx)
        expert = EXPERT_PROFILES.get(expert_key)

        if expert:
            print(f"  [路由] → {expert['name']} ({expert_key})")
        else:
            print(f"  [路由] → 通用模式 (general)")

        # 2. Planner: 判断是否需要分步执行 (复杂任务用全量工具)
        plan = self.planner.create_plan(user_input, self.mcp.tools)

        if plan:
            # 复杂任务: 按计划逐步执行，使用全量工具
            print(f"  [规划] 创建了 {len(plan.steps)} 步计划:")
            print(f"  {plan.summary()}")
            reply = await self._execute_with_plan(user_input, plan)
        else:
            # 简单任务: 专家模式 ReAct 循环
            expert_tools = self._filter_tools(expert["tool_names"]) if expert else (self.mcp.tools or None)
            expert_hint = expert["system_hint"] if expert else ""
            reply = await self._execute_react(user_input, tools=expert_tools, expert_hint=expert_hint)

        self.memory.add_message("assistant", reply)

        # 记忆压缩检查
        if self.memory.needs_compression():
            await self._compress_memory()

        return reply

    # ----------------------------------------------------------
    # ReAct 循环 (支持专家工具过滤)
    # ----------------------------------------------------------
    async def _execute_react(self, user_input: str, tools: list | None = None,
                             expert_hint: str = "") -> str:
        """专家模式 ReAct 循环（Reason → Act → Observe）"""
        system = self._build_system_prompt(expert_hint=expert_hint)
        messages = [{"role": "system", "content": system}] + self.memory.get_messages()

        response = self.llm_client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
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

                # 写入黑板（多Agent共享状态）
                self._update_blackboard(func_name, func_args, tool_result)

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
                tools=tools,
            )
            message = response.choices[0].message

        if iteration >= max_iterations:
            return "操作步骤过多，已停止。请尝试简化你的请求。"

        return message.content or "（无回复）"

    # ----------------------------------------------------------
    # 计划执行 (全量工具)
    # ----------------------------------------------------------
    async def _execute_with_plan(self, user_input: str, plan) -> str:
        """按计划逐步执行，使用全量工具"""
        all_tools = self.mcp.tools or None

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
                tools=all_tools,
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

                    # 写入黑板
                    self.blackboard.write_result(
                        step_id=f"step_{step.step_id}",
                        milestone="plan",
                        tool_name=fn,
                        result=result[:500],
                    )

                    # Reflection
                    ref = self.reflection.evaluate(fn, args, result, step.description)
                    if ref.should_retry:
                        print(f"    [反思] 重试: {ref.reasoning}")
                        result = await self.mcp.call_tool(fn, args)

                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

                response = self.llm_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=all_tools,
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

    # ----------------------------------------------------------
    # 记忆压缩
    # ----------------------------------------------------------
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

    # ----------------------------------------------------------
    # 黑板模式 - 多Agent共享状态
    # ----------------------------------------------------------
    def _update_blackboard(self, tool_name: str, tool_args: dict, tool_result: str):
        """将工具执行结果写入黑板"""
        try:
            # 根据工具类型识别实体
            if tool_name in ("list_contacts", "find_qq_by_name"):
                # 联系人信息
                if "联系人" in tool_result or "QQ号" in tool_result:
                    # 解析联系人结果并写入
                    pass  # 简化处理

            elif tool_name in ("get_weather",):
                # 天气信息 - 写入共享变量
                self.blackboard.set("last_weather", tool_result[:200])

            elif tool_name in ("search_knowledge",):
                # 知识库检索结果
                self.blackboard.set("last_knowledge_result", tool_result[:500])

            # 写入中间结果
            self.blackboard.write_result(
                step_id=f"react_{tool_name}",
                milestone="general",
                tool_name=tool_name,
                result=tool_result[:500],
            )
        except Exception as e:
            print(f"  [黑板] 更新失败: {e}")

    # ----------------------------------------------------------
    # 系统提示构建
    # ----------------------------------------------------------
    def _build_system_prompt(self, plan_context: str = "", expert_hint: str = "") -> str:
        facts = self.memory.get_facts_prompt()
        # 构建会话上下文描述
        ctx_parts = []
        if self.session_context.get("user_qq"):
            ctx_parts.append(f"当前对话用户的QQ号: {self.session_context['user_qq']}")
        if self.session_context.get("user_display_name"):
            ctx_parts.append(f"当前对话用户的名称: {self.session_context['user_display_name']}")
        if self.session_context.get("group_id"):
            ctx_parts.append(f"当前对话所在群号: {self.session_context['group_id']}")
        session_ctx = "\n".join(ctx_parts) if ctx_parts else ""

        # 加载守则
        rules_text = ""
        try:
            from assistant.agent.db import load_rules_text
            rules_text = load_rules_text()
        except Exception:
            pass

        return SYSTEM_PROMPT.format(
            session_context=session_ctx,
            user_facts=facts,
            plan_context=f"当前执行计划:\n{plan_context}" if plan_context else "",
            rules=rules_text,
            expert_hint=f"[专家模式] {expert_hint}" if expert_hint else "",
        )

    # ----------------------------------------------------------
    # 公共方法
    # ----------------------------------------------------------
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
