"""LLM 配置与模型池"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LLMEndpointConfig:
    name: str
    api_key: str
    base_url: str
    model: str


@dataclass
class DeepSeekConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    model_pool: list[LLMEndpointConfig] = field(default_factory=list)
    request_timeout: float = 60.0
    max_retries_per_endpoint: int = 1
