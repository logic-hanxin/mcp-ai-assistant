"""热点新闻 Skill - 获取热点新闻，支持手动触发推送"""

import os
import httpx
from assistant.skills.base import BaseSkill, ToolDefinition, register

NAPCAT_API_URL = os.getenv("NAPCAT_API_URL", "http://127.0.0.1:3000")

# 新闻源配置（免费公开 API）
NEWS_SOURCES = [
    {
        "name": "微博热搜",
        "url": "https://weibo.com/ajax/side/hotSearch",
        "parser": "_parse_weibo",
    },
    {
        "name": "知乎热榜",
        "url": "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=20",
        "parser": "_parse_zhihu",
    },
]

# 备用聚合 API（当主源不可用时）
BACKUP_API = "https://api.vvhan.com/api/hotlist/{source}"
BACKUP_SOURCES = ["wbHot", "zhihuHot", "baiduRD"]


def fetch_hot_news(max_per_source: int = 15) -> dict[str, list[str]]:
    """从多个来源获取热点新闻标题，返回 {来源名: [标题列表]}"""
    results: dict[str, list[str]] = {}

    # 尝试备用聚合 API（更稳定）
    source_names = {"wbHot": "微博热搜", "zhihuHot": "知乎热榜", "baiduRD": "百度热点"}
    for src in BACKUP_SOURCES:
        try:
            resp = httpx.get(
                BACKUP_API.format(source=src),
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    items = data.get("data", [])[:max_per_source]
                    titles = [item.get("title", "") for item in items if item.get("title")]
                    if titles:
                        results[source_names.get(src, src)] = titles
        except Exception:
            continue

    # 如果备用 API 全部失败，尝试直接抓取微博
    if not results:
        try:
            resp = httpx.get(
                "https://weibo.com/ajax/side/hotSearch",
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code == 200:
                data = resp.json()
                realtime = data.get("data", {}).get("realtime", [])[:max_per_source]
                titles = [item.get("note", "") for item in realtime if item.get("note")]
                if titles:
                    results["微博热搜"] = titles
        except Exception:
            pass

    return results


def format_news_text(news: dict[str, list[str]], max_items: int = 10) -> str:
    """将新闻数据格式化为可读文本"""
    if not news:
        return "暂时无法获取热点新闻，请稍后再试。"

    lines = ["[今日热点新闻]"]
    for source, titles in news.items():
        lines.append(f"\n【{source}】")
        for i, title in enumerate(titles[:max_items], 1):
            lines.append(f"  {i}. {title}")
    return "\n".join(lines)


class NewsSkill(BaseSkill):
    name = "news"
    description = "获取热点新闻，支持手动触发推送"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_hot_news",
                description=(
                    "获取当前热点新闻（微博热搜、知乎热榜、百度热点）。"
                    "返回各平台的热门话题列表。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "max_items": {
                            "type": "integer",
                            "description": "每个来源最多返回的新闻条数，默认10",
                            "default": 10,
                        },
                    },
                },
                handler=self._get_hot_news,
            ),
            ToolDefinition(
                name="send_news_to_qq",
                description=(
                    "立即获取热点新闻并发送给指定QQ用户。"
                    "会自动抓取当前热点并整理后推送。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "qq_number": {
                            "type": "string",
                            "description": "接收新闻的QQ号",
                        },
                    },
                    "required": ["qq_number"],
                },
                handler=self._send_news_to_qq,
            ),
        ]

    def _get_hot_news(self, max_items: int = 10) -> str:
        news = fetch_hot_news()
        return format_news_text(news, max_items=max_items)

    def _send_news_to_qq(self, qq_number: str) -> str:
        news = fetch_hot_news()
        if not news:
            return "获取新闻失败，无法发送。"

        text = format_news_text(news, max_items=10)

        try:
            resp = httpx.post(
                f"{NAPCAT_API_URL}/send_private_msg",
                json={
                    "user_id": int(qq_number),
                    "message": [{"type": "text", "data": {"text": text}}],
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "ok" or data.get("retcode") == 0:
                return f"热点新闻已发送给 QQ:{qq_number}"
            return f"发送失败: {data.get('message', '未知错误')}"
        except Exception as e:
            return f"发送失败: {e}"


register(NewsSkill)
