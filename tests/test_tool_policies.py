import unittest

from assistant.agent.tool_policies import apply_tool_policies, build_default_tool_policies


class ToolPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policies = build_default_tool_policies()

    def test_required_fields_policy_blocks_missing_required_field(self):
        result = apply_tool_policies(
            tool_name="create_reminder",
            tool_args={"message": "开会"},
            tool_metadata={"required_all": ["message", "time_str"]},
            session_context={},
            policies=self.policies,
        )
        self.assertIn("time_str", result)

    def test_required_any_policy_blocks_missing_target_group(self):
        result = apply_tool_policies(
            tool_name="send_qq_message",
            tool_args={"content": "你好"},
            tool_metadata={
                "side_effect": "external_message",
                "required_all": ["content"],
                "required_any": [["qq_number"]],
            },
            session_context={},
            policies=self.policies,
        )
        self.assertIn("qq_number", result)

    def test_session_context_policy_allows_when_user_exists(self):
        result = apply_tool_policies(
            tool_name="add_rule",
            tool_args={"title": "规则", "content": "内容"},
            tool_metadata={"session_required": True},
            session_context={"user_qq": "10001"},
            policies=self.policies,
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
