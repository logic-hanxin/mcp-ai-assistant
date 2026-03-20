import unittest

from assistant.agent.router import BASE_EXPERT_PROFILES, Router, build_expert_profiles, score_expert_intents


class RouterMetadataTests(unittest.TestCase):
    def test_build_expert_profiles_preserves_base_tools(self):
        profiles = build_expert_profiles({})
        self.assertEqual(profiles["task"]["tool_names"], BASE_EXPERT_PROFILES["task"]["tool_names"])

    def test_build_expert_profiles_assigns_query_tools_by_skill_and_category(self):
        profiles = build_expert_profiles(
            {
                "custom_search": {"skill": "search", "category": "read"},
                "custom_db_query": {"skill": "unknown", "category": "query"},
            }
        )
        self.assertIn("custom_search", profiles["query"]["tool_names"])
        self.assertIn("custom_db_query", profiles["query"]["tool_names"])

    def test_build_expert_profiles_assigns_task_tools_by_side_effect(self):
        profiles = build_expert_profiles(
            {
                "custom_notifier": {"skill": "unknown", "side_effect": "external_message"},
                "custom_scheduler": {"skill": "unknown", "side_effect": "scheduled_notification"},
            }
        )
        self.assertIn("custom_notifier", profiles["task"]["tool_names"])
        self.assertIn("custom_scheduler", profiles["task"]["tool_names"])

    def test_build_expert_profiles_enriches_description_with_metadata_summary(self):
        profiles = build_expert_profiles(
            {
                "custom_search": {"skill": "search", "category": "read", "keywords": ["搜索", "资料"], "intents": ["web_search"]},
                "custom_browser": {"skill": "browser", "category": "read"},
            }
        )
        description = profiles["query"]["description"]
        self.assertIn("扩展能力", description)
        self.assertIn("search", description)
        self.assertIn("browser", description)
        self.assertIn("搜索", description)
        self.assertIn("web_search", description)

    def test_score_expert_intents_scores_matching_keywords(self):
        scores = score_expert_intents(
            "帮我搜索一下 Python MCP 资料",
            {
                "web_search": {
                    "skill": "search",
                    "category": "read",
                    "keywords": ["搜索", "资料"],
                    "intents": ["web_search"],
                },
                "take_note": {
                    "skill": "note",
                    "category": "write",
                    "keywords": ["记笔记"],
                    "intents": ["take_note"],
                },
            },
        )
        self.assertGreater(scores["query"], scores["task"])
        self.assertGreater(scores["query"], 0)

    def test_router_short_circuits_on_strong_intent_match(self):
        class _LLMShouldNotBeCalled:
            class _Chat:
                class _Completions:
                    def create(self, **kwargs):
                        raise AssertionError("LLM should not be called for strong intent match")

                completions = _Completions()

            chat = _Chat()

        router = Router(
            _LLMShouldNotBeCalled(),
            "fake-model",
            tool_metadata={
                "create_reminder": {
                    "skill": "reminder",
                    "category": "write",
                    "keywords": ["提醒", "定时通知", "稍后提醒"],
                    "intents": ["create_reminder"],
                }
            },
        )
        result = router.classify("请帮我创建提醒，30分钟后提醒我开会")
        self.assertEqual(result, "task")


if __name__ == "__main__":
    unittest.main()
