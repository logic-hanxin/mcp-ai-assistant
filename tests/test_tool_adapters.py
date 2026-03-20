import unittest
from types import SimpleNamespace

from assistant.agent.blackboard import Blackboard
from assistant.agent.tool_adapters import ToolEvent, build_default_tool_adapters, dispatch_tool_adapters


class ToolAdapterTests(unittest.TestCase):
    def setUp(self):
        Blackboard.reset()
        self.bb = Blackboard.get_instance()
        self.core = type("CoreStub", (), {})()
        self.core.blackboard = self.bb
        self.core._bb_scoped_key = lambda key: f"session:test:{key}"
        self.core.tool_definitions = {}
        self.adapters = build_default_tool_adapters()

    def test_contact_adapter_extracts_contact_entity(self):
        event = ToolEvent(
            tool_name="find_qq_by_name",
            tool_args={"name": "小明"},
            tool_result="找到以下用户:\n  QQ 123456 -> 小明",
        )
        dispatch_tool_adapters(self.core, event, self.adapters)

        contacts = self.bb.get_entities("contact")
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0].value["qq"], "123456")
        self.assertEqual(contacts[0].value["name"], "小明")

    def test_knowledge_adapter_extracts_query_entity(self):
        event = ToolEvent(
            tool_name="search_knowledge",
            tool_args={"query": "入会流程"},
            tool_result="找到 1 条相关知识: ...",
        )
        dispatch_tool_adapters(self.core, event, self.adapters)

        entities = self.bb.get_entities("knowledge_query")
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].value["query"], "入会流程")

    def test_search_adapter_extracts_query_entity(self):
        self.core.tool_definitions["web_search"] = SimpleNamespace(
            result_parser=lambda args, result: {
                "query": "Python MCP",
                "results": [{"title": "示例标题", "snippet": "示例摘要"}],
                "result": result,
            }
        )
        event = ToolEvent(
            tool_name="web_search",
            tool_args={"query": "Python MCP"},
            tool_result="搜索结果文本",
        )
        dispatch_tool_adapters(self.core, event, self.adapters)

        entities = self.bb.get_entities("search_query")
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].value["query"], "Python MCP")
        self.assertEqual(entities[0].value["results"][0]["title"], "示例标题")

    def test_note_adapter_extracts_note_entity(self):
        self.core.tool_definitions["take_note"] = SimpleNamespace(
            result_parser=lambda args, result: {
                "note_id": 12,
                "title": "会议纪要",
                "tags": "会议",
            }
        )
        event = ToolEvent(
            tool_name="take_note",
            tool_args={"title": "会议纪要", "content": "今天讨论了排期"},
            tool_result="笔记已保存",
        )
        dispatch_tool_adapters(self.core, event, self.adapters)

        entities = self.bb.get_entities("note")
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].value["id"], 12)
        self.assertEqual(entities[0].value["title"], "会议纪要")

    def test_reminder_adapter_extracts_reminder_entity(self):
        self.core.tool_definitions["create_reminder"] = SimpleNamespace(
            result_parser=lambda args, result: {
                "id": 7,
                "message": "开会",
                "target_time": "2026-03-20 10:00",
                "notify_qq": "123456",
            }
        )
        event = ToolEvent(
            tool_name="create_reminder",
            tool_args={"message": "开会", "time_str": "30m", "notify_qq": "123456"},
            tool_result="提醒已创建",
        )
        dispatch_tool_adapters(self.core, event, self.adapters)

        entities = self.bb.get_entities("reminder")
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].value["id"], 7)
        self.assertEqual(entities[0].value["message"], "开会")

    def test_database_adapter_extracts_schema_entity(self):
        self.core.tool_definitions["get_table_schema"] = SimpleNamespace(
            result_parser=lambda args, result: {
                "table_name": "auth_user",
                "fields": [{"name": "id", "type": "bigint"}],
                "result": result,
            }
        )
        event = ToolEvent(
            tool_name="get_table_schema",
            tool_args={"table_name": "auth_user"},
            tool_result="表结构文本",
        )
        dispatch_tool_adapters(self.core, event, self.adapters)

        entities = self.bb.get_entities("database_schema")
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].value["table_name"], "auth_user")
        self.assertEqual(entities[0].value["fields"][0]["name"], "id")

    def test_database_adapter_extracts_query_entity(self):
        self.core.tool_definitions["query_database"] = SimpleNamespace(
            result_parser=lambda args, result: {
                "sql": "SELECT id, name FROM members",
                "columns": ["id", "name"],
                "rows": [{"id": "1", "name": "小明"}],
                "result": result,
            }
        )
        event = ToolEvent(
            tool_name="query_database",
            tool_args={"sql": "SELECT id, name FROM members"},
            tool_result="查询结果文本",
        )
        dispatch_tool_adapters(self.core, event, self.adapters)

        entities = self.bb.get_entities("database_query")
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].value["columns"], ["id", "name"])
        self.assertEqual(entities[0].value["rows"][0]["name"], "小明")

    def test_workflow_adapter_extracts_workflow_entity(self):
        self.core.tool_definitions["create_workflow"] = SimpleNamespace(
            result_parser=lambda args, result: {
                "id": 5,
                "name": "晨报",
                "schedule": "daily:08:00",
                "steps": [{"tool": "get_hot_news", "args": {}}],
                "step_count": 1,
                "next_run": "2026-03-21 08:00",
            }
        )
        event = ToolEvent(
            tool_name="create_workflow",
            tool_args={"name": "晨报"},
            tool_result="工作流已创建",
        )
        dispatch_tool_adapters(self.core, event, self.adapters)

        entities = self.bb.get_entities("workflow")
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].value["id"], 5)
        self.assertEqual(entities[0].value["name"], "晨报")

    def test_message_adapter_extracts_delivery_entity(self):
        self.core.tool_definitions["send_qq_message"] = SimpleNamespace(
            result_parser=lambda args, result: {
                "target_type": "private",
                "qq_number": "123456",
                "content": "你好",
                "delivered": True,
            }
        )
        event = ToolEvent(
            tool_name="send_qq_message",
            tool_args={"qq_number": "123456", "content": "你好"},
            tool_result="消息已发送",
        )
        dispatch_tool_adapters(self.core, event, self.adapters)

        entities = self.bb.get_entities("message_delivery")
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].value["qq_number"], "123456")

    def test_news_adapter_extracts_digest_entity(self):
        self.core.tool_definitions["get_hot_news"] = SimpleNamespace(
            result_parser=lambda args, result: {
                "news_items": [{"source": "百度热搜", "title": "示例新闻"}]
            }
        )
        event = ToolEvent(
            tool_name="get_hot_news",
            tool_args={},
            tool_result="热点文本",
        )
        dispatch_tool_adapters(self.core, event, self.adapters)

        entities = self.bb.get_entities("news_digest")
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].value["items"][0]["title"], "示例新闻")

    def test_monitor_adapter_extracts_site_monitor_entity(self):
        self.core.tool_definitions["add_site_monitor"] = SimpleNamespace(
            result_parser=lambda args, result: {
                "url": "https://example.com",
                "name": "官网",
                "success": True,
            }
        )
        event = ToolEvent(
            tool_name="add_site_monitor",
            tool_args={"url": "https://example.com", "name": "官网"},
            tool_result="已添加监控",
        )
        dispatch_tool_adapters(self.core, event, self.adapters)

        entities = self.bb.get_entities("site_monitor")
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].value["url"], "https://example.com")

    def test_location_adapter_extracts_phone_lookup_entity(self):
        self.core.tool_definitions["phone_area"] = SimpleNamespace(
            result_parser=lambda args, result: {
                "phone": "13800138000",
                "location": "北京",
                "isp": "移动",
            }
        )
        event = ToolEvent(
            tool_name="phone_area",
            tool_args={"phone": "13800138000"},
            tool_result="手机号信息",
        )
        dispatch_tool_adapters(self.core, event, self.adapters)

        entities = self.bb.get_entities("phone_lookup")
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].value["location"], "北京")

    def test_adapter_prefers_result_parser_when_available(self):
        parser = lambda args, result: {"contacts": [{"qq": "654321", "name": "解析器用户"}]}
        self.core.tool_definitions["find_qq_by_name"] = SimpleNamespace(result_parser=parser)

        event = ToolEvent(
            tool_name="find_qq_by_name",
            tool_args={"name": "小红"},
            tool_result="原始文本不重要",
        )
        dispatch_tool_adapters(self.core, event, self.adapters)

        contacts = self.bb.get_entities("contact")
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0].value["qq"], "654321")
        self.assertEqual(contacts[0].value["name"], "解析器用户")

    def test_adapter_prefers_structured_side_channel_over_result_parser(self):
        parser = lambda args, result: {"contacts": [{"qq": "111111", "name": "旧解析器"}]}
        self.core.tool_definitions["find_qq_by_name"] = SimpleNamespace(result_parser=parser)

        event = ToolEvent(
            tool_name="find_qq_by_name",
            tool_args={"name": "小蓝"},
            tool_result="原始文本不重要",
            structured_result={"contacts": [{"qq": "222222", "name": "结构化结果"}]},
        )
        dispatch_tool_adapters(self.core, event, self.adapters)

        contacts = self.bb.get_entities("contact")
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0].value["qq"], "222222")
        self.assertEqual(contacts[0].value["name"], "结构化结果")


if __name__ == "__main__":
    unittest.main()
