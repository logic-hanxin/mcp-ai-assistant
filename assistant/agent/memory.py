"""
Memory - 分层记忆模块

记忆分层:
- 短期记忆: 当前会话消息 (内存 + DB 双写)
- 压缩摘要: 超长对话自动摘要，持久化到 DB
- 用户事实: 偏好/个人信息，按 user_id 隔离持久化
- 经验教训: 跨用户共享的知识 (通过 db.py 直接操作)

每个 Memory 实例绑定一个 session_id (通常为QQ号)，
服务重启后可从数据库恢复上下文。
"""

from __future__ import annotations

import json
import traceback
from typing import Optional


def _sanitize_messages(messages: list[dict]) -> list[dict]:
    """
    清理消息列表，确保 tool_calls / tool 配对完整且相邻。

    OpenAI API 要求:
    - assistant(tool_calls) 之后必须紧跟对应的 tool 消息
    - 中间不能插入其他消息

    处理策略:
    1. 先找出所有完整配对的 tool_call 组（assistant + 所有 tool 响应）
    2. 把 tool 响应从原位置提取出来，紧跟在对应的 assistant 后面输出
    3. 不完整的配对整组丢弃
    """
    # 第一步: 索引所有 tool_call_id → 对应的 assistant 消息索引
    tc_id_to_assistant_idx = {}
    assistant_tc_ids = {}  # assistant_idx → [tc_id, ...]
    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            ids = []
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id", "")
                if tc_id:
                    tc_id_to_assistant_idx[tc_id] = i
                    ids.append(tc_id)
            assistant_tc_ids[i] = ids

    # 第二步: 收集所有 tool 响应，按 assistant 索引分组
    tool_responses = {}  # assistant_idx → [tool_msg, ...]
    tool_msg_indices = set()  # 记录哪些消息是 tool 响应（后面跳过）
    for i, msg in enumerate(messages):
        if msg.get("role") == "tool":
            tc_id = msg.get("tool_call_id", "")
            ast_idx = tc_id_to_assistant_idx.get(tc_id)
            if ast_idx is not None:
                tool_responses.setdefault(ast_idx, []).append(msg)
                tool_msg_indices.add(i)

    # 第三步: 判断哪些 assistant(tool_calls) 是完整配对的
    complete_assistants = set()
    for ast_idx, tc_ids in assistant_tc_ids.items():
        responses = tool_responses.get(ast_idx, [])
        responded_ids = {m.get("tool_call_id", "") for m in responses}
        if all(tc_id in responded_ids for tc_id in tc_ids):
            complete_assistants.add(ast_idx)

    # 第四步: 构建结果，确保 tool 响应紧跟 assistant
    result = []
    for i, msg in enumerate(messages):
        role = msg.get("role", "")

        # 跳过已被归组的 tool 消息（后面会跟在 assistant 后面输出）
        if i in tool_msg_indices:
            continue

        if role == "assistant" and msg.get("tool_calls"):
            if i in complete_assistants:
                # 完整配对: 输出 assistant + 紧跟所有 tool 响应
                result.append(msg)
                for tool_msg in tool_responses[i]:
                    result.append(tool_msg)
            # 不完整的直接丢弃
        elif role == "tool":
            # 孤立的 tool 消息（对应的 assistant 不在当前消息列表中），丢弃
            continue
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
    """分层记忆系统 (MySQL 持久化)"""

    def __init__(self, session_id: str = "default", user_id: Optional[str] = None,
                 max_short_term: int = 30):
        self.session_id = session_id
        self.user_id = user_id or session_id
        self.max_short_term = max_short_term

        # 短期记忆 (当前会话，内存中)
        self.short_term: list[dict] = []

        # 标记 DB 是否可用
        self._db_available = False
        self._init_db()

    def _init_db(self):
        """尝试初始化 DB 连接并恢复上下文"""
        try:
            from assistant.agent.db_memory import load_recent_messages, load_summaries
            self._db_available = True

            # 恢复上一次会话的消息
            restored = load_recent_messages(self.session_id, limit=self.max_short_term)
            if restored:
                self.short_term = restored
                print(f"[Memory] 从 DB 恢复了 {len(restored)} 条消息 (session={self.session_id})")

                # 加载最近的摘要作为上下文前缀
                summaries = load_summaries(self.session_id, limit=2)
                if summaries:
                    summary_text = " | ".join(s["summary"] for s in summaries)
                    # 在消息列表前面插入摘要上下文
                    self.short_term.insert(0, {
                        "role": "system",
                        "content": f"[历史对话摘要] {summary_text}"
                    })
                    print(f"[Memory] 加载了 {len(summaries)} 条历史摘要")
        except Exception as e:
            print(f"[Memory] DB 不可用，使用纯内存模式: {e}")
            traceback.print_exc()
            self._db_available = False

    # ----------------------------------------------------------
    # 短期记忆
    # ----------------------------------------------------------
    def add_message(self, role: str, content: str, **extra):
        """添加一条消息到短期记忆 + DB 持久化"""
        msg = {"role": role, "content": content, **extra}
        self.short_term.append(msg)
        self._persist_message(msg)

    def add_raw_message(self, msg: dict):
        """添加原始消息 dict"""
        self.short_term.append(msg)
        self._persist_message(msg)

    def _persist_message(self, msg: dict):
        """将消息写入 DB"""
        if not self._db_available:
            return
        try:
            from assistant.agent.db_memory import save_message
            save_message(
                session_id=self.session_id,
                role=msg.get("role", ""),
                content=msg.get("content"),
                tool_calls=msg.get("tool_calls"),
                tool_call_id=msg.get("tool_call_id"),
            )
        except Exception as e:
            print(f"[Memory] DB 写入失败: {e}")

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

        # 保存摘要到 DB
        if old_messages:
            self._save_summary(summary, len(old_messages))

        # 用摘要替换旧消息
        self.short_term = [
            {"role": "system", "content": f"[历史对话摘要] {summary}"}
        ] + recent

        # 清理 DB 中的旧消息，只保留最近的
        if self._db_available:
            try:
                from assistant.agent.db_memory import delete_old_messages
                deleted = delete_old_messages(self.session_id, keep_recent=keep_recent)
                if deleted:
                    print(f"[Memory] 清理了 DB 中 {deleted} 条旧消息")
            except Exception as e:
                print(f"[Memory] DB 清理失败: {e}")

    # ----------------------------------------------------------
    # 对话摘要
    # ----------------------------------------------------------
    def _save_summary(self, summary: str, message_count: int = 0):
        if not self._db_available:
            return
        try:
            from assistant.agent.db_memory import save_summary
            save_summary(self.session_id, summary, message_count)
        except Exception as e:
            print(f"[Memory] 摘要保存失败: {e}")

    def get_summaries(self) -> list[dict]:
        if not self._db_available:
            return []
        try:
            from assistant.agent.db_memory import load_summaries
            return load_summaries(self.session_id)
        except Exception:
            return []

    # ----------------------------------------------------------
    # 用户偏好/事实
    # ----------------------------------------------------------
    def save_fact(self, key: str, value: str):
        """保存用户偏好或事实，如 '用户名: 小明', '偏好语言: 中文'"""
        if not self._db_available:
            return
        try:
            from assistant.agent.db_memory import save_fact
            save_fact(self.user_id, key, value)
        except Exception as e:
            print(f"[Memory] 事实保存失败: {e}")

    def get_facts(self) -> dict:
        if not self._db_available:
            return {}
        try:
            from assistant.agent.db_memory import load_facts
            return load_facts(self.user_id)
        except Exception:
            return {}

    def get_facts_prompt(self) -> str:
        """将用户事实格式化为 system prompt 片段"""
        facts = self.get_facts()
        if not facts:
            return ""
        lines = [f"- {k}: {v}" for k, v in facts.items()]
        return "已知的用户信息:\n" + "\n".join(lines)

    # ----------------------------------------------------------
    # 会话管理
    # ----------------------------------------------------------
    def save_session(self):
        """会话保存（DB 模式下消息已实时持久化，此方法保持兼容）"""
        pass

    def clear_short_term(self):
        self.short_term.clear()
        if self._db_available:
            try:
                from assistant.agent.db_memory import clear_session_messages
                clear_session_messages(self.session_id)
            except Exception as e:
                print(f"[Memory] 清空会话失败: {e}")
