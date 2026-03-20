import json
import unittest

from assistant.agent.planner import Planner


class _FakeCompletions:
    def __init__(self):
        self.last_messages = None

    def create(self, **kwargs):
        self.last_messages = kwargs["messages"]
        content = json.dumps({"needs_plan": False})
        message = type("Msg", (), {"content": content})()
        choice = type("Choice", (), {"message": message})()
        return type("Resp", (), {"choices": [choice]})()


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeLLM:
    def __init__(self):
        self.chat = _FakeChat()


class PlannerMetadataTests(unittest.TestCase):
    def test_create_plan_includes_tool_metadata_in_prompt(self):
        llm = _FakeLLM()
        planner = Planner(llm, "fake-model")
        available_tools = [
            {
                "function": {
                    "name": "send_qq_message",
                    "description": "发送私聊消息",
                }
            }
        ]
        tool_metadata = {
            "send_qq_message": {
                "category": "notify",
                "side_effect": "external_message",
                "blackboard_reads": ["target_user"],
                "blackboard_writes": ["last_target_qq"],
                "keywords": ["通知", "私聊"],
                "intents": ["notify_person", "send_private_message"],
            }
        }

        planner.create_plan("告诉小明开会", available_tools, tool_metadata=tool_metadata)

        prompt = llm.chat.completions.last_messages[1]["content"]
        self.assertIn("category=notify", prompt)
        self.assertIn("side_effect=external_message", prompt)
        self.assertIn("bb_reads=target_user", prompt)
        self.assertIn("bb_writes=last_target_qq", prompt)
        self.assertIn("keywords=通知,私聊", prompt)
        self.assertIn("intents=notify_person,send_private_message", prompt)


if __name__ == "__main__":
    unittest.main()
