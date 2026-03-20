import unittest
from types import SimpleNamespace
from unittest.mock import patch
import sys


class GroupOpsSkillTests(unittest.TestCase):
    def setUp(self):
        fake_httpx = SimpleNamespace(post=lambda *args, **kwargs: None)
        with patch.dict("sys.modules", {"httpx": fake_httpx}):
            from assistant.skills.group_ops_skill import GroupOpsSkill
        self.skill = GroupOpsSkill()

    def test_notify_contact_by_name_sends_private_message(self):
        fake_response = type("Resp", (), {"json": lambda self: {"status": "ok"}})()
        with patch("assistant.skills.group_ops_skill.load_users", return_value={
            "123456": {"name": "小明", "nickname": "", "msg_count": 1},
        }):
            with patch("assistant.skills.group_ops_skill.httpx.post", return_value=fake_response) as mock_post:
                result = self.skill._notify_contact_by_name("小明", "你好")

        self.assertIn("消息已发送给 小明", result)
        self.assertTrue(mock_post.called)

    def test_notify_group_by_name_supports_at_contact(self):
        fake_response = type("Resp", (), {"json": lambda self: {"retcode": 0}})()
        with patch("assistant.skills.group_ops_skill.load_groups", return_value={
            "80001": {"name": "测试群", "group_name": "", "msg_count": 1},
        }):
            with patch("assistant.skills.group_ops_skill.load_users", return_value={
                "123456": {"name": "小明", "nickname": "", "msg_count": 1},
            }):
                with patch("assistant.skills.group_ops_skill.httpx.post", return_value=fake_response):
                    result = self.skill._notify_group_by_name("测试群", "同步一下", at_name="小明")

        self.assertIn("消息已发送到群 测试群", result)
        self.assertIn("123456", result)

    def test_notify_recent_contact_uses_latest_contact(self):
        fake_response = type("Resp", (), {"json": lambda self: {"status": "ok"}})()
        with patch("assistant.skills.group_ops_skill.load_users", return_value={
            "111111": {"name": "老联系人", "nickname": "", "msg_count": 2, "last_seen": "2026-03-19T10:00:00"},
            "222222": {"name": "新联系人", "nickname": "", "msg_count": 1, "last_seen": "2026-03-20T09:00:00"},
        }):
            with patch("assistant.skills.group_ops_skill.httpx.post", return_value=fake_response):
                result = self.skill._notify_recent_contact("记得看消息")

        self.assertIn("新联系人", result)

    def test_broadcast_workflow_result_uses_last_result(self):
        fake_response = type("Resp", (), {"json": lambda self: {"status": "ok"}})()
        fake_db_workflow = SimpleNamespace(
            workflow_get=lambda workflow_id: {
                "id": 8,
                "name": "晨报",
                "last_result": "今天天气晴朗",
            }
        )
        with patch("assistant.skills.group_ops_skill.httpx.post", return_value=fake_response):
            with patch.dict(sys.modules, {"assistant.agent.db_workflow": fake_db_workflow}):
                result = self.skill._broadcast_workflow_result(8, group_id="90001")

        self.assertIn("消息已发送到群 90001", result)


if __name__ == "__main__":
    unittest.main()
