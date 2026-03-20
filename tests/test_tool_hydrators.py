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
                session_image="",
                session_file="",
                bb_user="123456",
                bb_group="",
                bb_repo="",
                bb_branch="",
                bb_city="",
                bb_image="",
                bb_file="",
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
                session_image="",
                session_file="",
                bb_user="",
                bb_group="",
                bb_repo="owner/repo",
                bb_branch="dev",
                bb_city="",
                bb_image="",
                bb_file="",
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
                session_image="",
                session_file="",
                bb_user="",
                bb_group="",
                bb_repo="",
                bb_branch="",
                bb_city="",
                bb_image="",
                bb_file="",
                shareable_text="最近结果",
            ),
            self.hydrators,
        )
        self.assertEqual(args["content"], "最近结果")
        self.assertEqual(args["group_id"], "80001")
        self.assertEqual(args["at_qq"], "90001")

    def test_vision_hydrator_uses_session_image_first(self):
        args = hydrate_tool_args(
            ToolHydrationContext(
                tool_name="ocr_image",
                tool_args={},
                session_user="",
                session_group="",
                session_image="https://img.example.com/current.jpg",
                session_file="",
                bb_user="",
                bb_group="",
                bb_repo="",
                bb_branch="",
                bb_city="",
                bb_image="https://img.example.com/old.jpg",
                bb_file="",
                shareable_text="",
            ),
            self.hydrators,
        )
        self.assertEqual(args["image_url"], "https://img.example.com/current.jpg")

    def test_vision_hydrator_falls_back_to_blackboard_image(self):
        args = hydrate_tool_args(
            ToolHydrationContext(
                tool_name="understand_image",
                tool_args={},
                session_user="",
                session_group="",
                session_image="",
                session_file="",
                bb_user="",
                bb_group="",
                bb_repo="",
                bb_branch="",
                bb_city="",
                bb_image="https://img.example.com/last.jpg",
                bb_file="",
                shareable_text="",
            ),
            self.hydrators,
        )
        self.assertEqual(args["image_url"], "https://img.example.com/last.jpg")

    def test_document_hydrator_uses_session_file_first(self):
        args = hydrate_tool_args(
            ToolHydrationContext(
                tool_name="parse_document",
                tool_args={},
                session_user="",
                session_group="",
                session_image="",
                session_file="https://files.example.com/a.pdf",
                bb_user="",
                bb_group="",
                bb_repo="",
                bb_branch="",
                bb_city="",
                bb_image="",
                bb_file="https://files.example.com/old.pdf",
                shareable_text="",
            ),
            self.hydrators,
        )
        self.assertEqual(args["file_path"], "https://files.example.com/a.pdf")

    def test_document_hydrator_falls_back_to_blackboard_file(self):
        args = hydrate_tool_args(
            ToolHydrationContext(
                tool_name="import_document",
                tool_args={},
                session_user="",
                session_group="",
                session_image="",
                session_file="",
                bb_user="",
                bb_group="",
                bb_repo="",
                bb_branch="",
                bb_city="",
                bb_image="",
                bb_file="https://files.example.com/last.docx",
                shareable_text="",
            ),
            self.hydrators,
        )
        self.assertEqual(args["file_path"], "https://files.example.com/last.docx")

    def test_document_hydrator_replaces_suspicious_napcat_temp_path(self):
        args = hydrate_tool_args(
            ToolHydrationContext(
                tool_name="parse_document",
                tool_args={"file_path": "/app/.config/QQ/NapCat/temp/test.pdf"},
                session_user="",
                session_group="",
                session_image="",
                session_file="https://files.example.com/current.pdf",
                bb_user="",
                bb_group="",
                bb_repo="",
                bb_branch="",
                bb_city="",
                bb_image="",
                bb_file="",
                shareable_text="",
            ),
            self.hydrators,
        )
        self.assertEqual(args["file_path"], "https://files.example.com/current.pdf")


if __name__ == "__main__":
    unittest.main()
