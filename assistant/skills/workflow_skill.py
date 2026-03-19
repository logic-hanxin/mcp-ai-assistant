"""
工作流 Skill - 创建和管理自动化工作流

用户用自然语言描述自动化任务，LLM 将其转换为结构化的工作流定义。
工作流在后台按调度规则自动执行，结果通过 QQ 通知。

示例:
  "每天早上8点查北京天气然后发给我"
  "每周一三五9点获取热搜新闻发到群里"
  "每隔2小时检查一下GitHub仓库有没有新提交"
"""

import json
import datetime
from assistant.skills.base import BaseSkill, ToolDefinition, register
from assistant.agent import db
from assistant.agent.workflow_runner import calc_next_run, execute_workflow_steps, format_workflow_result


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
            ),
            ToolDefinition(
                name="list_workflows",
                description="列出所有工作流及其状态（启用/禁用、下次执行时间、执行次数等）。",
                parameters={"type": "object", "properties": {}},
                handler=self._list_workflows,
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
            ),
        ]

    def _create_workflow(self, name: str, steps: str, schedule: str,
                         notify_qq: str = "", notify_group_id: str = "") -> str:
        # 验证 steps JSON
        try:
            steps_list = json.loads(steps)
            if not isinstance(steps_list, list) or not steps_list:
                return "steps 必须是非空的 JSON 数组。"
            for s in steps_list:
                if "tool" not in s:
                    return f"每个步骤必须包含 tool 字段，错误步骤: {s}"
        except json.JSONDecodeError as e:
            return f"steps JSON 解析失败: {e}"

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
        if isinstance(steps_raw, str):
            try:
                steps = json.loads(steps_raw)
            except json.JSONDecodeError:
                return "工作流步骤解析失败。"
        else:
            steps = steps_raw

        results = execute_workflow_steps(steps)
        return format_workflow_result(wf["name"], results)


register(WorkflowSkill)
