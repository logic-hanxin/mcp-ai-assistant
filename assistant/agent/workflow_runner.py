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
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from assistant.agent.blackboard import Blackboard
from assistant.agent.tool_adapters import ToolEvent, build_default_tool_adapters, dispatch_tool_adapters
from assistant.agent.tool_hydrators import ToolHydrationContext, build_default_tool_hydrators, hydrate_tool_args
from assistant.agent.tool_policies import apply_tool_policies, build_default_tool_policies

NAPCAT_API_URL = os.getenv("NAPCAT_API_URL", "http://127.0.0.1:3000")
CHECK_INTERVAL = 30  # 秒

# 延迟加载的工具处理器映射
_tool_handlers: dict | None = None
_tool_definitions: dict | None = None
_tool_metadata: dict | None = None
_db_module = None


def _get_db():
    """延迟导入 DB 模块，降低模块导入时的环境依赖。"""
    global _db_module
    if _db_module is None:
        from assistant.agent import db_workflow as db_module
        _db_module = db_module
    return _db_module


def parse_workflow_steps(steps_raw: Any) -> tuple[list[dict] | None, str | None]:
    """
    解析并校验工作流步骤定义。

    支持输入:
    - JSON 字符串
    - Python list[dict]
    """
    if isinstance(steps_raw, str):
        try:
            steps = json.loads(steps_raw)
        except json.JSONDecodeError as e:
            return None, f"steps JSON 解析失败: {e}"
    else:
        steps = steps_raw

    if not isinstance(steps, list) or not steps:
        return None, "steps 必须是非空的步骤数组。"

    normalized_steps: list[dict] = []
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            return None, f"步骤 {index} 必须是对象，当前为: {type(step).__name__}"

        tool_name = step.get("tool")
        if not isinstance(tool_name, str) or not tool_name.strip():
            return None, f"步骤 {index} 缺少有效的 tool 字段。"

        args = step.get("args", {})
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return None, f"步骤 {index} 的 args 必须是对象。"

        normalized_steps.append({
            "tool": tool_name.strip(),
            "args": args,
        })

    return normalized_steps, None


def _ensure_tools():
    """延迟加载所有 Skill 工具处理器"""
    global _tool_handlers, _tool_definitions, _tool_metadata
    if _tool_handlers is not None and _tool_definitions is not None and _tool_metadata is not None:
        return
    _tool_handlers = {}
    try:
        from assistant.skills.base import (
            discover_and_load_skills,
            discover_tool_definitions,
            discover_tool_metadata,
        )
        skills = discover_and_load_skills()
        for skill in skills:
            for tool_def in skill.get_tools():
                _tool_handlers[tool_def.name] = tool_def.handler
        _tool_definitions = discover_tool_definitions()
        _tool_metadata = discover_tool_metadata()
        print(f"[工作流] 加载了 {len(_tool_handlers)} 个工具")
    except Exception as e:
        print(f"[工作流] 工具加载失败: {e}")


