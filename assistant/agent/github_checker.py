"""
GitHub 后台提交检查器

每 60 秒轮询监控列表中的仓库，检测新提交并通过 QQ 通知。
"""

import os
import asyncio

import httpx

from assistant.agent import db

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
NAPCAT_API_URL = os.getenv("NAPCAT_API_URL", "http://127.0.0.1:3000")
CHECK_INTERVAL = int(os.getenv("GITHUB_CHECK_INTERVAL", "60"))  # 秒


def _headers() -> dict:
    h = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h


async def github_check_loop():
    """后台循环，定期检查 GitHub 仓库新提交"""
    # 首次启动延迟 10 秒，等服务就绪
    await asyncio.sleep(10)

    while True:
        try:
            await _check_all_repos()
        except Exception:
            pass
        await asyncio.sleep(CHECK_INTERVAL)


async def _check_all_repos():
    """检查所有监控仓库"""
    try:
        repos = db.github_watch_list()
    except Exception:
        return
    if not repos:
        return

    async with httpx.AsyncClient(timeout=15) as client:
        for repo_config in repos:
            repo = repo_config["repo"]
            branch = repo_config.get("branch", "main")
            last_sha = repo_config.get("last_commit_sha", "")
            notify_qq = repo_config.get("notify_qq", "")

            try:
                resp = await client.get(
                    f"https://api.github.com/repos/{repo}/commits",
                    params={"sha": branch, "per_page": 5},
                    headers=_headers(),
                )
                if resp.status_code != 200:
                    continue

                commits = resp.json()
                if not commits:
                    continue

                latest_sha = commits[0]["sha"]

                # 首次检查，仅记录当前 SHA，不发通知
                if not last_sha:
                    try:
                        db.github_watch_update_sha(repo, branch, latest_sha)
                    except Exception:
                        pass
                    continue

                # 有新提交
                if latest_sha != last_sha:
                    # 找出所有新提交
                    new_commits = []
                    for c in commits:
                        if c["sha"] == last_sha:
                            break
                        new_commits.append(c)

                    try:
                        db.github_watch_update_sha(repo, branch, latest_sha)
                    except Exception:
                        pass

                    # 发送 QQ 通知
                    if notify_qq and new_commits:
                        await _notify_new_commits(notify_qq, repo, branch, new_commits)

            except Exception:
                continue


async def _notify_new_commits(notify_qq: str, repo: str, branch: str, commits: list[dict]):
    """通过 QQ 通知新提交"""
    lines = [f"[GitHub] {repo}:{branch} 有 {len(commits)} 个新提交"]
    for c in commits[:5]:  # 最多显示 5 条
        sha = c["sha"][:7]
        msg = c["commit"]["message"].split("\n")[0][:50]
        author = c["commit"]["author"]["name"]
        lines.append(f"  {sha} [{author}] {msg}")

    if len(commits) > 5:
        lines.append(f"  ... 还有 {len(commits) - 5} 条")

    text = "\n".join(lines)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{NAPCAT_API_URL}/send_private_msg", json={
                "user_id": int(notify_qq),
                "message": [{"type": "text", "data": {"text": text}}],
            })
        print(f"  [GitHub通知] {repo} -> QQ:{notify_qq}")
    except Exception as e:
        print(f"  [GitHub通知失败] {e}")
