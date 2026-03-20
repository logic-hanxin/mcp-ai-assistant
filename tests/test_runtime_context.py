import unittest
from types import SimpleNamespace
from unittest.mock import patch

from assistant.runtime_context import (
    get_current_user_qq,
    reset_current_user_qq,
    set_current_user_qq,
)
from assistant.skills.rule_skill import RuleSkill


class RuntimeContextTests(unittest.TestCase):
    def test_current_user_context_round_trip(self):
        token = set_current_user_qq("10001")
        try:
            self.assertEqual(get_current_user_qq(), "10001")
        finally:
            reset_current_user_qq(token)
        self.assertEqual(get_current_user_qq(), "")

    def test_rule_skill_uses_runtime_context_for_admin_check(self):
        skill = RuleSkill()
        token = set_current_user_qq("admin_qq")
        try:
            with patch("assistant.skills.rule_skill.RULE_ADMIN_QQ", "admin_qq"):
                fake_db = SimpleNamespace(save_rule=lambda title, content: 7)
                with patch.dict("sys.modules", {"assistant.agent.db_misc": fake_db}):
                    result = skill._add_rule("标题", "内容")
        finally:
            reset_current_user_qq(token)

        self.assertIn("守则已添加", result)
        self.assertIn("ID: 7", result)


if __name__ == "__main__":
    unittest.main()
