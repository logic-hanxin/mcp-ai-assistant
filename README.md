# 私人AI助手 (MCP + DeepSeek Agent)

基于 MCP 协议的高级私人 AI 助手，集成 DeepSeek 大模型，具备任务规划、自我反思和长期记忆能力。

## 架构

```
用户输入
  │
  ▼
┌─────────────────────────────────────────┐
│  Agent Core                             │
│  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │ Planner  │  │ Memory   │  │Reflect │ │
│  │ 任务规划  │  │ 长期记忆  │  │自我反思 │ │
│  └────┬─────┘  └────┬─────┘  └───┬────┘ │
│       └──────┬──────┘            │      │
│              ▼                   │      │
│        ReAct Loop ◄──────────────┘      │
│         (Reason → Act → Observe)        │
└───────────────┬─────────────────────────┘
                │ MCP Protocol (stdio)
                ▼
┌─────────────────────────────────────────┐
│  MCP Server (自动发现 Skills)            │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌────────┐  │
│  │ Time │ │Weather│ │ Note │ │File    │  │
│  │Skill │ │Skill  │ │Skill │ │Skill   │  │
│  └──────┘ └──────┘ └──────┘ └────────┘  │
└─────────────────────────────────────────┘
```

## Agent 能力

| 能力 | 说明 |
|------|------|
| **任务规划 (Planner)** | 复杂请求自动分解为多步计划，逐步执行 |
| **自我反思 (Reflection)** | 工具调用失败时分析原因，决定重试/换策略/放弃 |
| **长期记忆 (Memory)** | 会话内对话自动压缩，跨会话持久化，支持用户偏好存储 |
| **可插拔 Skills** | 添加新功能只需创建 `xxx_skill.py`，Server 自动发现 |

## 内置 Skills

| Skill | 工具 | 说明 |
|-------|------|------|
| Time | `get_current_time` | 多时区时间查询 |
| Weather | `get_weather` | 天气查询（可替换为真实API） |
| Note | `take_note`, `list_notes`, `search_notes`, `delete_note` | 笔记 CRUD |
| Calculator | `calculate` | 安全数学计算 |
| File | `read_file`, `list_directory` | 本地文件操作 |

## 快速开始

### 1. 安装依赖

```bash
pip install mcp openai python-dotenv httpx
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY（从 platform.deepseek.com 获取）
```

### 3. 运行

```bash
python -m assistant.main
```

## 交互命令

| 命令 | 说明 |
|------|------|
| `/tools` | 查看可用工具 |
| `/skills` | 查看已加载 Skills |
| `/fact K V` | 保存个人信息（如 `/fact 名字 小明`） |
| `/facts` | 查看已保存的个人信息 |
| `/clear` | 清空对话（自动保存到长期记忆） |
| `/help` | 显示帮助 |
| `/quit` | 退出 |

## 使用示例

```
你: 帮我查一下上海天气，然后记到笔记里
  [规划] 创建了 2 步计划:
    ⬜ Step 1: 查询上海天气
    ⬜ Step 2: 将天气信息保存为笔记
  [执行] Step 1: 查询上海天气
    [工具] get_weather({"city": "上海"})
  [完成] Step 1
  [执行] Step 2: 将天气信息保存为笔记
    [工具] take_note({"title": "上海天气", "content": "..."})
  [完成] Step 2

助手: 已查到上海天气并记录到笔记。当前上海多云，25°C，湿度 65%。笔记 ID: 1。

你: /fact 名字 小明
已保存: 名字 = 小明

你: 你知道我叫什么吗？
助手: 你好小明！有什么可以帮你的吗？
```

## 添加自定义 Skill

在 `assistant/skills/` 下新建文件，如 `translate_skill.py`:

```python
from assistant.skills.base import BaseSkill, ToolDefinition, register

class TranslateSkill(BaseSkill):
    name = "translate"
    description = "文本翻译"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="translate_text",
                description="将文本翻译为指定语言",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "要翻译的文本"},
                        "target_lang": {"type": "string", "description": "目标语言"},
                    },
                    "required": ["text", "target_lang"],
                },
                handler=self._translate,
            ),
        ]

    def _translate(self, text: str, target_lang: str) -> str:
        # 实现翻译逻辑
        return f"[翻译结果] ..."

register(TranslateSkill)
```

重启助手即可自动加载新 Skill，无需修改其他文件。

## 项目结构

```
├── .env.example           # 环境变量模板
├── pyproject.toml          # 依赖配置
├── README.md
└── assistant/
    ├── __init__.py
    ├── config.py            # 配置管理
    ├── main.py              # 启动入口
    ├── agent/               # Agent 核心
    │   ├── core.py          # Agent 主循环 (Planner + ReAct + Reflection)
    │   ├── planner.py       # 任务规划器
    │   ├── memory.py        # 长期记忆
    │   └── reflection.py    # 自我反思
    ├── mcp/                 # MCP 通信层
    │   ├── server.py        # MCP Server (自动加载 Skills)
    │   └── client.py        # MCP Client
    ├── skills/              # 可插拔技能模块
    │   ├── base.py          # Skill 基类 + 自动发现
    │   ├── time_skill.py
    │   ├── weather_skill.py
    │   ├── note_skill.py
    │   ├── calc_skill.py
    │   └── file_skill.py
    └── llm/
        └── deepseek.py      # DeepSeek 配置
```
