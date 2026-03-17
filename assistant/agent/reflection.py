"""
Reflection - 自我反思模块

在工具调用失败或结果不理想时:
1. 分析失败原因
2. 决定重试策略（换参数 / 换工具 / 放弃并告知用户）
3. 限制最大重试次数，避免死循环
"""

from dataclasses import dataclass


@dataclass
class ReflectionResult:
    """反思结果"""
    should_retry: bool
    strategy: str        # "retry_same" / "try_alternative" / "give_up"
    reasoning: str       # 反思过程
    suggestion: str = "" # 给 LLM 的建议（如换参数）


REFLECTION_PROMPT = """你是一个自我反思模块。工具调用出现了问题，请分析原因并给出建议。

工具名: {tool_name}
传入参数: {tool_args}
返回结果: {tool_result}
用户原始请求: {user_request}

请分析这个结果是否正常。如果结果包含错误信息或明显不合理，请给出建议。

返回 JSON:
{{
    "is_success": true/false,
    "reasoning": "分析过程",
    "should_retry": true/false,
    "strategy": "retry_same 或 try_alternative 或 give_up",
    "suggestion": "如果重试，给出修正建议"
}}

只返回 JSON。"""


class Reflection:
    """自我反思引擎"""

    def __init__(self, llm_client, model: str, max_retries: int = 2):
        self.llm = llm_client
        self.model = model
        self.max_retries = max_retries
        self._retry_counts: dict[str, int] = {}  # tool_name -> retry count

    def evaluate(
        self,
        tool_name: str,
        tool_args: dict,
        tool_result: str,
        user_request: str,
    ) -> ReflectionResult:
        """评估工具调用结果，决定是否需要重试"""
        # 快速检查：结果包含明显错误关键词
        error_keywords = ["出错", "失败", "不存在", "错误", "error", "failed", "not found"]
        has_error = any(kw in tool_result.lower() for kw in error_keywords)

        if not has_error:
            # 结果看起来正常，重置重试计数
            self._retry_counts.pop(tool_name, None)
            return ReflectionResult(
                should_retry=False,
                strategy="success",
                reasoning="工具调用结果正常",
            )

        # 检查重试次数
        current_retries = self._retry_counts.get(tool_name, 0)
        if current_retries >= self.max_retries:
            self._retry_counts.pop(tool_name, None)
            return ReflectionResult(
                should_retry=False,
                strategy="give_up",
                reasoning=f"工具 {tool_name} 已重试 {current_retries} 次仍失败，放弃重试",
            )

        # 使用 LLM 进行深度反思
        try:
            response = self.llm.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": REFLECTION_PROMPT.format(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        tool_result=tool_result,
                        user_request=user_request,
                    )}
                ],
                response_format={"type": "json_object"},
            )

            import json
            result = json.loads(response.choices[0].message.content)

            if result.get("should_retry"):
                self._retry_counts[tool_name] = current_retries + 1

            return ReflectionResult(
                should_retry=result.get("should_retry", False),
                strategy=result.get("strategy", "give_up"),
                reasoning=result.get("reasoning", ""),
                suggestion=result.get("suggestion", ""),
            )
        except Exception:
            # 反思本身失败，不重试
            return ReflectionResult(
                should_retry=False,
                strategy="give_up",
                reasoning="反思模块自身出错，跳过重试",
            )

    def reset(self):
        """重置所有重试计数"""
        self._retry_counts.clear()
