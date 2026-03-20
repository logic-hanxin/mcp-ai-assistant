"""
配置管理
"""

import os
import sys
from dotenv import load_dotenv
from assistant.llm.deepseek import DeepSeekConfig, LLMEndpointConfig


def _parse_model_pool(primary_endpoint: LLMEndpointConfig) -> list[LLMEndpointConfig]:
    pool_names = [name.strip() for name in os.getenv("LLM_POOL", "").split(",") if name.strip()]
    endpoints: list[LLMEndpointConfig] = []

    if not pool_names:
        return [primary_endpoint]

    for idx, raw_name in enumerate(pool_names, start=1):
        if raw_name.lower() == "primary":
            endpoints.append(primary_endpoint)
            continue

        env_prefix = f"LLM_{raw_name.upper()}"
        api_key = os.getenv(f"{env_prefix}_API_KEY", "")
        base_url = os.getenv(f"{env_prefix}_BASE_URL", "")
        model = os.getenv(f"{env_prefix}_MODEL", "")

        if not api_key or not base_url or not model:
            print(f"错误: 模型池节点 {raw_name} 配置不完整")
            print(f"  需要配置 {env_prefix}_API_KEY / {env_prefix}_BASE_URL / {env_prefix}_MODEL")
            sys.exit(1)

        endpoints.append(
            LLMEndpointConfig(
                name=raw_name,
                api_key=api_key,
                base_url=base_url,
                model=model,
            )
        )

    if not endpoints:
        endpoints.append(primary_endpoint)

    return endpoints


def load_config() -> DeepSeekConfig:
    """从 .env 加载配置"""
    load_dotenv()

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key == "your-deepseek-api-key-here":
        print("错误: 请配置 DEEPSEEK_API_KEY")
        print("  1. 复制 .env.example 为 .env")
        print("  2. 填入你的 DeepSeek API Key (https://platform.deepseek.com)")
        sys.exit(1)

    primary_endpoint = LLMEndpointConfig(
        name="primary",
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    )
    model_pool = _parse_model_pool(primary_endpoint)

    return DeepSeekConfig(
        api_key=primary_endpoint.api_key,
        base_url=primary_endpoint.base_url,
        model=primary_endpoint.model,
        model_pool=model_pool,
        request_timeout=float(os.getenv("LLM_REQUEST_TIMEOUT", "60")),
        max_retries_per_endpoint=int(os.getenv("LLM_MAX_RETRIES_PER_ENDPOINT", "1")),
    )
