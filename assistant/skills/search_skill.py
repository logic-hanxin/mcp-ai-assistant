"""搜索 Skill - 多源网页搜索"""

import html
import re
from assistant.skills.base import BaseSkill, ToolDefinition, register


def _clean_html_text(value: str) -> str:
    text = re.sub(r"<.*?>", "", value or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("//"):
        url = "https:" + url
    return url


def _search_sogou(query: str, max_results: int = 5) -> list[dict]:
    try:
        import httpx
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

        blocks = re.findall(
            r'<h3[^>]*>.*?<a[^>]*href="(.*?)"[^>]*>(.*?)</a>.*?</h3>.*?'
            r'(?:<p[^>]*class="[^"]*"[^>]*>(.*?)</p>|<div[^>]*class="[^"]*"[^>]*>(.*?)</div>)',
            html, re.DOTALL,
        )

        for url, title_html, snippet1, snippet2 in blocks[:max_results]:
            title = _clean_html_text(title_html)
            snippet = _clean_html_text(snippet1 or snippet2)
            if title:
                results.append({
                    "title": title,
                    "snippet": snippet[:120],
                    "url": _normalize_url(url),
                    "source": "sogou",
                })

        if not results:
            titles = re.findall(r'<h3[^>]*>\s*<a[^>]*>(.*?)</a>\s*</h3>', html, re.DOTALL)
            for title_html in titles[:max_results]:
                title = _clean_html_text(title_html)
                if title:
                    results.append({"title": title, "snippet": "", "url": "", "source": "sogou"})

        return results

    except Exception:
        return []


def _search_duckduckgo(query: str, max_results: int = 5) -> list[dict]:
    try:
        import httpx
        resp = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return []

        text = resp.text
        results = []
        blocks = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="(.*?)"[^>]*>(.*?)</a>.*?'
            r'(?:<a[^>]*class="result__snippet"[^>]*>(.*?)</a>|<div[^>]*class="result__snippet"[^>]*>(.*?)</div>)?',
            text,
            re.DOTALL,
        )
        for url, title_html, snippet1, snippet2 in blocks[:max_results]:
            title = _clean_html_text(title_html)
            snippet = _clean_html_text(snippet1 or snippet2)
            if title:
                results.append(
                    {
                        "title": title,
                        "snippet": snippet[:160],
                        "url": _normalize_url(url),
                        "source": "duckduckgo",
                    }
                )
        return results
    except Exception:
        return []


def _search_bing(query: str, max_results: int = 5) -> list[dict]:
    try:
        import httpx
        resp = httpx.get(
            "https://www.bing.com/search",
            params={"q": query},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return []
        text = resp.text
        results = []
        blocks = re.findall(
            r'<li class="b_algo".*?<h2><a href="(.*?)"[^>]*>(.*?)</a></h2>.*?'
            r'<p>(.*?)</p>',
            text,
            re.DOTALL,
        )
        for url, title_html, snippet_html in blocks[:max_results]:
            title = _clean_html_text(title_html)
            snippet = _clean_html_text(snippet_html)
            if title:
                results.append(
                    {
                        "title": title,
                        "snippet": snippet[:160],
                        "url": _normalize_url(url),
                        "source": "bing",
                    }
                )
        return results
    except Exception:
        return []


def _merge_results(query: str, max_results: int = 5) -> list[dict]:
    merged = []
    seen: set[tuple[str, str]] = set()
    providers = (_search_duckduckgo, _search_bing, _search_sogou)
    per_provider = max(max_results, 5)

    for provider in providers:
        for item in provider(query, per_provider):
            key = (
                (item.get("url") or "").strip().lower(),
                (item.get("title") or "").strip().lower(),
            )
            if key in seen:
                continue
            if not item.get("title"):
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= max_results:
                return merged
    return merged[:max_results]


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
                metadata={
                    "category": "read",
                    "blackboard_writes": ["last_search_result"],
                    "required_all": ["query"],
                    "store_result": ["last_search_result"],
                },
                result_parser=self._parse_search_result,
                keywords=["搜索", "查资料", "查网页", "实时信息", "上网查"],
                intents=["web_search", "find_information"],
            ),
        ]

    def _search(self, query: str, max_results: int = 5) -> str:
        if not query.strip():
            return "请提供搜索关键词。"

        results = _merge_results(query, max_results)
        if not results:
            return f"没有找到与 '{query}' 相关的结果。"

        lines = [f"搜索: {query}  (共 {len(results)} 条结果)"]
        lines.append("")
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            if r["snippet"]:
                lines.append(f"   {r['snippet']}")
            if r.get("url"):
                lines.append(f"   链接: {r['url']}")
            if r.get("source"):
                lines.append(f"   来源: {r['source']}")
            lines.append("")

        return "\n".join(lines)

    def _parse_search_result(self, args: dict, result: str) -> dict | None:
        query = str(args.get("query", "")).strip()
        if not query:
            return None

        results = []
        current: dict[str, str] | None = None
        for line in result.splitlines():
            title_match = re.match(r"^\d+\.\s+(.+)$", line.strip())
            if title_match:
                if current:
                    results.append(current)
                current = {"title": title_match.group(1).strip(), "snippet": "", "url": "", "source": ""}
                continue
            if current and line.strip().startswith("链接:"):
                current["url"] = line.split("链接:", 1)[1].strip()
                continue
            if current and line.strip().startswith("来源:"):
                current["source"] = line.split("来源:", 1)[1].strip()
                continue
            if current and line.strip():
                current["snippet"] = line.strip()
        if current:
            results.append(current)

        return {
            "query": query,
            "results": results,
            "result": result[:500],
        }


register(SearchSkill)
