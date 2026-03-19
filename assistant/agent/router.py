"""
Router - 多 Agent 意图路由器

将用户消息分类到对应的专家 Agent，每个专家只加载相关工具子集。
好处:
- 工具列表更短，LLM 选择更精准
- 系统提示更聚焦，回答质量更高
- 路由失败时自动回退到全量工具模式
"""

from __future__ import annotations

from openai import OpenAI


# ============================================================
# 专家档案定义
# ============================================================
EXPERT_PROFILES: dict[str, dict] = {
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
        "description": "数据库SQL查询、知识库RAG检索、网页搜索、新闻热搜、快递物流、音乐搜索、IP/手机定位、技术趋势、文件读取、浏览器自动化",
        "tool_names": {
            # SQL
            "list_tables", "get_table_schema", "query_database",
            # 知识库 RAG
            "add_knowledge", "search_knowledge", "list_knowledge_docs", "delete_knowledge_doc",
            # 文档导入
            "import_document", "parse_document",
            # 搜索 & 新闻
            "web_search", "get_hot_news", "send_news_to_qq",
            # 生活查询
            "query_express", "search_music", "music_hot_list",
            "ip_location", "phone_area",
            # 技术
            "github_trending", "hacker_news_top", "qa_tech_recommend",
            # 文件
            "read_file", "list_directory",
            # 浏览器
            "browse_page", "login_and_get", "fill_form", "click_element", "screenshot",
        },
        "system_hint": (
            "当前为信息查询模式。优先使用工具获取准确数据，"
            "查数据库时按照 list_tables → get_table_schema → query_database 三步走。"
            "用户发送文档时，使用 import_document 导入知识库。"
            "当需要获取没有API的网页内容时，使用 browse_page 浏览器自动化。"
        ),
    },
    "task": {
        "name": "任务管理专家",
        "description": "笔记管理、定时提醒、通讯录管理、QQ消息发送、GitHub仓库监控、网站监控、守则管理、自动化工作流",
        "tool_names": {
            # 笔记
            "take_note", "list_notes", "search_notes", "delete_note",
            # 提醒
            "create_reminder", "list_reminders", "delete_reminder",
            # 通讯录
            "set_user_name", "get_user_name", "set_group_name",
            "list_contacts", "find_qq_by_name",
            # QQ
            "send_qq_message", "send_qq_group_message",
            # GitHub
            "github_watch_repo", "github_unwatch_repo", "github_list_watched",
            "github_get_latest_commits", "github_get_branches",
            # 监控
            "add_site_monitor", "remove_site_monitor", "list_site_monitors",
            # 守则
            "add_rule", "list_rules", "delete_rule",
            # 工作流
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
            "run_cpp_code", "get_leetcode_problem",
            "web_search",
        },
        "system_hint": (
            "当前为代码模式。帮助用户编写、运行和调试代码，"
            "解释代码逻辑，提供编程建议。"
        ),
    },
}


def get_expert_descriptions() -> str:
    """生成专家列表描述，供路由 prompt 使用"""
    lines = []
    for key, profile in EXPERT_PROFILES.items():
        lines.append(f"- {key}: {profile['description']}")
    lines.append("- general: 不确定、复杂综合任务、或以上专家都不匹配")
    return "\n".join(lines)


_ROUTER_PROMPT = f"""你是一个意图分类器。根据用户消息，判断应该由哪个专家处理。

可选专家:
{get_expert_descriptions()}

只回复一个词（chat/query/task/code/general），不要回复其他内容。"""


class Router:
    """轻量意图路由器，用低开销 LLM 调用分类用户消息"""

    def __init__(self, llm_client: OpenAI, model: str):
        self.llm_client = llm_client
        self.model = model

    def classify(self, message: str, recent_context: str = "") -> str:
        """
        将用户消息分类到专家类别。

        Returns:
            专家 key: "chat" / "query" / "task" / "code" / "general"
        """
        user_content = message
        if recent_context:
            user_content = f"[最近对话上下文]\n{recent_context}\n\n[当前消息]\n{message}"

        try:
            resp = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _ROUTER_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=5,
                temperature=0,
            )
            result = resp.choices[0].message.content.strip().lower()

            if result in EXPERT_PROFILES or result == "general":
                return result

            # LLM 返回了意外内容，尝试提取关键词
            for key in EXPERT_PROFILES:
                if key in result:
                    return key

            return "general"

        except Exception as e:
            print(f"[Router] 分类失败，回退到 general: {e}")
            return "general"
