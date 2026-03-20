"""
Router - 多 Agent 意图路由器

将用户消息分类到对应的专家 Agent，每个专家只加载相关工具子集。
好处:
- 工具列表更短，LLM 选择更精准
- 系统提示更聚焦，回答质量更高
- 路由失败时自动回退到全量工具模式
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - 仅用于测试环境降级
    OpenAI = Any


BASE_EXPERT_PROFILES: dict[str, dict] = {
    "chat": {
        "name": "闲聊助手",
        "description": "日常闲聊、问候寒暄、天气查询、翻译、计算、时间查询、图片识别、王者荣耀",
        "tool_names": {
            "get_weather", "calculate", "translate_text",
            "get_current_time", "ocr_image", "understand_image", "scan_qrcode",
            "query_hero_power", "search_hero",
        },
        "system_hint": (
            "当前为闲聊模式。像真正的群友一样轻松自然地交流，"
            "回复简短有趣，不要长篇大论。"
        ),
    },
    "query": {
        "name": "信息查询专家",
        "description": "数据库SQL查询、知识库RAG检索、网页搜索、新闻热搜、快递物流、音乐搜索、IP/手机定位、技术趋势、文件读取、网页爬取",
        "tool_names": {
            "list_tables", "get_table_schema", "query_database",
            "add_knowledge", "search_knowledge", "list_knowledge_docs", "delete_knowledge_doc",
            "import_document", "parse_document",
            "web_search", "get_hot_news", "send_news_to_qq",
            "query_express", "search_music", "music_hot_list",
            "ip_location", "phone_area",
            "github_trending", "hacker_news_top", "qa_tech_recommend",
            "read_file", "list_directory",
            "browse_page", "browse_with_headers", "post_form", "get_json",
        },
        "system_hint": (
            "当前为信息查询模式。优先使用工具获取准确数据，"
            "查数据库时按照 list_tables → get_table_schema → query_database 三步走。"
            "用户发送文档时，使用 import_document 导入知识库。"
            "需要获取没有API的网页内容时，使用 browse_page 网页爬取。"
        ),
    },
    "task": {
        "name": "任务管理专家",
        "description": "笔记管理、定时提醒、通讯录管理、QQ消息发送、GitHub仓库监控、网站监控、守则管理、自动化工作流",
        "tool_names": {
            "take_note", "list_notes", "search_notes", "delete_note",
            "create_reminder", "list_reminders", "delete_reminder",
            "set_user_name", "get_user_name", "set_group_name",
            "list_contacts", "find_qq_by_name",
            "send_qq_message", "send_qq_group_message",
            "notify_contact_by_name", "notify_group_by_name", "broadcast_last_result",
            "github_watch_repo", "github_unwatch_repo", "github_list_watched",
            "github_get_latest_commits", "github_get_branches",
            "add_site_monitor", "remove_site_monitor", "list_site_monitors",
            "add_rule", "list_rules", "delete_rule",
            "create_workflow", "list_workflows", "toggle_workflow",
            "delete_workflow", "run_workflow_now",
        },
        "system_hint": (
            "当前为任务管理模式。准确执行用户的管理操作，"
            "操作前确认关键参数（如QQ号、时间等）。"
        ),
    },
    "code": {
        "name": "代码助手",
        "description": "运行C++代码、LeetCode题目查询、代码相关问题",
        "tool_names": {
            "run_cpp_code", "get_leetcode_problem", "web_search",
        },
        "system_hint": (
            "当前为代码模式。帮助用户编写、运行和调试代码，"
            "解释代码逻辑，提供编程建议。"
        ),
    },
}


ROUTER_METADATA_RULES: dict[str, dict[str, set[str]]] = {
    "chat": {
        "skills": {"weather", "translate", "time", "calc", "vision", "wzry"},
        "categories": {"chat"},
        "side_effects": set(),
    },
    "query": {
        "skills": {"search", "news", "knowledge", "sql", "document", "browser", "file", "express", "music", "location", "techtrend"},
        "categories": {"read", "query"},
        "side_effects": set(),
    },
    "task": {
        "skills": {"note", "reminder", "contacts", "qq_message", "group_ops", "github", "monitor", "rule", "workflow"},
        "categories": {"write", "notify", "admin"},
        "side_effects": {"external_message", "scheduled_notification", "data_write", "admin_operation", "external_trigger"},
    },
    "code": {
        "skills": {"code"},
        "categories": set(),
        "side_effects": set(),
    },
}


def _humanize_skill_name(skill: str) -> str:
    parts = [part for part in str(skill).strip().split("_") if part]
    if not parts:
        return ""
    if all(part.isascii() for part in parts):
        return "/".join(parts)
    return "".join(parts)


def _summarize_expert_metadata(expert_key: str, tool_metadata: dict[str, dict] | None = None, limit: int = 6) -> str:
    if not tool_metadata:
        return ""

    matched_skills: list[str] = []
    matched_categories: list[str] = []
    matched_keywords: list[str] = []
    matched_intents: list[str] = []
    rules = ROUTER_METADATA_RULES.get(expert_key, {})
    for meta in tool_metadata.values():
        skill = str(meta.get("skill", "")).strip()
        category = str(meta.get("category", "")).strip()
        side_effect = str(meta.get("side_effect", "")).strip()

        matches = (
            (skill and skill in rules.get("skills", set()))
            or (category and category in rules.get("categories", set()))
            or (side_effect and side_effect in rules.get("side_effects", set()))
        )
        if not matches:
            continue

        readable_skill = _humanize_skill_name(skill)
        if readable_skill and readable_skill not in matched_skills:
            matched_skills.append(readable_skill)
        if category and category not in matched_categories:
            matched_categories.append(category)
        for keyword in meta.get("keywords", [])[:3]:
            keyword = str(keyword).strip()
            if keyword and keyword not in matched_keywords:
                matched_keywords.append(keyword)
        for intent in meta.get("intents", [])[:2]:
            intent = str(intent).strip()
            if intent and intent not in matched_intents:
                matched_intents.append(intent)

    summary_parts = []
    if matched_skills:
        summary_parts.append("技能: " + "、".join(matched_skills[:limit]))
    if matched_categories:
        summary_parts.append("类别: " + "、".join(matched_categories[:3]))
    if matched_keywords:
        summary_parts.append("关键词: " + "、".join(matched_keywords[:5]))
    if matched_intents:
        summary_parts.append("意图: " + "、".join(matched_intents[:4]))
    return "；".join(summary_parts)


def build_expert_profiles(tool_metadata: dict[str, dict] | None = None) -> dict[str, dict]:
    """根据 tool metadata 扩展专家可用工具集合。"""
    profiles = deepcopy(BASE_EXPERT_PROFILES)

    if tool_metadata:
        for tool_name, meta in tool_metadata.items():
            skill = str(meta.get("skill", "")).strip()
            category = str(meta.get("category", "")).strip()
            side_effect = str(meta.get("side_effect", "")).strip()

            for expert_key, rules in ROUTER_METADATA_RULES.items():
                if (
                    (skill and skill in rules["skills"])
                    or (category and category in rules["categories"])
                    or (side_effect and side_effect in rules["side_effects"])
                ):
                    profiles[expert_key]["tool_names"].add(tool_name)

    for expert_key, profile in profiles.items():
        extra_summary = _summarize_expert_metadata(expert_key, tool_metadata)
        if extra_summary:
            profile["description"] = f"{profile['description']}；扩展能力: {extra_summary}"

    return profiles


def get_expert_descriptions(expert_profiles: dict[str, dict] | None = None) -> str:
    """生成专家列表描述，供路由 prompt 使用"""
    profiles = expert_profiles or BASE_EXPERT_PROFILES
    lines = []
    for key, profile in profiles.items():
        lines.append(f"- {key}: {profile['description']}")
    lines.append("- general: 不确定、复杂综合任务、或以上专家都不匹配")
    return "\n".join(lines)


def _normalize_intent_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text).strip().lower())


def score_expert_intents(message: str, tool_metadata: dict[str, dict] | None = None) -> dict[str, float]:
    """基于 keywords/intents 对专家做轻量预打分。"""
    scores = {key: 0.0 for key in ROUTER_METADATA_RULES}
    if not message or not tool_metadata:
        return scores

    normalized = _normalize_intent_text(message)
    lowered = str(message).lower()

    for meta in tool_metadata.values():
        skill = str(meta.get("skill", "")).strip()
        category = str(meta.get("category", "")).strip()
        side_effect = str(meta.get("side_effect", "")).strip()

        matched_experts = [
            expert_key
            for expert_key, rules in ROUTER_METADATA_RULES.items()
            if (
                (skill and skill in rules["skills"])
                or (category and category in rules["categories"])
                or (side_effect and side_effect in rules["side_effects"])
            )
        ]
        if not matched_experts:
            continue

        match_score = 0.0
        for keyword in meta.get("keywords", []):
            keyword_text = str(keyword).strip()
            if not keyword_text:
                continue
            if _normalize_intent_text(keyword_text) in normalized:
                match_score += 1.0

        for intent in meta.get("intents", []):
            intent_text = str(intent).strip().lower()
            if not intent_text:
                continue
            if intent_text in lowered:
                match_score += 1.5

        if match_score <= 0:
            continue

        for expert_key in matched_experts:
            scores[expert_key] += match_score

    return scores


class Router:
    """轻量意图路由器，用低开销 LLM 调用分类用户消息"""

    def __init__(self, llm_client: OpenAI, model: str, tool_metadata: dict[str, dict] | None = None):
        self.llm_client = llm_client
        self.model = model
        self.tool_metadata = tool_metadata or {}
        self.expert_profiles = build_expert_profiles(tool_metadata)
        self.router_prompt = self._build_router_prompt()

    def update_tool_metadata(self, tool_metadata: dict[str, dict] | None = None):
        """刷新专家档案，让路由工具集跟随 metadata 演进。"""
        self.tool_metadata = tool_metadata or {}
        self.expert_profiles = build_expert_profiles(tool_metadata)
        self.router_prompt = self._build_router_prompt()

    def _build_router_prompt(self) -> str:
        return (
            "你是一个意图分类器。根据用户消息，判断应该由哪个专家处理。\n\n"
            f"可选专家:\n{get_expert_descriptions(self.expert_profiles)}\n\n"
            "只回复一个词（chat/query/task/code/general），不要回复其他内容。"
        )

    def get_profiles(self) -> dict[str, dict]:
        return self.expert_profiles

    def classify(self, message: str, recent_context: str = "") -> str:
        """
        将用户消息分类到专家类别。

        Returns:
            专家 key: "chat" / "query" / "task" / "code" / "general"
        """
        user_content = message
        if recent_context:
            user_content = f"[最近对话上下文]\n{recent_context}\n\n[当前消息]\n{message}"

        hint = self._intent_match(message)
        if hint and hint["score"] >= 1.0 and hint["confidence"] >= 1.0:
            return hint["expert"]

        try:
            system_prompt = self.router_prompt
            if hint:
                system_prompt = (
                    f"{self.router_prompt}\n\n"
                    f"[额外提示] 基于关键词/意图匹配，{hint['expert']} 更可能相关，"
                    f"置信分数 {hint['confidence']:.1f}。如果用户消息明显不符，可忽略该提示。"
                )
            resp = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=5,
                temperature=0,
            )
            result = resp.choices[0].message.content.strip().lower()

            if result in self.expert_profiles or result == "general":
                return result

            for key in self.expert_profiles:
                if key in result:
                    return key

            return "general"

        except Exception as e:
            print(f"[Router] 分类失败，回退到 general: {e}")
            return hint["expert"] if hint else "general"

    def _intent_match(self, message: str) -> dict[str, float | str] | None:
        scores = score_expert_intents(message, self.tool_metadata)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if not ranked or ranked[0][1] <= 0:
            return None
        expert, score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
        confidence = score - runner_up if score > runner_up else score
        return {"expert": expert, "score": score, "confidence": confidence}


EXPERT_PROFILES = build_expert_profiles()
