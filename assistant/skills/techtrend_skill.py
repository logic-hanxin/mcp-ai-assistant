"""技术前沿资讯 Skill - GitHub 热门项目 + Hacker News + 测试开发相关资讯"""

from __future__ import annotations

import httpx
from assistant.skills.base import BaseSkill, ToolDefinition, register

GITHUB_SEARCH_API = "https://api.github.com/search/repositories"
HN_API = "https://hacker-news.firebaseio.com/v0"

# 测试开发相关的 GitHub 关键词
QA_TOPICS = [
    "testing framework", "test automation", "selenium", "playwright",
    "cypress", "pytest", "CI/CD", "devops", "quality assurance",
    "performance testing", "api testing", "load testing",
]


def _fetch_github_trending(language: str = "", topic: str = "") -> list[dict]:
    """获取 GitHub 热门项目"""
    try:
        query_parts = ["stars:>500"]
        if language:
            query_parts.append(f"language:{language}")
        if topic:
            query_parts.append(topic)

        resp = httpx.get(
            GITHUB_SEARCH_API,
            params={
                "q": " ".join(query_parts),
                "sort": "stars",
                "order": "desc",
                "per_page": 10,
            },
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github.v3+json"},
        )
        if resp.status_code == 200:
            return resp.json().get("items", [])
    except Exception:
        pass
    return []


def _fetch_github_recent(language: str = "", topic: str = "") -> list[dict]:
    """获取 GitHub 近期活跃的优质项目"""
    try:
        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        query_parts = [f"pushed:>{since}", "stars:>100"]
        if language:
            query_parts.append(f"language:{language}")
        if topic:
            query_parts.append(topic)

        resp = httpx.get(
            GITHUB_SEARCH_API,
            params={
                "q": " ".join(query_parts),
                "sort": "updated",
                "order": "desc",
                "per_page": 10,
            },
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github.v3+json"},
        )
        if resp.status_code == 200:
            return resp.json().get("items", [])
    except Exception:
        pass
    return []


def _fetch_hacker_news(count: int = 10) -> list[dict]:
    """获取 Hacker News 热门文章"""
    try:
        resp = httpx.get(f"{HN_API}/topstories.json", timeout=10)
        if resp.status_code != 200:
            return []

        story_ids = resp.json()[:count]
        stories = []
        for sid in story_ids:
            try:
                item_resp = httpx.get(f"{HN_API}/item/{sid}.json", timeout=5)
                if item_resp.status_code == 200:
                    stories.append(item_resp.json())
            except Exception:
                continue
        return stories
    except Exception:
        return []


def _format_github_repos(repos: list[dict], title: str) -> str:
    """格式化 GitHub 仓库列表"""
    if not repos:
        return f"{title}\n\n暂无数据。"

    lines = [title, ""]
    for i, r in enumerate(repos, 1):
        name = r.get("full_name", "?")
        stars = r.get("stargazers_count", 0)
        desc = r.get("description", "") or ""
        if len(desc) > 80:
            desc = desc[:80] + "..."
        lang = r.get("language", "") or ""
        url = r.get("html_url", "")

        lines.append(f"{i}. ⭐{stars} | {name}")
        if lang:
            lines.append(f"   语言: {lang}")
        if desc:
            lines.append(f"   {desc}")
        lines.append(f"   {url}")
        lines.append("")

    return "\n".join(lines)


