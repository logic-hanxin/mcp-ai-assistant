"""
配置管理
"""

import os
import sys
from dotenv import load_dotenv
from assistant.llm.deepseek import DeepSeekConfig


def load_config() -> DeepSeekConfig:
    """从 .env 加载配置"""
    load_dotenv()

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key == "your-deepseek-api-key-here":
        print("错误: 请配置 DEEPSEEK_API_KEY")
        print("  1. 复制 .env.example 为 .env")
        print("  2. 填入你的 DeepSeek API Key (https://platform.deepseek.com)")
        sys.exit(1)

    return DeepSeekConfig(
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    )
