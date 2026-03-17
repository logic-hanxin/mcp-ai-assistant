"""热点新闻 Skill - 获取热点新闻，支持手动触发推送"""

import os
import httpx
from assistant.skills.base import BaseSkill, ToolDefinition, register

NAPCAT_API_URL = os.getenv("NAPCAT_API_URL", "http://127.0.0.1:3000")
_UA = {"User-Agent": "Mozilla/5.0"}


def _fetch_baidu(max_items: int) -> list[str]:
    """百度热搜"""
    try:
        resp = httpx.get(
            "https://top.baidu.com/api/board?platform=wise&tab=realtime",
            timeout=10, headers=_UA,
        )
        if resp.status_code != 200:
            return []
        cards = resp.json().get("data", {}).get("cards", [])
        if not cards:
            return []
        # 第一个 card 的 content 列表
        content = cards[0].get("content", [])
        if content and isinstance(content[0], dict) and "content" in content[0]:
            items = content[0]["content"]
        else:
            items = content
        return [item["word"] for item in items[:max_items] if item.get("word")]
    except Exception:
        return []


def _fetch_toutiao(max_items: int) -> list[str]:
    """今日头条热榜"""
    try:
        resp = httpx.get(
            "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
            timeout=10, headers=_UA,
        )
        if resp.status_code != 200:
            return []
        items = resp.json().get("data", [])
        return [item["Title"] for item in items[:max_items] if item.get("Title")]
    except Exception:
        return []


def _fetch_pengpai(max_items: int) -> list[str]:
    """澎湃新闻热榜"""
    try:
        resp = httpx.get(
            "https://cache.thepaper.cn/contentapi/wwwIndex/rightSidebar",
            timeout=10, headers=_UA,
        )
        if resp.status_code != 200:
            return []
        hot_news = resp.json().get("data", {}).get("hotNews", [])
        return [
            item.get("name") or item.get("title", "")
            for item in hot_news[:max_items]
            if item.get("name") or item.get("title")
        ]
    except Exception:
        return []


def fetch_hot_news(max_per_source: int = 15) -> dict[str, list[str]]:
    """从多个来源获取热点新闻标题，返回 {来源名: [标题列表]}"""
    results: dict[str, list[str]] = {}

    fetchers = [
        ("百度热搜", _fetch_baidu),
        ("头条热榜", _fetch_toutiao),
        ("澎湃新闻", _fetch_pengpai),
    ]

    for name, fetcher in fetchers:
        try:
            titles = fetcher(max_per_source)
            if titles:
                results[name] = titles
        except Exception:
            continue

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
    description = "获取热点新闻（百度热搜、头条热榜、澎湃新闻），支持手动触发推送"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_hot_news",
                description=(
                    "获取当前热点新闻（百度热搜、头条热榜、澎湃新闻）。"
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
