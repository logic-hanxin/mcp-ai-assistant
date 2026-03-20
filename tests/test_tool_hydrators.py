import unittest

from assistant.agent.tool_hydrators import (
    ToolHydrationContext,
    build_default_tool_hydrators,
    hydrate_tool_args,
)


class ToolHydratorTests(unittest.TestCase):
    def setUp(self):
        self.hydrators = build_default_tool_hydrators()

    def test_message_hydrator_uses_blackboard_user(self):
        args = hydrate_tool_args(
            ToolHydrationContext(
                tool_name="send_qq_message",
                tool_args={"content": "你好"},
                session_user="",
                session_group="",
                bb_user="123456",
                bb_group="",
                bb_repo="",
                bb_branch="",
                bb_city="",
                shareable_text="",
            ),
            self.hydrators,
        )
        self.assertEqual(args["qq_number"], "123456")

    def test_github_hydrator_uses_recent_repo_and_branch(self):
        args = hydrate_tool_args(
            ToolHydrationContext(
                tool_name="github_get_latest_commits",
                tool_args={},
                session_user="",
                session_group="",
                bb_user="",
                bb_group="",
                bb_repo="owner/repo",
                bb_branch="dev",
                bb_city="",
                shareable_text="",
            ),
            self.hydrators,
        )
        self.assertEqual(args["repo"], "owner/repo")
        self.assertEqual(args["branch"], "dev")

    def test_group_ops_hydrator_uses_shareable_text_and_group(self):
        args = hydrate_tool_args(
            ToolHydrationContext(
                tool_name="broadcast_last_result",
                tool_args={},
                session_user="90001",
                session_group="80001",
                bb_user="",
                bb_group="",
                bb_repo="",
                bb_branch="",
                bb_city="",
                shareable_text="最近结果",
            ),
            self.hydrators,
        )
        self.assertEqual(args["content"], "最近结果")
        self.assertEqual(args["group_id"], "80001")
        self.assertEqual(args["at_qq"], "90001")


if __name__ == "__main__":
    unittest.main()
