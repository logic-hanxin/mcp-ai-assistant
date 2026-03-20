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

    def test_update_workflow_updates_schedule_and_name(self):
        fake_db = SimpleNamespace(
            workflow_get=lambda workflow_id: None,
            workflow_update=lambda workflow_id, **kwargs: None,
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
            "enabled": 1,
            "next_run": None,
        }

        with patch.object(fake_db, "workflow_get", return_value=source):
            with patch.object(fake_db, "workflow_update", return_value=True) as mock_update:
                result = skill._update_workflow(3, name="新名字", schedule="daily:09:00")

        self.assertIn("已更新", result)
        self.assertTrue(mock_update.called)


class SearchSkillEnhancementTests(unittest.TestCase):
    def test_merge_results_deduplicates_and_keeps_links(self):
        from assistant.skills import search_skill

        with patch.object(
            search_skill,
            "_search_duckduckgo",
            return_value=[
                {"title": "结果A", "snippet": "摘要A", "url": "https://a.example.com", "source": "duckduckgo"},
                {"title": "结果B", "snippet": "摘要B", "url": "https://b.example.com", "source": "duckduckgo"},
            ],
        ), patch.object(
            search_skill,
            "_search_bing",
            return_value=[
                {"title": "结果A", "snippet": "重复", "url": "https://a.example.com", "source": "bing"},
                {"title": "结果C", "snippet": "摘要C", "url": "https://c.example.com", "source": "bing"},
            ],
        ), patch.object(
            search_skill,
            "_search_sogou",
            return_value=[],
        ):
            results = search_skill._merge_results("测试", max_results=3)

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["url"], "https://a.example.com")
        self.assertEqual(results[2]["title"], "结果C")

    def test_merge_results_prioritizes_movie_domains(self):
        from assistant.skills import search_skill

        with patch.object(
            search_skill,
            "_search_duckduckgo",
            return_value=[
                {"title": "百科结果", "snippet": "摘要", "url": "https://baike.baidu.com/item/x", "source": "duckduckgo"},
            ],
        ), patch.object(
            search_skill,
            "_search_bing",
            return_value=[
                {"title": "豆瓣结果", "snippet": "剧情介绍", "url": "https://movie.douban.com/subject/1/", "source": "bing"},
            ],
        ), patch.object(
            search_skill,
            "_search_sogou",
            return_value=[],
        ):
            results = search_skill._merge_results("汤唯 色戒 电影 相关信息", max_results=2)

        self.assertEqual(results[0]["url"], "https://movie.douban.com/subject/1/")

    def test_search_and_read_uses_first_valid_page(self):
        from assistant.skills.search_skill import SearchSkill
        from assistant.skills import search_skill

        skill = SearchSkill()
        with patch.object(
            search_skill,
            "_merge_results",
            return_value=[
                {"title": "坏页面", "snippet": "", "url": "https://bad.example.com", "source": "bing"},
                {"title": "好页面", "snippet": "", "url": "https://good.example.com", "source": "duckduckgo"},
            ],
        ), patch.object(
            search_skill,
            "_fetch_page_excerpt",
            side_effect=[
                "爬取失败: 404",
                "【页面标题】好页面\n【URL】https://good.example.com\n\n【页面内容】\n这是一个足够长的正文内容，用来验证 search_and_read 会自动回退到第二个候选页面。" * 3,
            ],
        ):
            result = skill._search_and_read("测试查询")

        self.assertIn("已选结果: https://good.example.com", result)


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
