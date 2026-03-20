import datetime
import unittest
from types import SimpleNamespace

from assistant.agent.blackboard import Blackboard
from assistant.agent import workflow_runner
from assistant.agent.workflow_runner import calc_next_run, execute_workflow_steps, parse_workflow_steps


class WorkflowRunnerTests(unittest.TestCase):
    def setUp(self):
        Blackboard.reset()
        workflow_runner._tool_handlers = None
        workflow_runner._tool_definitions = None
        workflow_runner._tool_metadata = None

    def test_weekly_schedule_supports_same_day_future_time(self):
        now = datetime.datetime(2026, 3, 20, 8, 0)  # Friday
        next_run = calc_next_run("weekly:5:09:30", after=now)
        self.assertEqual(next_run, datetime.datetime(2026, 3, 20, 9, 30))

    def test_weekly_schedule_rolls_to_next_matching_day_when_today_passed(self):
        now = datetime.datetime(2026, 3, 20, 10, 0)  # Friday
        next_run = calc_next_run("weekly:5,7:09:30", after=now)
        self.assertEqual(next_run, datetime.datetime(2026, 3, 22, 9, 30))

    def test_invalid_schedule_returns_none(self):
        self.assertIsNone(calc_next_run("weekly:0:09:30"))
        self.assertIsNone(calc_next_run("daily:25:00"))
        self.assertIsNone(calc_next_run("interval:0h"))

    def test_parse_workflow_steps_accepts_json_string(self):
        steps, error = parse_workflow_steps('[{"tool":"get_weather","args":{"city":"北京"}}]')
        self.assertIsNone(error)
        self.assertEqual(
            steps,
            [{"tool": "get_weather", "args": {"city": "北京"}}],
        )

    def test_parse_workflow_steps_rejects_invalid_args(self):
        steps, error = parse_workflow_steps([{"tool": "get_weather", "args": []}])
        self.assertIsNone(steps)
        self.assertIn("args", error)

    def test_execute_workflow_steps_reuses_runtime_blackboard_between_steps(self):
        sent = {}

        def find_qq_by_name(name: str):
            return "找到联系人"

        def send_qq_message(qq_number: str = "", content: str = ""):
            sent["qq_number"] = qq_number
            sent["content"] = content
            return f"发送给 {qq_number}: {content}"

        workflow_runner._tool_handlers = {
            "find_qq_by_name": find_qq_by_name,
            "send_qq_message": send_qq_message,
        }
        workflow_runner._tool_definitions = {
            "find_qq_by_name": SimpleNamespace(
                result_parser=lambda args, result: {"contacts": [{"qq": "123456", "name": "小明"}]}
            ),
            "send_qq_message": SimpleNamespace(result_parser=None),
        }
        workflow_runner._tool_metadata = {
            "find_qq_by_name": {"category": "read"},
            "send_qq_message": {
                "category": "notify",
                "side_effect": "external_message",
                "required_all": ["content"],
                "required_any": [["qq_number"]],
            },
        }

        results = execute_workflow_steps(
            [
                {"tool": "find_qq_by_name", "args": {"name": "小明"}},
                {"tool": "send_qq_message", "args": {"content": "开会啦"}},
            ],
            workflow_id=42,
            workflow_name="通知流程",
        )

        self.assertEqual(results[1]["args"]["qq_number"], "123456")
        self.assertEqual(sent["qq_number"], "123456")
        self.assertEqual(sent["content"], "开会啦")

    def test_execute_workflow_steps_applies_runtime_policy(self):
        called = {"value": False}

        def send_qq_message(qq_number: str = "", content: str = ""):
            called["value"] = True
            return f"发送给 {qq_number}: {content}"

        workflow_runner._tool_handlers = {
            "send_qq_message": send_qq_message,
        }
        workflow_runner._tool_definitions = {
            "send_qq_message": SimpleNamespace(result_parser=None),
        }
        workflow_runner._tool_metadata = {
            "send_qq_message": {
                "category": "notify",
                "side_effect": "external_message",
                "required_all": ["content"],
                "required_any": [["qq_number"]],
            },
        }

        results = execute_workflow_steps(
            [{"tool": "send_qq_message", "args": {"content": "你好"}}],
            workflow_id=99,
            workflow_name="测试策略",
            session_context={},
        )

        self.assertIn("策略阻止执行", results[0]["result"])
        self.assertFalse(called["value"])


if __name__ == "__main__":
    unittest.main()
