"""
Reflection - 自我反思模块

在工具调用失败或结果不理想时:
1. 分析失败原因
2. 决定重试策略（换参数 / 换工具 / 放弃并告知用户）
3. 限制最大重试次数，避免死循环
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ReflectionResult:
    """反思结果"""
    should_retry: bool
    strategy: str        # "retry_same" / "try_alternative" / "give_up"
    reasoning: str       # 反思过程
    suggestion: str = "" # 给 LLM 的建议（如换参数）
    conflict_report: str = ""  # 冲突检测报告（多源结果不一致时）


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


# ============ 冲突解决模块 ============


@dataclass
class SourceCredibility:
    """数据源置信度配置"""
    # 预设的工具置信度权重 (0.0 - 1.0)
    DEFAULT_CREDIBILITY = {
        # 官方/API 类 - 最高置信度
        "get_weather": 0.95,
        "query_express": 0.95,
        "get_current_time": 0.95,
        "get_leetcode_problem": 0.95,
        "run_cpp_code": 0.90,
        # 数据库类
        "query_database": 0.90,
        "list_tables": 0.85,
        "get_table_schema": 0.85,
        "list_contacts": 0.90,
        "find_qq_by_name": 0.85,
        # 知识库
        "search_knowledge": 0.85,
        # 搜索类 - 置信度较低
        "web_search": 0.70,
        "github_trending": 0.75,
        "hacker_news_top": 0.70,
        "github_get_latest_commits": 0.80,
        # 用户输入类
        "take_note": 0.80,
        "add_rule": 0.80,
    }

    @classmethod
    def get_credibility(cls, tool_name: str) -> float:
        """获取工具的置信度权重"""
        return cls.DEFAULT_CREDIBILITY.get(tool_name, 0.50)

    @classmethod
    def register_source(cls, tool_name: str, credibility: float):
        """注册新的数据源及其置信度"""
        if 0.0 <= credibility <= 1.0:
            cls.DEFAULT_CREDIBILITY[tool_name] = credibility


@dataclass
class MultiSourceResult:
    """多源查询结果"""
    tool_name: str
    result: str
    credibility: float
    timestamp: float = 0.0


@dataclass
class ConflictReport:
    """冲突检测报告"""
    is_conflict: bool
    sources: list[str]           # 冲突的来源列表
    conflicting_points: list[str]  # 冲突点描述
    resolved_result: str = ""   # 仲裁结果
    resolution_method: str = ""  # 仲裁方式: "credibility_priority" / "majority_vote" / "llm_arbitration"
    confidence: float = 0.0      # 仲裁结果置信度


CONFLICT_DETECTION_PROMPT = """你是一个事实核查模块。多个数据源返回了不一致的结果，请分析冲突点并给出仲裁建议。

用户查询: {user_query}

数据源返回:
{sources_info}

请分析这些结果的差异点，判断哪个更可信。

返回 JSON:
{{
    "is_conflict": true/false,
    "conflicting_points": ["冲突点1", "冲突点2"],
    "resolved_result": "仲裁后的结果",
    "resolution_method": "credibility_priority / majority_vote / llm_arbitration",
    "confidence": 0.0-1.0,
    "reasoning": "仲裁理由"
}}

只返回 JSON。"""


class ConflictDetector:
    """冲突检测器 - 检测多源结果不一致并仲裁"""

    def __init__(self, llm_client, model: str):
        self.llm = llm_client
        self.model = model
        self._result_cache: list[MultiSourceResult] = []

    def add_result(self, tool_name: str, result: str, timestamp: float = 0.0):
        """添加一个查询结果到缓存"""
        credibility = SourceCredibility.get_credibility(tool_name)
        self._result_cache.append(MultiSourceResult(
            tool_name=tool_name,
            result=result,
            credibility=credibility,
            timestamp=timestamp,
        ))

    def clear(self):
        """清空缓存"""
        self._result_cache.clear()

    def detect_conflict(self, user_query: str = "") -> ConflictReport:
        """
        检测缓存中的结果是否有冲突
        如果有多个来源返回了结果，进行冲突检测和仲裁
        """
        if len(self._result_cache) < 2:
            return ConflictReport(
                is_conflict=False,
                sources=[],
                conflicting_points=[],
                resolution_method="insufficient_data",
                confidence=1.0,
            )

        # 简单冲突检测：检查是否有明显的矛盾关键词
        results_text = "\n".join(
            f"来源: {r.tool_name} (置信度: {r.credibility})\n结果: {r.result[:200]}"
            for r in self._result_cache
        )

        try:
            response = self.llm.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个事实核查专家。"},
                    {"role": "user", "content": CONFLICT_DETECTION_PROMPT.format(
                        user_query=user_query,
                        sources_info=results_text,
                    )}
                ],
                response_format={"type": "json_object"},
            )

            import json
            result = json.loads(response.choices[0].message.content)

            if not result.get("is_conflict", False):
                return ConflictReport(
                    is_conflict=False,
                    sources=[r.tool_name for r in self._result_cache],
                    conflicting_points=[],
                    resolved_result=self._get_highest_credibility_result(),
                    resolution_method="credibility_priority",
                    confidence=result.get("confidence", 0.8),
                )

            # 存在冲突，返回仲裁报告
            return ConflictReport(
                is_conflict=True,
                sources=[r.tool_name for r in self._result_cache],
                conflicting_points=result.get("conflicting_points", []),
                resolved_result=result.get("resolved_result", ""),
                resolution_method=result.get("resolution_method", "llm_arbitration"),
                confidence=result.get("confidence", 0.5),
            )

        except Exception:
            # LLM 仲裁失败，使用置信度优先级
            return ConflictReport(
                is_conflict=True,
                sources=[r.tool_name for r in self._result_cache],
                conflicting_points=["检测失败，使用置信度优先级"],
                resolved_result=self._get_highest_credibility_result(),
                resolution_method="credibility_priority",
                confidence=0.5,
            )

    def _get_highest_credibility_result(self) -> str:
        """返回置信度最高的来源结果"""
        if not self._result_cache:
            return ""
        sorted_results = sorted(self._result_cache, key=lambda x: x.credibility, reverse=True)
        return f"[来源: {sorted_results[0].tool_name}] {sorted_results[0].result[:500]}"

    def get_all_results(self) -> list[dict]:
        """获取所有缓存的结果（供调试或展示用）"""
        return [
            {
                "tool": r.tool_name,
                "credibility": r.credibility,
                "result": r.result[:200] if len(r.result) > 200 else r.result,
            }
            for r in sorted(self._result_cache, key=lambda x: x.credibility, reverse=True)
        ]
