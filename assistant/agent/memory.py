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


class Memory:
    """Agent 记忆系统"""

    def __init__(self, storage_dir: Path | None = None, max_short_term: int = 30):
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
        """获取短期记忆中的所有消息"""
        return list(self.short_term)

    def needs_compression(self) -> bool:
        """判断是否需要压缩记忆"""
        return len(self.short_term) > self.max_short_term

    def compress(self, summary: str):
        """
        压缩短期记忆：保留最近的几轮对话，
        将较早的内容替换为 LLM 生成的摘要。
        """
        keep_recent = 10  # 保留最近10条
        old_messages = self.short_term[:-keep_recent] if len(self.short_term) > keep_recent else []
        recent = self.short_term[-keep_recent:] if len(self.short_term) > keep_recent else self.short_term

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
