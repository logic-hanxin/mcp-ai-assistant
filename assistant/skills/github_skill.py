"""GitHub 仓库监控 Skill - 管理监控列表、查询分支状态"""

import os
import httpx
from assistant.skills.base import BaseSkill, ToolDefinition, register
from assistant.agent import db_misc as db

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")


def _headers() -> dict:
    h = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h


class GitHubSkill(BaseSkill):
    name = "github"
    description = "GitHub 仓库监控，查询分支/提交状态，有新提交时 QQ 通知"

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
                metadata={
                    "category": "write",
                    "side_effect": "scheduled_notification",
                    "blackboard_reads": ["github_repo", "target_user"],
                    "blackboard_writes": ["last_github_repo", "last_github_branch"],
                    "required_all": ["repo"],
                    "required_any": [["notify_qq"]],
                    "store_args": {
                        "repo": "last_github_repo",
                        "branch": "last_github_branch",
                        "notify_qq": "last_target_qq",
                    },
                },
                result_parser=self._parse_repo_branch_result,
                keywords=["GitHub监控", "仓库订阅", "新提交提醒", "repo watch"],
                intents=["watch_repository", "subscribe_repo"],
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
                keywords=["取消监控", "停止订阅仓库", "移除GitHub监控"],
                intents=["unwatch_repository"],
            ),
            ToolDefinition(
                name="github_list_watched",
                description="列出当前所有监控中的 GitHub 仓库。",
                parameters={"type": "object", "properties": {}},
                handler=self._list_watched,
                keywords=["监控列表", "查看订阅仓库", "GitHub监控列表"],
                intents=["list_watched_repositories"],
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
                metadata={
                    "category": "read",
                    "blackboard_reads": ["github_repo", "github_branch"],
                    "blackboard_writes": ["last_github_repo", "last_github_branch"],
                    "required_all": ["repo"],
                    "store_args": {"repo": "last_github_repo", "branch": "last_github_branch"},
                },
                result_parser=self._parse_repo_branch_result,
                keywords=["最近提交", "commit记录", "仓库提交历史", "分支提交"],
                intents=["get_recent_commits", "inspect_repository"],
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
                metadata={
                    "category": "read",
                    "blackboard_reads": ["github_repo"],
                    "blackboard_writes": ["last_github_repo"],
                    "required_all": ["repo"],
                    "store_args": {"repo": "last_github_repo"},
                },
                result_parser=self._parse_repo_branch_result,
                keywords=["分支列表", "查看仓库分支", "branch信息"],
                intents=["list_branches", "inspect_repository"],
            ),
            ToolDefinition(
                name="github_get_repo_overview",
                description="查看仓库概要信息，包括描述、星标、Fork、默认分支、Open Issue 等。",
                parameters={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "仓库全名，如 'owner/repo'"},
                    },
                    "required": ["repo"],
                },
                handler=self._get_repo_overview,
                metadata={
                    "category": "read",
                    "blackboard_reads": ["github_repo"],
                    "blackboard_writes": ["last_github_repo"],
                    "required_all": ["repo"],
                    "store_args": {"repo": "last_github_repo"},
                },
                result_parser=self._parse_repo_branch_result,
                keywords=["仓库概览", "repo信息", "仓库摘要"],
                intents=["get_repo_overview"],
            ),
            ToolDefinition(
                name="github_list_pull_requests",
                description="列出指定仓库的 Pull Request。",
                parameters={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "仓库全名，如 'owner/repo'"},
                        "state": {"type": "string", "description": "PR 状态: open/closed/all", "default": "open"},
                        "limit": {"type": "integer", "description": "返回条数，默认5", "default": 5},
                    },
                    "required": ["repo"],
                },
                handler=self._list_pull_requests,
                metadata={
                    "category": "read",
                    "blackboard_reads": ["github_repo"],
                    "blackboard_writes": ["last_github_repo"],
                    "required_all": ["repo"],
                    "store_args": {"repo": "last_github_repo"},
                },
                result_parser=self._parse_repo_branch_result,
                keywords=["查看PR", "Pull Request列表", "合并请求"],
                intents=["list_pull_requests"],
            ),
            ToolDefinition(
                name="github_list_issues",
                description="列出指定仓库的 Issue。",
                parameters={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "仓库全名，如 'owner/repo'"},
                        "state": {"type": "string", "description": "Issue 状态: open/closed/all", "default": "open"},
                        "limit": {"type": "integer", "description": "返回条数，默认5", "default": 5},
                    },
                    "required": ["repo"],
                },
                handler=self._list_issues,
                metadata={
                    "category": "read",
                    "blackboard_reads": ["github_repo"],
                    "blackboard_writes": ["last_github_repo"],
                    "required_all": ["repo"],
                    "store_args": {"repo": "last_github_repo"},
                },
                result_parser=self._parse_repo_branch_result,
                keywords=["查看Issue", "问题列表", "仓库问题"],
                intents=["list_issues"],
            ),
        ]

    def _watch_repo(self, repo: str, notify_qq: str, branch: str = "main") -> str:
        try:
            db.github_watch_add(repo, branch=branch, notify_qq=notify_qq)
            return f"已添加监控: {repo}:{branch}，有新提交会通知 QQ:{notify_qq}"
        except Exception as e:
            return f"添加监控失败: {e}"

    def _unwatch_repo(self, repo: str) -> str:
        try:
            if db.github_watch_remove(repo):
                return f"已移除 {repo} 的监控。"
            return f"未找到 {repo} 的监控记录。"
        except Exception as e:
            return f"移除失败: {e}"

    def _list_watched(self) -> str:
        try:
            repos = db.github_watch_list()
        except Exception as e:
            return f"查询失败: {e}"

        if not repos:
            return "暂无监控中的仓库。"
        lines = []
        for r in repos:
            sha = (r.get("last_commit_sha") or "")[:7] or "未检查"
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

    def _get_repo_overview(self, repo: str) -> str:
        try:
            resp = httpx.get(
                f"https://api.github.com/repos/{repo}",
                headers=_headers(),
                timeout=15,
            )
            if resp.status_code == 404:
                return f"仓库 {repo} 不存在或无权访问。"
            if resp.status_code != 200:
                return f"查询失败: HTTP {resp.status_code}"
            data = resp.json()
            lines = [
                f"{repo} 仓库概览",
                f"描述: {data.get('description') or '无'}",
                f"默认分支: {data.get('default_branch', 'main')}",
                f"⭐ Stars: {data.get('stargazers_count', 0)} | Forks: {data.get('forks_count', 0)}",
                f"Open Issues: {data.get('open_issues_count', 0)}",
                f"主页: {data.get('html_url', '')}",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"查询失败: {e}"

    def _list_pull_requests(self, repo: str, state: str = "open", limit: int = 5) -> str:
        try:
            resp = httpx.get(
                f"https://api.github.com/repos/{repo}/pulls",
                params={"state": state, "per_page": limit},
                headers=_headers(),
                timeout=15,
            )
            if resp.status_code != 200:
                return f"查询失败: HTTP {resp.status_code}"
            pulls = resp.json()
            if not pulls:
                return f"{repo} 当前没有 {state} 状态的 PR。"
            lines = [f"{repo} 的 PR 列表 ({state}):"]
            for pr in pulls[:limit]:
                lines.append(f"  #{pr['number']} {pr['title']} [{pr['user']['login']}]")
            return "\n".join(lines)
        except Exception as e:
            return f"查询失败: {e}"

    def _list_issues(self, repo: str, state: str = "open", limit: int = 5) -> str:
        try:
            resp = httpx.get(
                f"https://api.github.com/repos/{repo}/issues",
                params={"state": state, "per_page": limit},
                headers=_headers(),
                timeout=15,
            )
            if resp.status_code != 200:
                return f"查询失败: HTTP {resp.status_code}"
            issues = [item for item in resp.json() if "pull_request" not in item]
            if not issues:
                return f"{repo} 当前没有 {state} 状态的 Issue。"
            lines = [f"{repo} 的 Issue 列表 ({state}):"]
            for issue in issues[:limit]:
                lines.append(f"  #{issue['number']} {issue['title']} [{issue['user']['login']}]")
            return "\n".join(lines)
        except Exception as e:
            return f"查询失败: {e}"

    def _parse_repo_branch_result(self, args: dict, result: str) -> dict | None:
        repo = str(args.get("repo", "")).strip()
        branch = str(args.get("branch", "")).strip()
        if repo:
            return {"repo": repo, "branch": branch or "main"}
        return None


register(GitHubSkill)
