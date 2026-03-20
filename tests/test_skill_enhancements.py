import unittest
from types import SimpleNamespace
from unittest.mock import patch
import sys


class WorkflowSkillEnhancementTests(unittest.TestCase):
    def test_clone_workflow_uses_source_workflow_defaults(self):
        fake_db = SimpleNamespace(
            workflow_get=lambda workflow_id: None,
            workflow_create=lambda **kwargs: None,
        )
        with patch.dict(sys.modules, {"assistant.agent.db_workflow": fake_db}):
            from assistant.skills.workflow_skill import WorkflowSkill

            skill = WorkflowSkill()
        source = {
            "id": 3,
            "name": "原始工作流",
            "steps": '[{"tool":"get_weather","args":{"city":"北京"}}]',
            "schedule": "daily:08:00",
            "description": "desc",
            "notify_qq": "123456",
            "notify_group_id": "",
        }

        with patch.object(fake_db, "workflow_get", return_value=source):
            with patch.object(fake_db, "workflow_create", return_value=9) as mock_create:
                result = skill._clone_workflow(3)

        self.assertIn("新ID: 9", result)
        self.assertTrue(mock_create.called)


class NoteSkillEnhancementTests(unittest.TestCase):
    def test_append_note_appends_existing_note(self):
        from assistant.skills.note_skill import NoteSkill

        skill = NoteSkill()
        fake_db_misc = SimpleNamespace(
            note_get=lambda note_id: {"id": 7, "title": "周报"},
            note_append=lambda note_id, extra: True,
        )
        with patch.dict(sys.modules, {"assistant.agent.db_misc": fake_db_misc}):
            with patch.object(fake_db_misc, "note_get", return_value={"id": 7, "title": "周报"}):
                with patch.object(fake_db_misc, "note_append", return_value=True):
                    result = skill._append_note(7, "补充内容")

        self.assertIn("已向笔记 7 追加内容", result)


if __name__ == "__main__":
    unittest.main()
