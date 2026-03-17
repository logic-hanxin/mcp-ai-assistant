"""搜索 Skill - 基于搜狗搜索的网页搜索"""

import re
import httpx
from assistant.skills.base import BaseSkill, ToolDefinition, register


def _search_sogou(query: str, max_results: int = 5) -> list[dict]:
    """搜狗搜索，返回 [{title, snippet, url}]"""
    try:
        resp = httpx.get(
            "https://www.sogou.com/web",
            params={"query": query},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return []

        html = resp.text
        results = []

        # 提取搜索结果块
        blocks = re.findall(
            r'<h3[^>]*>.*?<a[^>]*href="(.*?)"[^>]*>(.*?)</a>.*?</h3>.*?'
            r'(?:<p[^>]*class="[^"]*"[^>]*>(.*?)</p>|<div[^>]*class="[^"]*"[^>]*>(.*?)</div>)',
            html, re.DOTALL,
        )

        for url, title_html, snippet1, snippet2 in blocks[:max_results]:
            title = re.sub(r"<.*?>", "", title_html).strip()
            snippet = re.sub(r"<.*?>", "", snippet1 or snippet2).strip()
            if title:
                results.append({
                    "title": title,
                    "snippet": snippet[:120],
                    "url": url,
                })

        # 如果正则没匹配到，尝试更宽松的匹配
        if not results:
            titles = re.findall(r'<h3[^>]*>\s*<a[^>]*>(.*?)</a>\s*</h3>', html, re.DOTALL)
            for title_html in titles[:max_results]:
                title = re.sub(r"<.*?>", "", title_html).strip()
                if title:
                    results.append({"title": title, "snippet": "", "url": ""})

        return results

    except Exception:
        return []


class SearchSkill(BaseSkill):
    name = "search"
    description = "网页搜索，获取实时信息"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="web_search",
                description=(
                    "搜索互联网获取实时信息。适用于查询最新资讯、技术问题、"
                    "百科知识、产品信息等。返回搜索结果的标题和摘要。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "最多返回的结果数，默认5",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
                handler=self._search,
            ),
        ]

    def _search(self, query: str, max_results: int = 5) -> str:
        if not query.strip():
            return "请提供搜索关键词。"

        results = _search_sogou(query, max_results)
        if not results:
            return f"没有找到与 '{query}' 相关的结果。"

        lines = [f"搜索: {query}  (共 {len(results)} 条结果)"]
        lines.append("")
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            if r["snippet"]:
                lines.append(f"   {r['snippet']}")
            lines.append("")

        return "\n".join(lines)


register(SearchSkill)