class TechTrendSkill(BaseSkill):
    name = "techtrend"
    description = "技术前沿资讯 - GitHub 热门项目、Hacker News、测试开发动态"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="github_trending",
                description=(
                    "获取 GitHub 热门或近期活跃的优质开源项目。"
                    "可按编程语言和主题筛选。适合发现新工具、新框架。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "language": {
                            "type": "string",
                            "description": "编程语言筛选，如 python, java, go, c++, rust, javascript 等（可选）",
                        },
                        "topic": {
                            "type": "string",
                            "description": "主题关键词，如 testing, automation, devops, AI, web 等（可选）",
                        },
                        "type": {
                            "type": "string",
                            "description": "hot=按星标数排序的热门项目, recent=近期活跃项目",
                            "enum": ["hot", "recent"],
                        },
                    },
                    "required": [],
                },
                handler=self._github_trending,
            ),
            ToolDefinition(
                name="hacker_news_top",
                description=(
                    "获取 Hacker News 当前热门文章。"
                    "Hacker News 是全球顶级技术社区，涵盖编程、AI、创业、工程等话题。"
                    "适合了解技术圈最新热点。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "获取文章数量，默认 10，最多 20",
                        },
                    },
                    "required": [],
                },
                handler=self._hacker_news_top,
            ),
            ToolDefinition(
                name="qa_tech_recommend",
                description=(
                    "获取测试开发工程师相关的优质项目和工具推荐。"
                    "涵盖自动化测试、性能测试、CI/CD、API 测试等领域。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "area": {
                            "type": "string",
                            "description": "细分领域：automation=自动化测试, performance=性能测试, api=API测试, cicd=CI/CD, all=全部",
                            "enum": ["automation", "performance", "api", "cicd", "all"],
                        },
                    },
                    "required": [],
                },
                handler=self._qa_tech_recommend,
            ),
        ]

    def _github_trending(self, language: str = "", topic: str = "", type: str = "hot") -> str:
        if type == "recent":
            repos = _fetch_github_recent(language, topic)
            title_text = "📈 GitHub 近期活跃项目"
        else:
            repos = _fetch_github_trending(language, topic)
            title_text = "🔥 GitHub 热门项目"

        filters = []
        if language:
            filters.append(f"语言: {language}")
        if topic:
            filters.append(f"主题: {topic}")
        if filters:
            title_text += f" ({', '.join(filters)})"

        return _format_github_repos(repos, title_text)

    def _hacker_news_top(self, count: int = 10) -> str:
        count = min(max(count, 1), 20)
        stories = _fetch_hacker_news(count)

        if not stories:
            return "获取 Hacker News 热门文章失败，请稍后重试。"

        lines = [f"🔶 Hacker News 热门 Top {len(stories)}", ""]
        for i, s in enumerate(stories, 1):
            title = s.get("title", "?")
            url = s.get("url", "")
            score = s.get("score", 0)
            comments = s.get("descendants", 0)
            hn_url = f"https://news.ycombinator.com/item?id={s.get('id', '')}"

            lines.append(f"{i}. {title}")
            lines.append(f"   👍{score} | 💬{comments}")
            if url:
                lines.append(f"   {url}")
            else:
                lines.append(f"   {hn_url}")
            lines.append("")

        return "\n".join(lines)

    def _qa_tech_recommend(self, area: str = "all") -> str:
        area_keywords = {
            "automation": "test automation",
            "performance": "performance testing",
            "api": "api testing",
            "cicd": "CI CD pipeline",
            "all": "testing",
        }
        keyword = area_keywords.get(area, area_keywords["all"])

        repos = _fetch_github_trending(topic=keyword)

        # 如果没结果，放宽搜索
        if not repos:
            fallback = {
                "automation": "selenium OR playwright OR cypress",
                "performance": "benchmark OR load-testing OR k6",
                "api": "postman OR httprunner OR REST",
                "cicd": "github-actions OR jenkins OR gitlab-ci",
                "all": "testing OR QA OR automation",
            }
            repos = _fetch_github_trending(topic=fallback.get(area, fallback["all"]))
        area_names = {
            "automation": "自动化测试", "performance": "性能测试",
            "api": "API 测试", "cicd": "CI/CD", "all": "测试开发综合",
        }
        area_name = area_names.get(area, "测试开发")

        return _format_github_repos(repos, f"🧪 {area_name} - 优质项目推荐")


register(TechTrendSkill)
