"""
私人AI助手 - 启动入口

使用方式:
    python -m assistant.main
"""

import asyncio
from pathlib import Path

from assistant.config import load_config
from assistant.agent.core import AgentCore
from assistant.agent.reminder_checker import reminder_loop
from assistant.agent.github_checker import github_check_loop
from assistant.agent.news_checker import news_check_loop
from assistant.agent.workflow_runner import workflow_loop

BANNER = r"""
╔════════════════════════════════════════════════════╗
║         私人AI助手 (MCP + DeepSeek Agent)          ║
╠════════════════════════════════════════════════════╣
║  命令:                                             ║
║    /clear      - 清空对话历史（保存到长期记忆）      ║
║    /tools      - 查看可用工具                       ║
║    /skills     - 查看已加载的 Skills                 ║
║    /reminders  - 查看待执行的提醒                    ║
║    /fact K V   - 保存个人信息 (如 /fact 名字 小明)   ║
║    /facts      - 查看已保存的个人信息                ║
║    /help       - 显示帮助                           ║
║    /quit       - 退出                               ║
╚════════════════════════════════════════════════════╝
"""


async def run():
    config = load_config()
    agent = AgentCore(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        model_pool=config.model_pool,
        llm_request_timeout=config.request_timeout,
        llm_max_retries_per_endpoint=config.max_retries_per_endpoint,
    )
    background_tasks: list[asyncio.Task] = []

    server_script = str(Path(__file__).parent / "mcp" / "server.py")

    try:
        await agent.connect(server_script)

        # 启动后台检查器
        background_tasks = [
            asyncio.create_task(reminder_loop()),
            asyncio.create_task(github_check_loop()),
            asyncio.create_task(news_check_loop()),
            asyncio.create_task(workflow_loop()),
        ]

        print(BANNER)

        while True:
            try:
                # 在线程中运行 input()，避免阻塞事件循环（后台提醒检查器需要运行）
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("\n你: ").strip()
                )
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                break

            if not user_input:
                continue

            # 命令处理
            if user_input.startswith("/"):
                parts = user_input.split(maxsplit=2)
                cmd = parts[0].lower()

                if cmd == "/quit":
                    print("再见！")
                    break
                elif cmd == "/clear":
                    agent.clear_history()
                elif cmd == "/tools":
                    print("可用工具:")
                    for t in agent.mcp.tools:
                        f = t["function"]
                        print(f"  - {f['name']}: {f['description'][:60]}")
                elif cmd == "/skills":
                    from assistant.skills.base import get_registered_skills
                    for cls in get_registered_skills():
                        s = cls()
                        tools = [t.name for t in s.get_tools()]
                        print(f"  [{s.name}] {s.description} -> {', '.join(tools)}")
                elif cmd == "/fact" and len(parts) >= 3:
                    agent.save_fact(parts[1], parts[2])
                    print(f"已保存: {parts[1]} = {parts[2]}")
                elif cmd == "/facts":
                    facts = agent.memory.get_facts()
                    if facts:
                        for k, v in facts.items():
                            print(f"  {k}: {v}")
                    else:
                        print("  暂无保存的个人信息。")
                elif cmd == "/reminders":
                    from assistant.agent import db_misc as _db
                    import datetime as _dt
                    try:
                        reminders = _db.reminder_get_all_pending()
                    except Exception:
                        reminders = []
                    if not reminders:
                        print("  暂无待执行的提醒。")
                    else:
                        now = _dt.datetime.now()
                        for r in reminders:
                            target = r["target_time"]
                            if isinstance(target, str):
                                target = _dt.datetime.fromisoformat(target)
                            delta = target - now
                            mins = max(0, int(delta.total_seconds()) // 60)
                            h, m = divmod(mins, 60)
                            remaining = f"{h}小时{m}分钟" if h else f"{m}分钟"
                            print(f"  [{r['id']}] {r['message']}  {target.strftime('%m-%d %H:%M')}  (还有 {remaining})")
                elif cmd == "/help":
                    print(BANNER)
                else:
                    print(f"未知命令: {cmd}")
                continue

            # 正常对话
            try:
                reply = await agent.chat(user_input)
                print(f"\n助手: {reply}")
            except Exception as e:
                print(f"\n出错了: {e}")

    finally:
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
        await agent.close()


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
