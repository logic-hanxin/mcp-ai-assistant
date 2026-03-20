"""
Web API 服务 - 将 Agent 包装为 HTTP 接口

为 NapCat/OneBot 等外部平台提供对话能力。
每个用户（QQ号）维护独立的 Agent 会话。
"""

import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI

from assistant.config import load_config
from assistant.agent.core import AgentCore
from assistant.agent.reminder_checker import reminder_loop
from assistant.agent.github_checker import github_check_loop
from assistant.agent.news_checker import news_check_loop
from assistant.agent.site_checker import site_check_loop
from assistant.agent.workflow_runner import workflow_loop


# 每个用户独立的 Agent 实例
_agents: dict[str, AgentCore] = {}
_config = None
_server_script = None


async def get_agent(user_id: str) -> AgentCore:
    """获取或创建用户专属 Agent（session_id = user_id，实现记忆隔离）"""
    if user_id not in _agents:
        agent = AgentCore(
            api_key=_config.api_key,
            base_url=_config.base_url,
            model=_config.model,
            session_id=user_id,
            user_id=user_id,
            model_pool=_config.model_pool,
            llm_request_timeout=_config.request_timeout,
            llm_max_retries_per_endpoint=_config.max_retries_per_endpoint,
        )
        await agent.connect(_server_script)
        _agents[user_id] = agent
    return _agents[user_id]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _server_script
    background_tasks: list[asyncio.Task] = []
    _config = load_config()
    _server_script = str(Path(__file__).resolve().parent.parent / "mcp" / "server.py")

    # 初始化记忆数据库表
    try:
        from assistant.agent.db_core import init_tables
        init_tables()
    except Exception as e:
        print(f"[API] 记忆数据库初始化失败，将使用纯内存模式: {e}")

    # 启动后台检查器
    background_tasks = [
        asyncio.create_task(reminder_loop()),
        asyncio.create_task(github_check_loop()),
        asyncio.create_task(news_check_loop()),
        asyncio.create_task(site_check_loop()),
        asyncio.create_task(workflow_loop()),
    ]
    print("[API] AI助手服务已启动")
    yield

    for task in background_tasks:
        task.cancel()
    if background_tasks:
        await asyncio.gather(*background_tasks, return_exceptions=True)
    for agent in _agents.values():
        await agent.close()
    _agents.clear()


app = FastAPI(title="AI助手 API", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "active_sessions": len(_agents)}
