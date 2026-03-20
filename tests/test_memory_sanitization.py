import unittest

from assistant.agent.memory import _find_safe_cut, _sanitize_messages


class MemorySanitizationTests(unittest.TestCase):
    def test_sanitize_messages_keeps_complete_tool_call_groups(self):
        messages = [
            {"role": "user", "content": "查天气"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "get_weather", "arguments": "{}"}}
                ],
            },
            {"role": "user", "content": "插入的无关消息"},
            {"role": "tool", "tool_call_id": "call_1", "content": "晴天"},
        ]

        sanitized = _sanitize_messages(messages)

        self.assertEqual(sanitized[0]["role"], "user")
        self.assertEqual(sanitized[1]["role"], "assistant")
        self.assertEqual(sanitized[2]["role"], "tool")
        self.assertEqual(sanitized[2]["tool_call_id"], "call_1")

    def test_find_safe_cut_moves_before_tool_message(self):
        messages = [
            {"role": "user", "content": "1"},
            {"role": "assistant", "content": "2"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "x", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "done"},
            {"role": "assistant", "content": "4"},
        ]

        safe_cut = _find_safe_cut(messages, 3)
        self.assertEqual(safe_cut, 1)


if __name__ == "__main__":
    unittest.main()
