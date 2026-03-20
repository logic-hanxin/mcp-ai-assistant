import unittest

from assistant.llm.deepseek import LLMEndpointConfig
from assistant.llm.model_pool import OpenAIModelPool


class _FakeClientFactory:
    def __init__(self, plans):
        self._plans = list(plans)

    def __call__(self, api_key: str, base_url: str):
        plan = self._plans.pop(0)

        class _Completions:
            def create(self, **kwargs):
                if isinstance(plan, Exception):
                    raise plan
                return {
                    "client_api_key": api_key,
                    "client_base_url": base_url,
                    "request_model": kwargs.get("model"),
                }

        class _Chat:
            completions = _Completions()

        class _Client:
            chat = _Chat()

        return _Client()


class ModelPoolTests(unittest.TestCase):
    def test_model_pool_falls_back_to_next_endpoint(self):
        pool = OpenAIModelPool(
            [
                LLMEndpointConfig(name="primary", api_key="k1", base_url="https://a", model="m1"),
                LLMEndpointConfig(name="backup", api_key="k2", base_url="https://b", model="m2"),
            ],
            client_factory=_FakeClientFactory([RuntimeError("boom"), object()]),
        )

        result = pool.chat.completions.create(messages=[{"role": "user", "content": "hi"}])
        self.assertEqual(result["client_api_key"], "k2")
        self.assertEqual(result["client_base_url"], "https://b")
        self.assertEqual(result["request_model"], "m2")

    def test_model_pool_reports_exhausted_endpoints(self):
        pool = OpenAIModelPool(
            [LLMEndpointConfig(name="primary", api_key="k1", base_url="https://a", model="m1")],
            client_factory=_FakeClientFactory([RuntimeError("down")]),
        )

        with self.assertRaises(RuntimeError) as ctx:
            pool.chat.completions.create(messages=[{"role": "user", "content": "hi"}])

        self.assertIn("model_pool=", str(ctx.exception))
        self.assertIn("primary", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