@dataclass
class WorkflowRuntime:
    workflow_id: int | str
    workflow_name: str
    session_context: dict

    def __post_init__(self):
        _ensure_tools()
        self.blackboard = Blackboard.get_instance()
        self.tool_hydrators = build_default_tool_hydrators()
        self.tool_adapters = build_default_tool_adapters()
        self.tool_policies = build_default_tool_policies()
        self.tool_metadata = _tool_metadata or {}
        self.tool_definitions = _tool_definitions or {}

    def scope(self) -> str:
        return f"workflow:{self.workflow_id}"

    def scoped_key(self, key: str) -> str:
        return f"{self.scope()}:{key}"

    def _bb_scoped_key(self, key: str) -> str:
        return self.scoped_key(key)

    def scoped_step_id(self, step_id: str) -> str:
        return f"{self.scope()}:{step_id}"

    def scoped_milestone(self, milestone: str) -> str:
        return f"{self.scope()}:{milestone}"

    def reset_scope(self):
        self.blackboard.clear_scope(self.scope())

    def hydrate_args(self, tool_name: str, tool_args: dict) -> dict:
        session_user = str(self.session_context.get("user_qq", "")).strip()
        session_group = str(self.session_context.get("group_id", "")).strip()
        session_image = str(self.session_context.get("latest_image_url", "")).strip()
        session_file = str(self.session_context.get("latest_file_url", "")).strip()
        bb_user = str(self.blackboard.get(self.scoped_key("last_target_qq"), "")).strip() or self.latest_contact_qq()
        bb_group = str(self.blackboard.get(self.scoped_key("last_target_group"), "")).strip()
        bb_repo = str(self.blackboard.get(self.scoped_key("last_github_repo"), "")).strip()
        bb_branch = str(self.blackboard.get(self.scoped_key("last_github_branch"), "")).strip()
        bb_city = str(self.blackboard.get(self.scoped_key("last_city"), "")).strip()
        bb_image = str(self.blackboard.get(self.scoped_key("last_image_url"), "")).strip()
        bb_file = str(self.blackboard.get(self.scoped_key("last_file_url"), "")).strip()
        shareable_text = self.latest_shareable_result()
        return hydrate_tool_args(
            ToolHydrationContext(
                tool_name=tool_name,
                tool_args=dict(tool_args),
                session_user=session_user,
                session_group=session_group,
                session_image=session_image,
                session_file=session_file,
                bb_user=bb_user,
                bb_group=bb_group,
                bb_repo=bb_repo,
                bb_branch=bb_branch,
                bb_city=bb_city,
                bb_image=bb_image,
                bb_file=bb_file,
                shareable_text=shareable_text,
            ),
            self.tool_hydrators,
        )

    def apply_policy(self, tool_name: str, tool_args: dict) -> str | None:
        return apply_tool_policies(
            tool_name=tool_name,
            tool_args=tool_args,
            tool_metadata=self.tool_metadata.get(tool_name, {}),
            session_context=self.session_context,
            policies=self.tool_policies,
        )

    def update_blackboard(self, step_index: int, tool_name: str, tool_args: dict, tool_result: str, structured_result: dict | None = None):
        self._record_blackboard_variables(tool_name, tool_args, tool_result)
        dispatch_tool_adapters(
            self,
            ToolEvent(
                tool_name=tool_name,
                tool_args=tool_args,
                tool_result=tool_result,
                structured_result=structured_result,
            ),
            self.tool_adapters,
        )
        self.blackboard.write_result(
            step_id=self.scoped_step_id(f"step_{step_index}_{tool_name}"),
            milestone=self.scoped_milestone("workflow"),
            tool_name=tool_name,
            result=tool_result[:500],
        )

    def _record_blackboard_variables(self, tool_name: str, tool_args: dict, tool_result: str):
        meta = self.tool_metadata.get(tool_name, {})
        for arg_key, bb_key in meta.get("store_args", {}).items():
            value = str(tool_args.get(arg_key, "")).strip()
            if value:
                self.blackboard.set(self.scoped_key(bb_key), value[:500])

        for bb_key in meta.get("store_result", []):
            self.blackboard.set(self.scoped_key(bb_key), tool_result[:500])

        if tool_name in ("query_database", "list_tables", "get_table_schema"):
            self.blackboard.set(self.scoped_key("last_db_result"), tool_result[:500])
        elif tool_name in ("web_search", "browse_page", "get_json"):
            self.blackboard.set(self.scoped_key("last_search_result"), tool_result[:500])

    def latest_contact_qq(self) -> str:
        latest_entity = None
        for entity in self.blackboard.get_entities("contact"):
            if not entity.key.startswith(f"{self.scope()}:"):
                continue
            if latest_entity is None or entity.discovered_at > latest_entity.discovered_at:
                latest_entity = entity
        if latest_entity and isinstance(latest_entity.value, dict):
            return str(latest_entity.value.get("qq", "")).strip()
        return ""

    def latest_shareable_result(self) -> str:
        for key in (
            "last_shared_result",
            "last_knowledge_result",
            "last_search_result",
            "last_db_result",
            "last_note_result",
            "last_weather",
            "last_reminder",
            "last_workflow_result",
        ):
            value = str(self.blackboard.get(self.scoped_key(key), "")).strip()
            if value:
                return value

        results = [
            item for item in self.blackboard.get_results()
            if item.step_id.startswith(f"{self.scope()}:")
        ]
        if results:
            return results[-1].result[:500]
        return ""


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
        if not (0 <= h <= 23 and 0 <= mi <= 59):
            return None
        target = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target

    # weekly:1,3,5:HH:MM  (1=周一, 7=周日)
    m = re.match(r'^weekly:([\d,]+):(\d{1,2}):(\d{2})$', schedule)
    if m:
        try:
            days = sorted({int(d) for d in m.group(1).split(",") if d})
        except ValueError:
            return None
        h, mi = int(m.group(2)), int(m.group(3))
        if not days or any(day < 1 or day > 7 for day in days):
            return None
        if not (0 <= h <= 23 and 0 <= mi <= 59):
            return None

        for delta in range(0, 8):
            candidate = now + timedelta(days=delta)
            if candidate.isoweekday() not in days:
                continue
            run_at = candidate.replace(hour=h, minute=mi, second=0, microsecond=0)
            if run_at > now:
                return run_at
        return None

    # interval:30m / interval:2h
    m = re.match(r'^interval:(\d+)([mh])$', schedule)
    if m:
        val, unit = int(m.group(1)), m.group(2)
        if val <= 0:
            return None
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
def _execute_step(tool_name: str, args: dict) -> tuple[str, dict | None]:
    """执行单个工作流步骤，返回结果文本和结构化结果。"""
    _ensure_tools()

    handler = _tool_handlers.get(tool_name)
    if not handler:
        return f"[错误] 未知工具: {tool_name}", None

    try:
        result = handler(**args)
        result_text = str(result) if result else "(无结果)"
        structured = None
        tool_def = (_tool_definitions or {}).get(tool_name)
        parser = getattr(tool_def, "result_parser", None) if tool_def else None
        if parser:
            try:
                parsed = parser(args, result_text)
                structured = parsed if isinstance(parsed, dict) else None
            except Exception:
                structured = None
        return result_text, structured
    except Exception as e:
        return f"[执行失败] {tool_name}: {e}", None


