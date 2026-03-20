"""OpenAI-compatible 模型池与自动回退。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from assistant.llm.deepseek import DeepSeekConfig, LLMEndpointConfig


@dataclass
class _RuntimeEndpoint:
    name: str
    model: str
    client: Any


class _PoolChatCompletions:
    def __init__(self, pool: "OpenAIModelPool"):
        self._pool = pool

    def create(self, **kwargs):
        return self._pool.create_chat_completion(**kwargs)


class _PoolChat:
    def __init__(self, pool: "OpenAIModelPool"):
        self.completions = _PoolChatCompletions(pool)


class OpenAIModelPool:
    """对 OpenAI 客户端做一层模型池封装，保留 chat.completions.create 接口。"""

    def __init__(
        self,
        endpoints: list[LLMEndpointConfig],
        *,
        request_timeout: float = 60.0,
        max_retries_per_endpoint: int = 1,
        client_factory: Callable[..., Any] | None = None,
    ):
        if not endpoints:
            raise ValueError("OpenAIModelPool requires at least one endpoint")

        if client_factory is None:
            from openai import OpenAI
            client_factory = OpenAI

        self.request_timeout = request_timeout
        self.max_retries_per_endpoint = max(1, int(max_retries_per_endpoint or 1))
        self._endpoints = [
            _RuntimeEndpoint(
                name=endpoint.name,
                model=endpoint.model,
                client=client_factory(api_key=endpoint.api_key, base_url=endpoint.base_url),
            )
            for endpoint in endpoints
        ]
        self.chat = _PoolChat(self)

    def create_chat_completion(self, **kwargs):
        errors: list[str] = []

        for endpoint in self._endpoints:
            for attempt in range(1, self.max_retries_per_endpoint + 1):
                request_kwargs = dict(kwargs)
                request_kwargs["model"] = endpoint.model
                request_kwargs.setdefault("timeout", self.request_timeout)
                try:
                    return endpoint.client.chat.completions.create(**request_kwargs)
                except Exception as exc:
                    errors.append(f"{endpoint.name}[{attempt}/{self.max_retries_per_endpoint}]: {exc}")
                    if len(self._endpoints) > 1:
                        print(f"[LLMPool] {endpoint.name} 调用失败，尝试回退: {exc}")

        error_summary = " | ".join(errors[:6]) if errors else "unknown"
        raise RuntimeError(f"Connection error. model_pool={error_summary}")


def build_llm_client(config: DeepSeekConfig) -> OpenAIModelPool:
    endpoints = config.model_pool or [
        LLMEndpointConfig(
            name="primary",
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
        )
    ]
    return OpenAIModelPool(
        endpoints,
        request_timeout=config.request_timeout,
        max_retries_per_endpoint=config.max_retries_per_endpoint,
    )
