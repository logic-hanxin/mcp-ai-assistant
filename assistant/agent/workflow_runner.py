"""
工作流后台执行器

每 30 秒检查到期工作流，按步骤执行工具调用，
将结果汇总后通过 QQ 通知用户。

工作流步骤格式: [{"tool": "get_weather", "args": {"city": "北京"}}, ...]
调度格式:
  daily:08:00           - 每天 08:00
  weekly:1,3,5:09:00    - 每周一三五 09:00 (1=周一, 7=周日)
  interval:30m          - 每 30 分钟 (支持 m/h)
  once:2026-03-20 15:00 - 单次执行
"""

from __future__ import annotations

import os
import re
import json
import asyncio
import datetime
from datetime import timedelta

import httpx

from assistant.agent import db

NAPCAT_API_URL = os.getenv("NAPCAT_API_URL", "http://127.0.0.1:3000")
CHECK_INTERVAL = 30  # 秒

# 延迟加载的工具处理器映射
_tool_handlers: dict | None = None


def _ensure_tools():
    """延迟加载所有 Skill 工具处理器"""
    global _tool_handlers
    if _tool_handlers is not None:
        return
    _tool_handlers = {}
    try:
        from assistant.skills.base import discover_and_load_skills
        skills = discover_and_load_skills()
        for skill in skills:
            for tool_def in skill.get_tools():
                _tool_handlers[tool_def.name] = tool_def.handler
        print(f"[工作流] 加载了 {len(_tool_handlers)} 个工具")
    except Exception as e:
        print(f"[工作流] 工具加载失败: {e}")


# ============================================================
# 调度计算
# ============================================================
def calc_next_run(schedule: str, after: datetime.datetime = None) -> datetime.datetime | None:
    """根据调度规则计算下一次执行时间"""
    now = after or datetime.datetime.now()

    # daily:HH:MM
    m = re.match(r'^daily:(\d{1,2}):(\d{2})$', schedule)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        target = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target

    # weekly:1,3,5:HH:MM  (1=周一, 7=周日)
    m = re.match(r'^weekly:([\d,]+):(\d{1,2}):(\d{2})$', schedule)
    if m:
        days = [int(d) for d in m.group(1).split(",")]
        h, mi = int(m.group(2)), int(m.group(3))
        for delta in range(1, 8):
            candidate = now + timedelta(days=delta)
            if candidate.isoweekday() in days:
                return candidate.replace(hour=h, minute=mi, second=0, microsecond=0)
        return now + timedelta(days=1)

    # interval:30m / interval:2h
    m = re.match(r'^interval:(\d+)([mh])$', schedule)
    if m:
        val, unit = int(m.group(1)), m.group(2)
        if unit == "m":
            return now + timedelta(minutes=val)
        elif unit == "h":
            return now + timedelta(hours=val)

    # once:2026-03-20 15:00  (单次，执行后不再调度)
    m = re.match(r'^once:(.+)$', schedule)
    if m:
        try:
            target = datetime.datetime.strptime(m.group(1).strip(), "%Y-%m-%d %H:%M")
            if target > now:
                return target
        except ValueError:
            pass
        return None  # 已过期或解析失败

    return None


# ============================================================
# 工作流执行
# ============================================================
def _execute_step(tool_name: str, args: dict) -> str:
    """执行单个工作流步骤，返回结果文本"""
    _ensure_tools()

    handler = _tool_handlers.get(tool_name)
    if not handler:
        return f"[错误] 未知工具: {tool_name}"

    try:
        result = handler(**args)
        return str(result) if result else "(无结果)"
    except Exception as e:
        return f"[执行失败] {tool_name}: {e}"


def execute_workflow_steps(steps: list[dict]) -> list[dict]:
    """
    执行工作流的所有步骤，返回结果列表。
    每个结果: {"step": 1, "tool": "xxx", "result": "..."}
    """
    results = []
    for i, step in enumerate(steps, 1):
        tool_name = step.get("tool", "")
        args = step.get("args", {})
        result = _execute_step(tool_name, args)
        results.append({
            "step": i,
            "tool": tool_name,
            "result": result,
        })
    return results


def format_workflow_result(workflow_name: str, results: list[dict]) -> str:
    """将工作流执行结果格式化为通知文本"""
    lines = [f"[工作流] {workflow_name} 执行完成"]
    for r in results:
        lines.append(f"\n--- 步骤{r['step']}: {r['tool']} ---")
        # 截取结果避免消息过长
        text = r["result"]
        if len(text) > 500:
            text = text[:500] + "..."
        lines.append(text)
    return "\n".join(lines)


# ============================================================
# 后台调度循环
# ============================================================
async def workflow_loop():
    """后台循环，定期检查并执行到期工作流"""
    await asyncio.sleep(20)  # 启动延迟
    print(f"[工作流] 调度引擎已启动，间隔 {CHECK_INTERVAL}s")

    while True:
        try:
            await _check_and_run()
        except Exception as e:
            print(f"[工作流] 调度异常: {e}")
        await asyncio.sleep(CHECK_INTERVAL)


async def _check_and_run():
    """检查到期工作流并执行"""
    try:
        due_workflows = db.workflow_get_due()
    except Exception:
        return

    for wf in due_workflows:
        wf_id = wf["id"]
        wf_name = wf["name"]
        schedule = wf["schedule"]

        print(f"[工作流] 执行: {wf_name} (ID:{wf_id})")

        # 解析步骤
        steps_raw = wf["steps"]
        if isinstance(steps_raw, str):
            try:
                steps = json.loads(steps_raw)
            except json.JSONDecodeError:
                print(f"[工作流] 步骤解析失败: {wf_name}")
                continue
        else:
            steps = steps_raw

        # 在线程中执行（避免阻塞事件循环）
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, execute_workflow_steps, steps)

        # 格式化结果
        result_text = format_workflow_result(wf_name, results)

        # 发送通知
        notify_qq = wf.get("notify_qq", "")
        notify_group = wf.get("notify_group_id", "")
        if notify_qq or notify_group:
            await _send_notification(notify_qq, notify_group, result_text)

        # 计算下一次执行时间
        next_run = calc_next_run(schedule, after=datetime.datetime.now())
        next_run_str = next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else None

        # 单次任务执行后自动禁用
        if schedule.startswith("once:") or next_run is None:
            try:
                db.workflow_toggle(wf_id, enabled=False)
            except Exception:
                pass

        # 更新执行记录
        try:
            db.workflow_update_after_run(
                wf_id,
                next_run=next_run_str,
                last_result=result_text[:2000],
            )
        except Exception as e:
            print(f"[工作流] 更新执行记录失败: {e}")

        print(f"[工作流] {wf_name} 执行完成，下次: {next_run_str or '无'}")


async def _send_notification(notify_qq: str, notify_group: str, text: str):
    """发送工作流执行结果通知"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if notify_group:
                message = [{"type": "text", "data": {"text": text}}]
                if notify_qq:
                    message.insert(0, {"type": "at", "data": {"qq": notify_qq}})
                    message.insert(1, {"type": "text", "data": {"text": " "}})
                await client.post(f"{NAPCAT_API_URL}/send_group_msg", json={
                    "group_id": int(notify_group),
                    "message": message,
                })
            elif notify_qq:
                await client.post(f"{NAPCAT_API_URL}/send_private_msg", json={
                    "user_id": int(notify_qq),
                    "message": [{"type": "text", "data": {"text": text}}],
                })
    except Exception as e:
        print(f"[工作流] 通知发送失败: {e}")
