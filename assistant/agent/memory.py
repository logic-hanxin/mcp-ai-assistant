"""
Memory - 长期记忆模块

功能:
- 会话内短期记忆（对话历史）
- 跨会话长期记忆（持久化到磁盘）
- 对话摘要压缩（超长对话自动摘要，避免 token 溢出）
"""

import json
import datetime
from pathlib import Path
from typing import Optional


def _sanitize_messages(messages: list[dict]) -> list[dict]:
    """
    清理消息列表，确保 tool_calls / tool 配对完整。
    规则:
    - role=tool 的消息，前面必须有一条包含 tool_calls 的 assistant 消息
    - 如果发现孤立的 tool 消息（前面没有 tool_calls），直接丢弃
    - 如果 assistant 有 tool_calls 但后面缺少对应的 tool 响应，也丢弃该 assistant 消息
    """
    result = []
    # 收集所有有效的 tool_call_id
    valid_tc_ids = set()
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id", "")
                if tc_id:
                    valid_tc_ids.add(tc_id)

    # 第一遍: 找出实际有 tool 响应的 tool_call_id
    responded_tc_ids = set()
    for msg in messages:
        if msg.get("role") == "tool":
            tc_id = msg.get("tool_call_id", "")
            if tc_id in valid_tc_ids:
                responded_tc_ids.add(tc_id)

    # 第二遍: 构建干净的消息列表
    for msg in messages:
        role = msg.get("role", "")

        if role == "tool":
            tc_id = msg.get("tool_call_id", "")
            if tc_id in valid_tc_ids:
                result.append(msg)
            # 否则丢弃（孤立的 tool 消息）

        elif role == "assistant" and msg.get("tool_calls"):
            # 检查这条 assistant 的所有 tool_calls 是否都有对应的 tool 响应
            tc_ids = [tc.get("id", "") for tc in msg["tool_calls"]]
            if all(tc_id in responded_tc_ids for tc_id in tc_ids):
                result.append(msg)
            # 否则丢弃（tool_calls 没有对应响应的 assistant 消息）

        else:
            result.append(msg)

    return result


def _find_safe_cut(messages: list[dict], target_cut: int) -> int:
    """
    在 target_cut 附近找到一个安全切分点，
    确保不会把 assistant(tool_calls) 和其后的 tool 响应拆开。
    向前移动切分点直到安全。
    """
    if target_cut <= 0:
        return 0
    if target_cut >= len(messages):
        return len(messages)

    cut = target_cut
    while cut > 0:
        msg = messages[cut]
        role = msg.get("role", "")

        # 切分点在 tool 消息上 → 不安全，往前
        if role == "tool":
            cut -= 1
            continue

        # 切分点在 assistant(tool_calls) 上 → 不安全（后面的 tool 会被切掉），往前
        if role == "assistant" and msg.get("tool_calls"):
            cut -= 1
            continue

        # 安全位置
        break

    return cut


class Memory:
    """Agent 记忆系统"""

    def __init__(self, storage_dir: Optional[Path] = None, max_short_term: int = 30):
        self.storage_dir = storage_dir or (Path.home() / ".ai_assistant" / "memory")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.max_short_term = max_short_term

        # 短期记忆 (当前会话)
        self.short_term: list[dict] = []

        # 长期记忆文件
        self._summaries_file = self.storage_dir / "summaries.json"
        self._facts_file = self.storage_dir / "user_facts.json"
        self._history_file = self.storage_dir / "history.json"

    # ----------------------------------------------------------
    # 短期记忆
    # ----------------------------------------------------------
    def add_message(self, role: str, content: str, **extra):
        """添加一条消息到短期记忆"""
        msg = {"role": role, "content": content, **extra}
        self.short_term.append(msg)

    def add_raw_message(self, msg: dict):
        """添加原始消息 dict"""
        self.short_term.append(msg)

    def get_messages(self) -> list[dict]:
        """获取短期记忆中的所有消息（确保 tool_calls/tool 配对完整）"""
        return _sanitize_messages(self.short_term)

    def needs_compression(self) -> bool:
        """判断是否需要压缩记忆"""
        return len(self.short_term) > self.max_short_term

    def compress(self, summary: str):
        """
        压缩短期记忆：保留最近的几轮对话，
        将较早的内容替换为 LLM 生成的摘要。
        切分时确保不拆散 tool_calls/tool 配对。
        """
        keep_recent = 10  # 目标保留条数

        # 找安全切分点：从目标位置往前找，确保不拆散 tool 调用组
        cut = max(0, len(self.short_term) - keep_recent)
        cut = _find_safe_cut(self.short_term, cut)

        old_messages = self.short_term[:cut]
        recent = self.short_term[cut:]

        # 保存摘要到长期记忆
        if old_messages:
            self._save_summary(summary)

        # 用摘要替换旧消息
        self.short_term = [
            {"role": "system", "content": f"[历史对话摘要] {summary}"}
        ] + recent

    # ----------------------------------------------------------
    # 长期记忆 - 对话摘要
    # ----------------------------------------------------------
    def _save_summary(self, summary: str):
        summaries = self._load_json(self._summaries_file)
        summaries.append({
            "summary": summary,
            "timestamp": datetime.datetime.now().isoformat(),
        })
        # 只保留最近20条摘要
        summaries = summaries[-20:]
        self._save_json(self._summaries_file, summaries)

    def get_summaries(self) -> list[dict]:
        return self._load_json(self._summaries_file)

    # ----------------------------------------------------------
    # 长期记忆 - 用户偏好/事实
    # ----------------------------------------------------------
    def save_fact(self, key: str, value: str):
        """保存用户偏好或事实，如 '用户名: 小明', '偏好语言: 中文'"""
        facts = self._load_json(self._facts_file)
        facts[key] = {"value": value, "updated_at": datetime.datetime.now().isoformat()}
        self._save_json(self._facts_file, facts)

    def get_facts(self) -> dict:
        return self._load_json(self._facts_file)

    def get_facts_prompt(self) -> str:
        """将用户事实格式化为 system prompt 片段"""
        facts = self.get_facts()
        if not facts:
            return ""
        lines = [f"- {k}: {v['value']}" for k, v in facts.items()]
        return "已知的用户信息:\n" + "\n".join(lines)

    # ----------------------------------------------------------
    # 会话历史持久化
    # ----------------------------------------------------------
    def save_session(self):
        """将当前会话保存到历史"""
        if not self.short_term:
            return
        history = self._load_json(self._history_file)
        history.append({
            "messages": self.short_term,
            "timestamp": datetime.datetime.now().isoformat(),
        })
        # 保留最近50个会话
        history = history[-50:]
        self._save_json(self._history_file, history)

    def clear_short_term(self):
        self.short_term.clear()

    # ----------------------------------------------------------
    # 工具函数
    # ----------------------------------------------------------
    def _load_json(self, path: Path):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, Exception):
                return [] if path.name != "user_facts.json" else {}
        return [] if path.name != "user_facts.json" else {}

    def _save_json(self, path: Path, data):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
