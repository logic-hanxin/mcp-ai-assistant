"""搜索 Skill - 多源网页搜索与正文抓取"""

import html
import re
from urllib.parse import urlparse
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


def _detect_query_topics(query: str) -> set[str]:
    query = (query or "").lower()
    topics = set()
    movie_keywords = ("电影", "演员", "剧情", "导演", "票房", "豆瓣", "色戒", "上映", "影视")
    if any(keyword in query for keyword in movie_keywords):
        topics.add("movie")
    person_keywords = ("是谁", "人物", "介绍", "简历", "资料", "信息", "汤唯", "明星")
    if any(keyword in query for keyword in person_keywords):
        topics.add("person")
    tech_keywords = ("api", "github", "python", "mcp", "文档", "sdk", "代码", "技术")
    if any(keyword in query for keyword in tech_keywords):
        topics.add("tech")
    return topics


def _score_result(query: str, item: dict) -> tuple[int, int, int]:
    url = (item.get("url") or "").lower()
    title = (item.get("title") or "").lower()
    snippet = (item.get("snippet") or "").lower()
    text = f"{title} {snippet}"
    topics = _detect_query_topics(query)

    domain_score = 0
    if "movie" in topics:
        if "douban.com" in url:
            domain_score += 50
        if "imdb.com" in url:
            domain_score += 40
        if "wikipedia.org" in url:
            domain_score += 30
        if "baike.baidu.com" in url:
            domain_score += 20
    if "person" in topics:
        if "baike.baidu.com" in url or "wikipedia.org" in url:
            domain_score += 35
        if "douban.com" in url:
            domain_score += 20
    if "tech" in topics:
        if "github.com" in url:
            domain_score += 45
        if "docs." in url or "developer." in url:
            domain_score += 35

    quality_score = 0
    if item.get("url"):
        quality_score += 10
    if len(title) >= 6:
        quality_score += 5
    if len(snippet) >= 20:
        quality_score += 5

    keyword_hits = 0
    for token in re.findall(r"[\w\u4e00-\u9fa5]+", query.lower()):
        if token and token in text:
            keyword_hits += 1

    return (domain_score, quality_score, keyword_hits)


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
    merged = sorted(merged, key=lambda item: _score_result(query, item), reverse=True)
    return merged[:max_results]


def _fetch_page_excerpt(url: str, max_text_length: int = 3000) -> str:
    try:
        import requests
        from bs4 import BeautifulSoup

        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        title = soup.title.string.strip() if soup.title and soup.title.string else url
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned = "\n".join(lines)
        if len(cleaned) > max_text_length:
            cleaned = cleaned[:max_text_length] + f"\n... (还有 {len(cleaned) - max_text_length} 字符)"
        return f"【页面标题】{title}\n【URL】{url}\n\n【页面内容】\n{cleaned}"
    except Exception as e:
        return f"爬取失败: {e}"


def _is_valid_page_excerpt(content: str) -> bool:
    if not content:
        return False
    failure_markers = (
        "爬取失败:",
        "您所访问的页面不存在",
        "read timed out",
        "404",
        "403",
        "502",
        "503",
    )
    if any(marker in content for marker in failure_markers):
        return False
    return len(content) >= 180


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
            ToolDefinition(
                name="search_and_read",
                description="先搜索，再自动挑选更可靠的结果抓取正文。适合人物、电影、事件、技术资料等需要进一步阅读的查询。",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "最多返回的候选结果数，默认5",
                            "default": 5,
                        },
                        "max_text_length": {
                            "type": "integer",
                            "description": "抓取正文的最大长度，默认3000",
                            "default": 3000,
                        },
                    },
                    "required": ["query"],
                },
                handler=self._search_and_read,
                metadata={
                    "category": "read",
                    "required_all": ["query"],
                    "store_result": ["last_search_result"],
                },
                result_parser=self._parse_search_and_read_result,
                keywords=["搜索并阅读", "自动找网页正文", "查一下并展开看看"],
                intents=["search_and_read", "search_then_browse"],
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

    def _search_and_read(self, query: str, max_results: int = 5, max_text_length: int = 3000) -> str:
        if not query.strip():
            return "请提供搜索关键词。"

        results = _merge_results(query, max_results)
        if not results:
            return f"没有找到与 '{query}' 相关的结果。"

        attempts = []
        best_content = ""
        best_url = ""

        for item in results[: min(len(results), 3)]:
            url = str(item.get("url", "")).strip()
            if not url:
                continue
            content = _fetch_page_excerpt(url, max_text_length=max_text_length)
            attempts.append({"title": item.get("title", ""), "url": url, "content": content})
            if _is_valid_page_excerpt(content):
                best_content = content
                best_url = url
                break

        lines = [f"搜索并阅读: {query}"]
        if best_url:
            lines.append(f"已选结果: {best_url}")
            lines.append("")
            lines.append(best_content)
        else:
            lines.append("没有成功抓到可靠正文，先给你候选结果：")
            lines.append("")
            for idx, item in enumerate(results, 1):
                lines.append(f"{idx}. {item['title']}")
                if item.get("snippet"):
                    lines.append(f"   {item['snippet']}")
                if item.get("url"):
                    lines.append(f"   链接: {item['url']}")
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

    def _parse_search_and_read_result(self, args: dict, result: str) -> dict | None:
        query = str(args.get("query", "")).strip()
        selected_url = ""
        match = re.search(r"已选结果:\s*(https?://\S+)", result)
        if match:
            selected_url = match.group(1).strip()
        return {
            "query": query,
            "selected_url": selected_url,
            "result": result[:1000],
        }


register(SearchSkill)
