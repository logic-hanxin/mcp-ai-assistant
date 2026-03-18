"""代码沙盒 Skill - C++ 代码执行 + LeetCode 刷题辅助"""

from __future__ import annotations

import re
import random
import subprocess
import tempfile
import os

import httpx
from assistant.skills.base import BaseSkill, ToolDefinition, register

LEETCODE_GRAPHQL = "https://leetcode.cn/graphql/"
LEETCODE_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",
}

# 代码执行安全限制
COMPILE_TIMEOUT = 10   # 编译超时(秒)
RUN_TIMEOUT = 5        # 运行超时(秒)
MAX_OUTPUT = 2000      # 最大输出字符数


def _run_cpp_code(code: str, stdin_input: str = "") -> str:
    """编译并运行 C++ 代码，返回执行结果"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, "solution.cpp")
        bin_path = os.path.join(tmpdir, "solution")

        with open(src_path, "w") as f:
            f.write(code)

        # 编译
        try:
            compile_result = subprocess.run(
                ["g++", "-std=c++17", "-O2", "-o", bin_path, src_path],
                capture_output=True, text=True, timeout=COMPILE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return "编译超时（超过 10 秒）"
        except FileNotFoundError:
            return "服务器未安装 g++ 编译器，请联系管理员安装。"

        if compile_result.returncode != 0:
            errors = compile_result.stderr[:MAX_OUTPUT]
            return f"编译错误:\n{errors}"

        # 运行
        try:
            run_result = subprocess.run(
                [bin_path],
                input=stdin_input, capture_output=True, text=True,
                timeout=RUN_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return f"运行超时（超过 {RUN_TIMEOUT} 秒），可能存在死循环。"

        output = run_result.stdout[:MAX_OUTPUT]
        stderr = run_result.stderr[:MAX_OUTPUT]

        lines = []
        if run_result.returncode != 0:
            lines.append(f"程序异常退出 (返回码: {run_result.returncode})")
        if output:
            lines.append(f"标准输出:\n{output}")
        if stderr:
            lines.append(f"错误输出:\n{stderr}")
        if not output and not stderr and run_result.returncode == 0:
            lines.append("程序正常运行，无输出。")

        return "\n".join(lines)


def _fetch_leetcode_today() -> dict | None:
    """获取 LeetCode 每日一题"""
    query = """
    query questionOfToday {
      todayRecord {
        question {
          questionFrontendId
          titleSlug
          translatedTitle
          difficulty
          translatedContent
        }
      }
    }
    """
    try:
        resp = httpx.post(LEETCODE_GRAPHQL, json={"query": query},
                          timeout=10, headers=LEETCODE_HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            records = data.get("data", {}).get("todayRecord", [])
            if records:
                return records[0].get("question")
    except Exception:
        pass
    return None


def _fetch_leetcode_random(difficulty: str = "") -> dict | None:
    """随机获取一道 LeetCode 题目"""
    query = """
    query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
      problemsetQuestionList(categorySlug: $categorySlug, limit: $limit, skip: $skip, filters: $filters) {
        total
        questions {
          frontendQuestionId
          titleSlug
          translatedTitle
          difficulty
          translatedContent
        }
      }
    }
    """
    diff_map = {"easy": "EASY", "medium": "MEDIUM", "hard": "HARD",
                "简单": "EASY", "中等": "MEDIUM", "困难": "HARD"}
    filters = {}
    if difficulty and difficulty.lower() in diff_map:
        filters["difficulty"] = diff_map[difficulty.lower()]

    try:
        # 先获取 total
        variables = {"categorySlug": "algorithms", "limit": 1, "skip": 0, "filters": filters}
        resp = httpx.post(LEETCODE_GRAPHQL, json={"query": query, "variables": variables},
                          timeout=10, headers=LEETCODE_HEADERS)
        total = resp.json()["data"]["problemsetQuestionList"]["total"]

        # 随机取一道
        skip = random.randint(0, min(total - 1, 2000))
        variables["skip"] = skip
        resp = httpx.post(LEETCODE_GRAPHQL, json={"query": query, "variables": variables},
                          timeout=10, headers=LEETCODE_HEADERS)
        questions = resp.json()["data"]["problemsetQuestionList"]["questions"]
        if questions:
            return questions[0]
    except Exception:
        pass
    return None


def _clean_html(html: str) -> str:
    """将 HTML 内容转为纯文本"""
    text = re.sub(r"<pre>\s*", "\n```\n", html)
    text = re.sub(r"\s*</pre>", "\n```\n", text)
    text = re.sub(r"<code>", "`", text)
    text = re.sub(r"</code>", "`", text)
    text = re.sub(r"<strong[^>]*>", "**", text)
    text = re.sub(r"</strong>", "**", text)
    text = re.sub(r"<li>", "- ", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<p>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _format_question(q: dict) -> str:
    """格式化 LeetCode 题目"""
    qid = q.get("questionFrontendId", "?")
    title = q.get("translatedTitle", q.get("titleSlug", ""))
    diff = q.get("difficulty", "")
    diff_cn = {"EASY": "简单", "MEDIUM": "中等", "HARD": "困难", "Easy": "简单", "Medium": "中等", "Hard": "困难"}.get(diff, diff)
    slug = q.get("titleSlug", "")
    url = f"https://leetcode.cn/problems/{slug}/" if slug else ""
    content = _clean_html(q.get("translatedContent", "") or "")

    lines = [
        f"📝 LeetCode {qid}. {title} [{diff_cn}]",
        f"🔗 {url}",
        "",
    ]
    if content:
        # 限制内容长度
        if len(content) > 1500:
            content = content[:1500] + "\n\n... (内容过长已截断，请访问链接查看完整题目)"
        lines.append(content)

    lines.append("")
    lines.append("请用 C++ 写出你的解法，发给我后我会帮你编译运行并给出改进建议！")
    return "\n".join(lines)


class CodeSkill(BaseSkill):
    name = "code"
    description = "C++ 代码沙盒执行 + LeetCode 刷题辅助"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="run_cpp_code",
                description=(
                    "编译并运行 C++ 代码，返回编译结果和程序输出。"
                    "用于执行用户发送的 C++ 代码片段，查看运行结果。"
                    "代码需要是完整可编译的（包含 main 函数）。"
                    "运行后请根据代码质量给出改进建议，包括时间复杂度、代码风格等。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "完整的 C++ 代码",
                        },
                        "stdin_input": {
                            "type": "string",
                            "description": "程序的标准输入（可选），用于提供测试数据",
                        },
                    },
                    "required": ["code"],
                },
                handler=self._run_cpp_code,
            ),
            ToolDefinition(
                name="get_leetcode_problem",
                description=(
                    "获取 LeetCode 算法题目。可以获取每日一题，也可以按难度随机抽一道题。"
                    "获取到题目后展示给用户，引导用户用 C++ 作答。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "description": "题目类型：today=每日一题, random=随机题目",
                            "enum": ["today", "random"],
                        },
                        "difficulty": {
                            "type": "string",
                            "description": "难度筛选（仅 random 模式有效）：简单/中等/困难 或 easy/medium/hard",
                        },
                    },
                    "required": [],
                },
                handler=self._get_leetcode_problem,
            ),
        ]

    def _run_cpp_code(self, code: str, stdin_input: str = "") -> str:
        if not code.strip():
            return "请提供 C++ 代码。"
        return _run_cpp_code(code, stdin_input)

    def _get_leetcode_problem(self, type: str = "today", difficulty: str = "") -> str:
        if type == "random":
            q = _fetch_leetcode_random(difficulty)
        else:
            q = _fetch_leetcode_today()

        if not q:
            return "获取 LeetCode 题目失败，请稍后重试。"
        return _format_question(q)


register(CodeSkill)
