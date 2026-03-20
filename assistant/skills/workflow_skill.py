"""
工作流 Skill - 创建和管理自动化工作流

用户用自然语言描述自动化任务，LLM 将其转换为结构化的工作流定义。
工作流在后台按调度规则自动执行，结果通过 QQ 通知。

示例:
  "每天早上8点查北京天气然后发给我"
  "每周一三五9点获取热搜新闻发到群里"
  "每隔2小时检查一下GitHub仓库有没有新提交"
"""

import datetime
import re
from assistant.skills.base import BaseSkill, ToolDefinition, register
from assistant.agent import db_workflow as db
from assistant.agent.workflow_runner import (
    calc_next_run,
    execute_workflow_steps,
    format_workflow_result,
    parse_workflow_steps,
)


class WorkflowSkill(BaseSkill):
    name = "workflow"
    description = "自动化工作流引擎，定时自动执行一系列操作并通知"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="create_workflow",
                description=(
                    "创建一个自动化工作流。工作流会按设定的时间自动执行一系列工具操作，并将结果通知用户。\n"
                    "steps 是 JSON 数组，每个元素: {\"tool\": \"工具名\", \"args\": {参数}}\n"
                    "可用工具举例: get_weather, get_hot_news, web_search, query_database, list_tables, "
                    "get_table_schema, github_get_latest_commits, search_music 等所有已注册工具。\n"
                    "schedule 调度格式:\n"
                    "  daily:HH:MM         - 每天定时 (如 daily:08:00)\n"
                    "  weekly:天,天:HH:MM  - 每周指定日 (如 weekly:1,3,5:09:00, 1=周一 7=周日)\n"
                    "  interval:数值单位   - 固定间隔 (如 interval:30m 或 interval:2h)\n"
                    "  once:日期 时间      - 单次执行 (如 once:2026-03-20 15:00)"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "工作流名称，简短描述用途",
                        },
                        "steps": {
                            "type": "string",
                            "description": (
                                'JSON数组格式的步骤定义。'
                                '例: [{"tool":"get_weather","args":{"city":"北京"}},{"tool":"get_hot_news","args":{}}]'
                            ),
                        },
                        "schedule": {
                            "type": "string",
                            "description": "调度规则，如 daily:08:00",
                        },
                        "notify_qq": {
                            "type": "string",
                            "description": "执行结果通知的QQ号",
                            "default": "",
                        },
                        "notify_group_id": {
                            "type": "string",
                            "description": "执行结果通知的群号（群内发送）",
                            "default": "",
                        },
                    },
                    "required": ["name", "steps", "schedule"],
                },
                handler=self._create_workflow,
                metadata={
                    "category": "write",
                    "side_effect": "scheduled_notification",
                    "blackboard_reads": ["target_user", "target_group"],
                    "required_all": ["name", "steps", "schedule"],
                    "required_any": [["notify_qq", "notify_group_id"]],
                    "store_args": {
                        "notify_qq": "last_target_qq",
                        "notify_group_id": "last_target_group",
                    },
                    "store_result": ["last_workflow_result"],
                },
                result_parser=self._parse_create_workflow_result,
                keywords=["工作流", "自动化", "定时执行", "自动任务"],
                intents=["create_workflow", "schedule_workflow"],
            ),
            ToolDefinition(
                name="list_workflows",
                description="列出所有工作流及其状态（启用/禁用、下次执行时间、执行次数等）。",
                parameters={"type": "object", "properties": {}},
                handler=self._list_workflows,
                metadata={
                    "category": "read",
                    "blackboard_writes": ["last_workflow_result"],
                    "store_result": ["last_workflow_result"],
                },
                result_parser=self._parse_list_workflows_result,
                keywords=["工作流列表", "查看自动化任务", "已配置工作流"],
                intents=["list_workflows"],
            ),
            ToolDefinition(
                name="toggle_workflow",
                description="启用或禁用一个工作流。",
                parameters={
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "integer", "description": "工作流ID"},
                        "enabled": {"type": "boolean", "description": "true=启用, false=禁用"},
                    },
                    "required": ["workflow_id", "enabled"],
                },
                handler=self._toggle_workflow,
                metadata={
                    "category": "write",
                    "side_effect": "data_write",
                    "required_all": ["workflow_id", "enabled"],
                    "store_result": ["last_workflow_result"],
                },
                result_parser=self._parse_toggle_workflow_result,
                keywords=["启用工作流", "禁用工作流", "切换自动化"],
                intents=["toggle_workflow"],
            ),
            ToolDefinition(
                name="delete_workflow",
                description="删除一个工作流。",
                parameters={
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "integer", "description": "工作流ID"},
                    },
                    "required": ["workflow_id"],
                },
                handler=self._delete_workflow,
                metadata={
                    "category": "write",
                    "side_effect": "data_write",
                    "required_all": ["workflow_id"],
                    "store_result": ["last_workflow_result"],
                },
                result_parser=self._parse_delete_workflow_result,
                keywords=["删除工作流", "移除自动化任务"],
                intents=["delete_workflow"],
            ),
            ToolDefinition(
                name="run_workflow_now",
                description="立即手动执行一个工作流（不影响正常调度），返回执行结果。",
                parameters={
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "integer", "description": "工作流ID"},
                    },
                    "required": ["workflow_id"],
                },
                handler=self._run_now,
                metadata={
                    "category": "write",
                    "side_effect": "external_trigger",
                    "required_all": ["workflow_id"],
                    "store_result": ["last_workflow_result"],
                },
                result_parser=self._parse_run_workflow_result,
                keywords=["立即执行工作流", "手动运行自动化", "现在运行任务"],
                intents=["run_workflow_now"],
            ),
            ToolDefinition(
                name="describe_workflow",
                description="查看某个工作流的详细配置、步骤、最近结果和通知设置。",
                parameters={
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "integer", "description": "工作流ID"},
                    },
                    "required": ["workflow_id"],
                },
                handler=self._describe_workflow,
                metadata={
                    "category": "read",
                    "required_all": ["workflow_id"],
                    "store_result": ["last_workflow_result"],
                },
                result_parser=self._parse_describe_workflow_result,
                keywords=["工作流详情", "查看工作流配置", "工作流步骤"],
                intents=["describe_workflow"],
            ),
            ToolDefinition(
                name="clone_workflow",
                description="复制一个已有工作流，可选修改名称、调度和通知对象。",
                parameters={
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "integer", "description": "源工作流ID"},
                        "new_name": {"type": "string", "description": "新工作流名称（可选）", "default": ""},
                        "new_schedule": {"type": "string", "description": "新调度规则（可选）", "default": ""},
                        "notify_qq": {"type": "string", "description": "新的通知QQ（可选）", "default": ""},
                        "notify_group_id": {"type": "string", "description": "新的通知群（可选）", "default": ""},
                    },
                    "required": ["workflow_id"],
                },
                handler=self._clone_workflow,
                metadata={
                    "category": "write",
                    "side_effect": "scheduled_notification",
                    "required_all": ["workflow_id"],
                    "store_args": {
                        "notify_qq": "last_target_qq",
                        "notify_group_id": "last_target_group",
                    },
                    "store_result": ["last_workflow_result"],
                },
                result_parser=self._parse_clone_workflow_result,
                keywords=["复制工作流", "克隆自动化任务", "基于现有工作流新建"],
                intents=["clone_workflow"],
            ),
        ]

    def _create_workflow(self, name: str, steps: str, schedule: str,
                         notify_qq: str = "", notify_group_id: str = "") -> str:
        steps_list, steps_error = parse_workflow_steps(steps)
        if steps_error:
            return steps_error

        # 验证 schedule
        next_run = calc_next_run(schedule)
        if next_run is None:
            return (
                f"无法解析调度规则 '{schedule}'。支持的格式:\n"
                f"  daily:08:00\n"
                f"  weekly:1,3,5:09:00\n"
                f"  interval:30m\n"
                f"  once:2026-03-20 15:00"
            )

        try:
            wf_id = db.workflow_create(
                name=name,
                steps=steps,
                schedule=schedule,
                description=f"{len(steps_list)} 个步骤, 调度: {schedule}",
                notify_qq=notify_qq,
                notify_group_id=notify_group_id,
                next_run=next_run.strftime("%Y-%m-%d %H:%M:%S"),
            )
        except Exception as e:
            return f"创建失败: {e}"

        step_names = [s.get("tool", "?") for s in steps_list]
        return (
            f"工作流已创建！\n"
            f"  ID: {wf_id}\n"
            f"  名称: {name}\n"
            f"  步骤: {' → '.join(step_names)}\n"
            f"  调度: {schedule}\n"
            f"  首次执行: {next_run.strftime('%Y-%m-%d %H:%M')}\n"
            f"  通知: {'QQ:' + notify_qq if notify_qq else '无'}"
            f"{' 群:' + notify_group_id if notify_group_id else ''}"
        )

    def _list_workflows(self) -> str:
        try:
            workflows = db.workflow_list()
        except Exception as e:
            return f"查询失败: {e}"

        if not workflows:
            return "暂无工作流。"

        lines = [f"共 {len(workflows)} 个工作流:"]
        for wf in workflows:
            status = "✅ 启用" if wf["enabled"] else "⏸ 禁用"
            next_run = wf.get("next_run")
            if next_run:
                if isinstance(next_run, datetime.datetime):
                    next_str = next_run.strftime("%m-%d %H:%M")
                else:
                    next_str = str(next_run)[:16]
            else:
                next_str = "无"

            lines.append(
                f"\n[{wf['id']}] {wf['name']}  {status}\n"
                f"    调度: {wf['schedule']}  下次: {next_str}  已执行: {wf['run_count']}次"
            )
        return "\n".join(lines)

    def _toggle_workflow(self, workflow_id: int, enabled: bool) -> str:
        try:
            ok = db.workflow_toggle(workflow_id, enabled)
        except Exception as e:
            return f"操作失败: {e}"

        if not ok:
            return f"未找到 ID 为 {workflow_id} 的工作流。"

        if enabled:
            # 重新计算 next_run
            wf = db.workflow_get(workflow_id)
            if wf:
                next_run = calc_next_run(wf["schedule"])
                if next_run:
                    db.workflow_update_after_run(
                        workflow_id,
                        next_run=next_run.strftime("%Y-%m-%d %H:%M:%S"),
                        last_result=wf.get("last_result", ""),
                    )

        action = "启用" if enabled else "禁用"
        return f"工作流 {workflow_id} 已{action}。"

    def _delete_workflow(self, workflow_id: int) -> str:
        try:
            ok = db.workflow_delete(workflow_id)
        except Exception as e:
            return f"删除失败: {e}"
        if not ok:
            return f"未找到 ID 为 {workflow_id} 的工作流。"
        return f"工作流 {workflow_id} 已删除。"

    def _run_now(self, workflow_id: int) -> str:
        try:
            wf = db.workflow_get(workflow_id)
        except Exception as e:
            return f"查询失败: {e}"
        if not wf:
            return f"未找到 ID 为 {workflow_id} 的工作流。"

        steps_raw = wf["steps"]
        steps, error = parse_workflow_steps(steps_raw)
        if error:
            return f"工作流步骤解析失败: {error}"

        results = execute_workflow_steps(
            steps,
            workflow_id=workflow_id,
            workflow_name=wf["name"],
            session_context={
                "user_qq": str(wf.get("notify_qq", "")).strip(),
                "group_id": str(wf.get("notify_group_id", "")).strip(),
            },
        )
        return format_workflow_result(wf["name"], results)

    def _describe_workflow(self, workflow_id: int) -> str:
        try:
            wf = db.workflow_get(workflow_id)
        except Exception as e:
            return f"查询失败: {e}"
        if not wf:
            return f"未找到 ID 为 {workflow_id} 的工作流。"

        steps, error = parse_workflow_steps(wf.get("steps", "[]"))
        if error:
            return f"工作流步骤解析失败: {error}"

        next_run = wf.get("next_run")
        if isinstance(next_run, datetime.datetime):
            next_run_text = next_run.strftime("%Y-%m-%d %H:%M")
        else:
            next_run_text = str(next_run)[:16] if next_run else "无"
        last_run = wf.get("last_run")
        if isinstance(last_run, datetime.datetime):
            last_run_text = last_run.strftime("%Y-%m-%d %H:%M")
        else:
            last_run_text = str(last_run)[:16] if last_run else "无"

        lines = [
            f"工作流详情 #{workflow_id}",
            f"名称: {wf['name']}",
            f"状态: {'启用' if wf.get('enabled') else '禁用'}",
            f"调度: {wf.get('schedule', '')}",
            f"下次执行: {next_run_text}",
            f"上次执行: {last_run_text}",
            f"通知: {'QQ:' + str(wf.get('notify_qq', '')) if wf.get('notify_qq') else '无'}"
            f"{' 群:' + str(wf.get('notify_group_id', '')) if wf.get('notify_group_id') else ''}",
            "步骤:",
        ]
        for idx, step in enumerate(steps or [], 1):
            lines.append(f"  {idx}. {step.get('tool')}({step.get('args', {})})")
        last_result = str(wf.get("last_result", "")).strip()
        if last_result:
            lines.append("最近结果:")
            lines.append(last_result[:500] + ("..." if len(last_result) > 500 else ""))
        return "\n".join(lines)

    def _clone_workflow(
        self,
        workflow_id: int,
        new_name: str = "",
        new_schedule: str = "",
        notify_qq: str = "",
        notify_group_id: str = "",
    ) -> str:
        try:
            wf = db.workflow_get(workflow_id)
        except Exception as e:
            return f"查询失败: {e}"
        if not wf:
            return f"未找到 ID 为 {workflow_id} 的工作流。"

        schedule = new_schedule.strip() or str(wf.get("schedule", "")).strip()
        next_run = calc_next_run(schedule)
        if next_run is None:
            return f"无法解析调度规则 '{schedule}'。"

        cloned_name = new_name.strip() or f"{wf['name']}-副本"
        qq = notify_qq.strip() or str(wf.get("notify_qq", "")).strip()
        group_id = notify_group_id.strip() or str(wf.get("notify_group_id", "")).strip()
        try:
            new_id = db.workflow_create(
                name=cloned_name,
                steps=wf["steps"],
                schedule=schedule,
                description=str(wf.get("description", "")),
                notify_qq=qq,
                notify_group_id=group_id,
                next_run=next_run.strftime("%Y-%m-%d %H:%M:%S"),
            )
        except Exception as e:
            return f"克隆失败: {e}"

        return (
            f"工作流已克隆！\n"
            f"  来源ID: {workflow_id}\n"
            f"  新ID: {new_id}\n"
            f"  名称: {cloned_name}\n"
            f"  调度: {schedule}\n"
            f"  首次执行: {next_run.strftime('%Y-%m-%d %H:%M')}"
        )

    def _parse_create_workflow_result(self, args: dict, result: str) -> dict | None:
        workflow_id = None
        next_run = ""
        id_match = re.search(r"ID:\s*(\d+)", result)
        if id_match:
            workflow_id = int(id_match.group(1))
        next_match = re.search(r"首次执行:\s*([0-9\-:\s]+)", result)
        if next_match:
            next_run = next_match.group(1).strip()
        steps, _ = parse_workflow_steps(args.get("steps", "[]"))
        return {
            "action": "create_workflow",
            "id": workflow_id,
            "name": str(args.get("name", "")).strip(),
            "schedule": str(args.get("schedule", "")).strip(),
            "notify_qq": str(args.get("notify_qq", "")).strip(),
            "notify_group_id": str(args.get("notify_group_id", "")).strip(),
            "step_count": len(steps or []),
            "steps": steps or [],
            "next_run": next_run,
        }

    def _parse_list_workflows_result(self, args: dict, result: str) -> dict | None:
        workflows = []
        current = None
        for raw_line in result.splitlines():
            line = raw_line.rstrip()
            head_match = re.match(r"^\[(\d+)\]\s+(.+?)\s+(✅ 启用|⏸ 禁用)$", line.strip())
            if head_match:
                current = {
                    "id": int(head_match.group(1)),
                    "name": head_match.group(2).strip(),
                    "enabled": head_match.group(3) == "✅ 启用",
                }
                workflows.append(current)
                continue
            detail_match = re.match(r"^调度:\s+(.+?)\s+下次:\s+(.+?)\s+已执行:\s+(\d+)次$", line.strip())
            if current and detail_match:
                current["schedule"] = detail_match.group(1).strip()
                current["next_run"] = detail_match.group(2).strip()
                current["run_count"] = int(detail_match.group(3))
        return {"action": "list_workflows", "workflows": workflows}

    def _parse_toggle_workflow_result(self, args: dict, result: str) -> dict | None:
        return {
            "action": "toggle_workflow",
            "workflow_id": args.get("workflow_id"),
            "enabled": args.get("enabled"),
            "updated": "已启用" in result or "已禁用" in result,
        }

    def _parse_delete_workflow_result(self, args: dict, result: str) -> dict | None:
        return {
            "action": "delete_workflow",
            "workflow_id": args.get("workflow_id"),
            "deleted": "已删除" in result,
        }

    def _parse_run_workflow_result(self, args: dict, result: str) -> dict | None:
        name = ""
        name_match = re.search(r"^\[工作流\]\s+(.+?)\s+执行完成$", result.splitlines()[0].strip()) if result.strip() else None
        if name_match:
            name = name_match.group(1).strip()
        return {
            "action": "run_workflow_now",
            "workflow_id": args.get("workflow_id"),
            "name": name,
            "result": result[:500],
        }

    def _parse_describe_workflow_result(self, args: dict, result: str) -> dict | None:
        return {
            "action": "describe_workflow",
            "workflow_id": args.get("workflow_id"),
            "result": result[:500],
        }

    def _parse_clone_workflow_result(self, args: dict, result: str) -> dict | None:
        source_match = re.search(r"来源ID:\s*(\d+)", result)
        new_match = re.search(r"新ID:\s*(\d+)", result)
        return {
            "action": "clone_workflow",
            "source_workflow_id": int(source_match.group(1)) if source_match else args.get("workflow_id"),
            "workflow_id": int(new_match.group(1)) if new_match else None,
            "name": str(args.get("new_name", "")).strip(),
        }


register(WorkflowSkill)
