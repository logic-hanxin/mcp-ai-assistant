import unittest
from types import SimpleNamespace
from unittest.mock import patch

from assistant.agent.blackboard import Blackboard


class BlackboardIntegrationTests(unittest.TestCase):
    def setUp(self):
        Blackboard.reset()
        fake_openai = SimpleNamespace(OpenAI=object)
        fake_mcp_client = SimpleNamespace(MCPClient=object)
        with patch.dict(
            "sys.modules",
            {
                "openai": fake_openai,
                "assistant.mcp.client": fake_mcp_client,
            },
        ):
            from assistant.agent.core import AgentCore
        self.core = AgentCore.__new__(AgentCore)
        self.core.blackboard = Blackboard.get_instance()
        self.core.memory = type("MemoryStub", (), {"session_id": "test_session"})()
        self.core.session_context = {}
        self.core.tool_metadata = {
            "send_qq_message": {
                "category": "notify",
                "side_effect": "external_message",
                "required_all": ["content"],
                "required_any": [["qq_number"]],
            },
            "add_rule": {
                "category": "admin",
                "side_effect": "admin_operation",
                "required_all": ["title", "content"],
                "session_required": True,
            },
        }

    def test_update_blackboard_records_scoped_variables_and_entities(self):
        self.core.tool_metadata["set_user_name"] = {
            "store_args": {"qq_number": "last_target_qq"},
        }
        self.core.tool_metadata["get_weather"] = {
            "store_args": {"city": "last_city"},
            "store_result": ["last_weather"],
        }
        self.core._update_blackboard(
            "set_user_name",
            {"qq_number": "123456", "name": "小明"},
            "已保存: QQ 123456 -> 小明",
        )
        self.core._update_blackboard(
            "get_weather",
            {"city": "上海"},
            "上海: 多云 25度",
        )

        context = self.core._build_blackboard_context()
        self.assertIn("last_city", context)
        self.assertIn("上海", context)
        self.assertIn("小明=123456", context)

    def test_clear_scope_removes_only_current_session_data(self):
        bb = self.core.blackboard
        bb.set("session:test_session:last_weather", "晴")
        bb.set("session:other:last_weather", "雨")
        bb.write_entity("contact", "session:test_session:contact:1", {"qq": "1", "name": "甲"}, "x")
        bb.write_entity("contact", "session:other:contact:2", {"qq": "2", "name": "乙"}, "x")
        bb.write_result("session:test_session:react_get_weather", "session:test_session:general", "get_weather", "晴")
        bb.write_result("session:other:react_get_weather", "session:other:general", "get_weather", "雨")

        bb.clear_scope("session:test_session")

        self.assertIsNone(bb.get("session:test_session:last_weather"))
        self.assertEqual(bb.get("session:other:last_weather"), "雨")
        remaining_contacts = [e.key for e in bb.get_entities("contact")]
        self.assertEqual(remaining_contacts, ["session:other:contact:2"])
        remaining_results = [r.step_id for r in bb.get_results()]
        self.assertEqual(remaining_results, ["session:other:react_get_weather"])

    def test_hydrate_tool_args_uses_session_and_blackboard_defaults(self):
        self.core.session_context = {"user_qq": "90001", "group_id": "80001"}
        bb = self.core.blackboard
        bb.set("session:test_session:last_github_repo", "owner/repo")
        bb.set("session:test_session:last_github_branch", "dev")
        bb.set("session:test_session:last_search_result", "这是最近一次搜索结果")
        bb.write_entity(
            "contact",
            "session:test_session:contact:123456",
            {"qq": "123456", "name": "小明"},
            "find_qq_by_name",
        )

        reminder_args = self.core._hydrate_tool_args("create_reminder", {"message": "开会", "time_str": "30m"})
        github_args = self.core._hydrate_tool_args("github_get_latest_commits", {})
        send_args = self.core._hydrate_tool_args("send_qq_message", {"content": "你好"})
        broadcast_args = self.core._hydrate_tool_args("broadcast_last_result", {})
        rule_args = self.core._hydrate_tool_args("add_rule", {"title": "新规则", "content": "别刷屏"})

        self.assertEqual(reminder_args["notify_qq"], "90001")
        self.assertEqual(reminder_args["notify_group_id"], "80001")
        self.assertEqual(github_args["repo"], "owner/repo")
        self.assertEqual(github_args["branch"], "dev")
        self.assertEqual(send_args["qq_number"], "123456")
        self.assertEqual(broadcast_args["group_id"], "80001")
        self.assertEqual(broadcast_args["at_qq"], "90001")
        self.assertEqual(broadcast_args["content"], "这是最近一次搜索结果")
        self.assertEqual(rule_args["user_qq"], "90001")

    def test_tool_policy_blocks_notify_without_target(self):
        error = self.core._apply_tool_policy("send_qq_message", {"content": "你好"})
        self.assertIn("qq_number", error)

    def test_tool_policy_blocks_admin_without_user_context(self):
        error = self.core._apply_tool_policy("add_rule", {"title": "规则", "content": "内容"})
        self.assertIn("缺少管理员身份上下文", error)

    def test_tool_policy_allows_admin_with_user_context(self):
        self.core.session_context = {"user_qq": "90001"}
        error = self.core._apply_tool_policy("add_rule", {"title": "规则", "content": "内容"})
        self.assertIsNone(error)


if __name__ == "__main__":
    unittest.main()