def execute_workflow_steps(
    steps: list[dict],
    workflow_id: int | str = "adhoc",
    workflow_name: str = "工作流",
    session_context: dict | None = None,
    clear_scope: bool = True,
) -> list[dict]:
    """
    执行工作流的所有步骤，返回结果列表。
    每个结果: {"step": 1, "tool": "xxx", "result": "...", "args": {...}}
    """
    runtime = WorkflowRuntime(
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        session_context=dict(session_context or {}),
    )
    if clear_scope:
        runtime.reset_scope()

    results = []
    for i, step in enumerate(steps, 1):
        tool_name = step.get("tool", "")
        raw_args = step.get("args", {})
        args = runtime.hydrate_args(tool_name, raw_args)
        policy_error = runtime.apply_policy(tool_name, args)
        if policy_error:
            result = policy_error
            structured = None
        else:
            result, structured = _execute_step(tool_name, args)
        runtime.update_blackboard(i, tool_name, args, result, structured_result=structured)
        results.append({
            "step": i,
            "tool": tool_name,
            "result": result,
            "args": args,
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
        due_workflows = _get_db().workflow_get_due()
    except Exception:
        return

    for wf in due_workflows:
        wf_id = wf["id"]
        wf_name = wf["name"]
        schedule = wf["schedule"]

        print(f"[工作流] 执行: {wf_name} (ID:{wf_id})")

        # 解析步骤
        steps, error = parse_workflow_steps(wf["steps"])
        if error:
            print(f"[工作流] 步骤解析失败: {wf_name} - {error}")
            try:
                _get_db().workflow_update_after_run(
                    wf_id,
                    next_run=None,
                    last_result=error[:2000],
                )
                _get_db().workflow_toggle(wf_id, enabled=False)
            except Exception:
                pass
            continue

        # 在线程中执行（避免阻塞事件循环）
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            execute_workflow_steps,
            steps,
            wf_id,
            wf_name,
            {
                "user_qq": str(wf.get("notify_qq", "")).strip(),
                "group_id": str(wf.get("notify_group_id", "")).strip(),
            },
        )

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
                _get_db().workflow_toggle(wf_id, enabled=False)
            except Exception:
                pass

        # 更新执行记录
        try:
            _get_db().workflow_update_after_run(
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
        import httpx
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
