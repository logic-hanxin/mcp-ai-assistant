# 私人 AI 助手

基于 `MCP + DeepSeek/OpenAI Compatible LLM + Skills` 的可扩展 Agent 平台。  
它不只是“能调工具的聊天机器人”，而是一套带有路由、规划、黑板共享上下文、执行治理、工作流调度和多接入形态的运行时。

## 当前特性

- `Router + Planner + Reflection + Memory` 组成主 Agent 链路
- `Blackboard` 作为共享上下文总线，支持多步任务和跨工具参数复用
- `tool_hydrators / tool_policies / tool_adapters` 负责补参、执行前治理、执行后结构化写板
- MCP Server 自动发现并注册所有 skills
- MCP Client 支持“文本结果 + 结构化 side channel”
- 支持 CLI、Web API、OneBot/QQ 机器人接入
- 支持提醒、网站监控、GitHub 监控、热点新闻、自动化工作流后台循环
- 数据层已按领域拆分为 `db_memory / db_workflow / db_knowledge / db_contacts / db_misc`

## 运行架构

```text
用户输入
  │
  ▼
AgentCore.chat()
  │
  ├─ Memory: 记录用户消息 / 长短期记忆
  ├─ Router: 意图路由 (chat/query/task/code/general)
  ├─ Planner: 判断是否需要多步计划
  │
  ├─ [简单任务] ReAct Loop
  │      ├─ tool_hydrators: 补全缺失参数
  │      ├─ tool_policies: 执行前校验/拦截
  │      ├─ MCP Client -> MCP Server -> Skill Handler
  │      ├─ result_parser / structured result
  │      ├─ tool_adapters: 写入黑板实体
  │      ├─ Blackboard: 最近结果/实体/共享变量
  │      └─ Reflection: 评估结果，决定是否重试
  │
  └─ [复杂任务] Plan 执行
         └─ 每一步同样复用 hydrator / policy / adapter / blackboard
```

## Blackboard 模式

黑板现在不只是“存一点上下文”，而是运行时的一部分：

- 存共享变量：最近城市、最近仓库、最近结果、最近联系人等
- 存结构化实体：`contact / github_repo / note / reminder / workflow / database_query / news_digest ...`
- 给后续工具补参：例如 `send_qq_message` 自动补最近联系人 QQ
- 给工作流复用：工作流步骤现在也使用同一套 runtime

## 内置能力

### 基础查询

- `get_current_time`：时间查询
- `get_weather`：天气查询
- `translate_text`：翻译
- `calculate`：数学计算
- `read_file` / `list_directory`：文件读取和目录浏览
- `ocr_image` / `understand_image` / `scan_qrcode`：图片识别
- `ip_location` / `phone_area`：定位与归属地查询
- `search_music` / `music_hot_list`：音乐搜索和榜单
- `query_express`：快递查询
- `query_hero_power` / `search_hero`：王者荣耀战力查询

### 信息检索

- `web_search`：网页搜索
- `browse_page` / `browse_with_headers` / `post_form` / `get_json`：网页/API 抓取
- `get_hot_news` / `send_news_to_qq`：热点新闻
- `github_trending` / `hacker_news_top` / `qa_tech_recommend`：技术资讯
- `add_knowledge` / `search_knowledge` / `list_knowledge_docs` / `delete_knowledge_doc`：知识库
- `import_document` / `parse_document`：文档解析与导入
- `list_tables` / `get_table_schema` / `query_database`：数据库查询

### 通讯与协作

- `set_user_name` / `get_user_name` / `list_contacts` / `find_qq_by_name`：通讯录
- `send_qq_message` / `send_qq_group_message`：QQ 消息
- `notify_contact_by_name` / `notify_group_by_name` / `broadcast_last_result`
- `notify_recent_contact` / `broadcast_workflow_result`

### 任务与自动化

- `take_note` / `list_notes` / `search_notes` / `delete_note`
- `append_note` / `summarize_notes`
- `create_reminder` / `list_reminders` / `delete_reminder`
- `add_rule` / `list_rules` / `delete_rule`
- `add_site_monitor` / `remove_site_monitor` / `list_site_monitors` / `check_site_now`
- `github_watch_repo` / `github_unwatch_repo` / `github_list_watched`
- `github_get_latest_commits` / `github_get_branches`
- `github_get_repo_overview` / `github_list_pull_requests` / `github_list_issues`
- `create_workflow` / `list_workflows` / `toggle_workflow` / `delete_workflow`
- `run_workflow_now` / `describe_workflow` / `clone_workflow`

### 代码辅助

- `run_cpp_code`：编译并运行 C++
- `get_leetcode_problem`：LeetCode 刷题辅助

## 工作流运行时

工作流现在已经接入统一 runtime，而不是旁路执行：

- 步骤执行前走 `tool_hydrators`
- 缺失参数会从工作流上下文和黑板自动补全
- 执行前走 `tool_policies`
- 执行后走 `result_parser + tool_adapters`
- 每个工作流使用独立黑板作用域：`workflow:<id>`

这意味着工作流也能稳定复用前一步结果，例如：

1. `find_qq_by_name`
2. `send_qq_message`

第二步即使不显式填 `qq_number`，也可以从第一步写入的联系人实体里补出来。

## 项目结构

