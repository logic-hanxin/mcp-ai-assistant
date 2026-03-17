"""GitHub 仓库监控 Skill - 管理监控列表、查询分支状态"""

import os
import json
from pathlib import Path
import httpx
from assistant.skills.base import BaseSkill, ToolDefinition, register

GITHUB_DIR = Path.home() / ".ai_assistant" / "github"
WATCH_FILE = GITHUB_DIR / "watch_repos.json"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")


def _headers() -> dict:
    h = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h


def _load_watch() -> list[dict]:
    if WATCH_FILE.exists():
        try:
            return json.loads(WATCH_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_watch(data: list[dict]):
    GITHUB_DIR.mkdir(parents=True, exist_ok=True)
    WATCH_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class GitHubSkill(BaseSkill):
    name = "github"
    description = "GitHub 仓库监控，查询分支/提交状态，有新提交时 QQ 通知"

    def on_load(self):
        GITHUB_DIR.mkdir(parents=True, exist_ok=True)

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="github_watch_repo",
                description=(
                    "添加一个 GitHub 仓库到监控列表。有新提交时会自动通过 QQ 通知。"
                    "需要指定仓库全名（owner/repo）、要监控的分支、和接收通知的 QQ 号。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "仓库全名，如 'logic-hanxin/mcp-ai-assistant'"},
                        "branch": {"type": "string", "description": "要监控的分支名，如 'main'", "default": "main"},
                        "notify_qq": {"type": "string", "description": "接收通知的QQ号"},
                    },
                    "required": ["repo", "notify_qq"],
                },
                handler=self._watch_repo,
            ),
            ToolDefinition(
                name="github_unwatch_repo",
                description="从监控列表中移除一个仓库。",
                parameters={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "仓库全名，如 'owner/repo'"},
                    },
                    "required": ["repo"],
                },
                handler=self._unwatch_repo,
            ),
            ToolDefinition(
                name="github_list_watched",
                description="列出当前所有监控中的 GitHub 仓库。",
                parameters={"type": "object", "properties": {}},
                handler=self._list_watched,
            ),
            ToolDefinition(
                name="github_get_latest_commits",
                description="查询指定仓库指定分支的最近几条提交记录。",
                parameters={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "仓库全名，如 'owner/repo'"},
                        "branch": {"type": "string", "description": "分支名", "default": "main"},
                        "count": {"type": "integer", "description": "返回条数", "default": 5},
                    },
                    "required": ["repo"],
                },
                handler=self._get_commits,
            ),
            ToolDefinition(
                name="github_get_branches",
                description="查询指定仓库的所有分支及最新提交信息。",
                parameters={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "仓库全名，如 'owner/repo'"},
                    },
                    "required": ["repo"],
                },
                handler=self._get_branches,
            ),
        ]

    def _watch_repo(self, repo: str, notify_qq: str, branch: str = "main") -> str:
        repos = _load_watch()
        # 检查是否已存在
        for r in repos:
            if r["repo"] == repo and r["branch"] == branch:
                r["notify_qq"] = notify_qq
                _save_watch(repos)
                return f"已更新监控: {repo}:{branch} -> 通知 QQ:{notify_qq}"

        repos.append({
            "repo": repo,
            "branch": branch,
            "notify_qq": notify_qq,
            "last_commit_sha": "",  # 后台检查器会填入
        })
        _save_watch(repos)
        return f"已添加监控: {repo}:{branch}，有新提交会通知 QQ:{notify_qq}"

    def _unwatch_repo(self, repo: str) -> str:
        repos = _load_watch()
        original = len(repos)
        repos = [r for r in repos if r["repo"] != repo]
        if len(repos) == original:
            return f"未找到 {repo} 的监控记录。"
        _save_watch(repos)
        return f"已移除 {repo} 的监控。"

    def _list_watched(self) -> str:
        repos = _load_watch()
        if not repos:
            return "暂无监控中的仓库。"
        lines = []
        for r in repos:
            sha = r.get("last_commit_sha", "")[:7] or "未检查"
            lines.append(f"  {r['repo']}:{r['branch']}  通知QQ:{r['notify_qq']}  最新:{sha}")
        return "监控列表:\n" + "\n".join(lines)

    def _get_commits(self, repo: str, branch: str = "main", count: int = 5) -> str:
        try:
            resp = httpx.get(
                f"https://api.github.com/repos/{repo}/commits",
                params={"sha": branch, "per_page": count},
                headers=_headers(),
                timeout=15,
            )
            if resp.status_code == 404:
                return f"仓库 {repo} 不存在或无权访问。"
            if resp.status_code != 200:
                return f"GitHub API 错误: {resp.status_code}"

            commits = resp.json()
            lines = [f"{repo}:{branch} 最近 {len(commits)} 条提交:"]
            for c in commits:
                sha = c["sha"][:7]
                msg = c["commit"]["message"].split("\n")[0][:60]
                author = c["commit"]["author"]["name"]
                date = c["commit"]["author"]["date"][:10]
                lines.append(f"  {sha} {date} [{author}] {msg}")
            return "\n".join(lines)
        except Exception as e:
            return f"查询失败: {e}"

    def _get_branches(self, repo: str) -> str:
        try:
            resp = httpx.get(
                f"https://api.github.com/repos/{repo}/branches",
                headers=_headers(),
                timeout=15,
            )
            if resp.status_code != 200:
                return f"查询失败: HTTP {resp.status_code}"

            branches = resp.json()
            lines = [f"{repo} 共 {len(branches)} 个分支:"]
            for b in branches:
                name = b["name"]
                sha = b["commit"]["sha"][:7]
                lines.append(f"  {name} (最新: {sha})")
            return "\n".join(lines)
        except Exception as e:
            return f"查询失败: {e}"


register(GitHubSkill)