```text
.
├── README.md
├── pyproject.toml
├── .env.example
└── assistant/
    ├── config.py
    ├── main.py
    ├── runtime_context.py
    ├── agent/
    │   ├── core.py
    │   ├── router.py
    │   ├── planner.py
    │   ├── reflection.py
    │   ├── memory.py
    │   ├── blackboard.py
    │   ├── tool_hydrators.py
    │   ├── tool_policies.py
    │   ├── tool_adapters.py
    │   ├── workflow_runner.py
    │   ├── reminder_checker.py
    │   ├── github_checker.py
    │   ├── news_checker.py
    │   ├── site_checker.py
    │   ├── rag.py
    │   ├── db.py
    │   ├── db_core.py
    │   ├── db_memory.py
    │   ├── db_contacts.py
    │   ├── db_knowledge.py
    │   ├── db_workflow.py
    │   └── db_misc.py
    ├── mcp/
    │   ├── client.py
    │   └── server.py
    ├── skills/
    │   ├── base.py
    │   ├── time_skill.py
    │   ├── weather_skill.py
    │   ├── translate_skill.py
    │   ├── calc_skill.py
    │   ├── file_skill.py
    │   ├── search_skill.py
    │   ├── browser_skill.py
    │   ├── note_skill.py
    │   ├── reminder_skill.py
    │   ├── contacts_skill.py
    │   ├── qq_skill.py
    │   ├── group_ops_skill.py
    │   ├── github_skill.py
    │   ├── monitor_skill.py
    │   ├── workflow_skill.py
    │   ├── knowledge_skill.py
    │   ├── document_skill.py
    │   ├── sql_skill.py
    │   ├── news_skill.py
    │   ├── music_skill.py
    │   ├── express_skill.py
    │   ├── location_skill.py
    │   ├── techtrend_skill.py
    │   ├── rule_skill.py
    │   ├── code_skill.py
    │   ├── vision_skill.py
    │   └── wzry_skill.py
    ├── web/
    │   ├── api.py
    │   ├── onebot.py
    │   └── run.py
    └── llm/
        └── deepseek.py
```

## 快速开始

### 1. 安装依赖

```bash
pip install -e .
```

项目基础依赖由 [pyproject.toml](/Users/hanxin/Documents/New%20project/mcp-ai-assistant/pyproject.toml) 管理，已包含：

- `mcp`
- `openai`
- `python-dotenv`
- `httpx`
- `fastapi`
- `uvicorn`
- `pymysql`

如果你要启用更多增强能力，通常还会需要额外安装：

```bash
pip install requests beautifulsoup4 pypdf python-docx pillow opencv-python
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

常见配置包括：

- `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `MODEL`
- `DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME`
- `NAPCAT_API_URL`
- `QQ_ADMIN / RULE_ADMIN_QQ`
- `GITHUB_TOKEN`

### 3. 运行方式

CLI:

```bash
python -m assistant.main
# 或
ai-assistant
```

Web / QQ Bot:

```bash
python -m assistant.web.run
# 或
ai-assistant-qq
```

## CLI 命令

| 命令 | 说明 |
|------|------|
| `/tools` | 查看可用工具 |
| `/skills` | 查看已加载 Skills |
| `/fact K V` | 保存用户事实 |
| `/facts` | 查看用户事实 |
| `/clear` | 清空当前对话并保存长期记忆 |
| `/help` | 查看帮助 |
| `/quit` | 退出 |

## 测试

当前仓库已经补了一批围绕 runtime 的单元测试，覆盖了：

- planner / router metadata
- blackboard 集成
- tool hydrators / policies / adapters
- MCP 结构化结果编解码
- workflow runtime
- 一部分 skill 增强功能

运行方式：

```bash
python3.11 -m unittest discover -s tests -v
```

## 扩展自定义 Skill

新增 skill 推荐至少实现这几层：

- `metadata`：供 router / planner / policy 使用
- `keywords / intents`：供意图匹配使用
- `result_parser`：供 MCP structured result 和 adapter 使用

示例：

```python
from assistant.skills.base import BaseSkill, ToolDefinition, register


class DemoSkill(BaseSkill):
    name = "demo"
    description = "示例技能"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="demo_tool",
                description="执行一个示例动作",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "输入文本"},
                    },
                    "required": ["text"],
                },
                handler=self._demo_tool,
                metadata={
                    "category": "read",
                    "required_all": ["text"],
                },
                keywords=["示例", "测试工具"],
                intents=["demo_tool"],
                result_parser=self._parse_demo_result,
            ),
        ]

    def _demo_tool(self, text: str) -> str:
        return f"收到: {text}"

    def _parse_demo_result(self, args: dict, result: str) -> dict | None:
        return {
            "text": args.get("text", ""),
            "result": result,
        }


register(DemoSkill)
```

重启后，MCP Server 会自动发现并注册新工具。

如果你要让新工具完整接入当前 runtime，推荐同时补两层：

- 在 `metadata` 里声明 `category / side_effect / required_all / required_any / session_required`
- 在 `result_parser` 里直接返回结构化对象，减少 adapter 对文本格式的依赖

## 当前代码状态说明

当前仓库已经不再是 README 早期版本里的“轻量 demo”。  
它现在更接近一个可演进的 Agent runtime：

- skill 协议化
- 路由与规划 metadata-aware
- 结构化工具结果
- 黑板共享上下文
- 工作流复用统一运行时
- 多接入形态
- 覆盖到较多单元测试

如果你准备继续演进，最推荐的下一步通常是：

- 增强更多 skill 的结构化解析和 adapter
- 增强可观测性/trace
- 给 README 补部署说明和 Web/QQ 接入说明
