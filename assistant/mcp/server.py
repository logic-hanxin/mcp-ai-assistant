"""
MCP Server - 自动发现并加载所有 Skills

启动时扫描 skills/ 目录，将每个 Skill 的工具注册为 MCP tool。
新增 Skill 无需修改此文件。
"""

import sys
from pathlib import Path

# 将项目根目录加入 sys.path，确保作为子进程运行时也能找到 assistant 包
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# MCP Server 作为子进程运行，需要自行加载 .env
from dotenv import load_dotenv
load_dotenv()

from mcp.server.fastmcp import FastMCP
from assistant.skills.base import discover_and_load_skills, encode_tool_result

mcp = FastMCP("PrivateAssistant")


def _build_server():
    """发现所有 Skills 并注册其工具到 MCP Server"""
    skills = discover_and_load_skills()
    registered = []

    for skill in skills:
        for tool_def in skill.get_tools():
            # 动态注册工具到 FastMCP
            # FastMCP 的 @mcp.tool() 本质是注册 name -> handler 映射
            # 我们手动调用底层 API 实现动态注册
            _register_tool(tool_def)
            registered.append(f"{skill.name}/{tool_def.name}")

    print(f"[MCP Server] 已加载 {len(skills)} 个 Skills，注册 {len(registered)} 个工具:")
    for name in registered:
        print(f"  - {name}")


def _register_tool(tool_def):
    """将 ToolDefinition 注册为 MCP tool"""
    import inspect

    handler = tool_def.handler

    # 包装 handler，同时复制原始函数签名
    # FastMCP 通过 inspect.signature() 提取参数来生成 JSON Schema
    # 如果 wrapper 签名是 **kwargs，FastMCP 会生成错误的 schema
    def make_wrapper(h):
        def wrapper(**kwargs):
            result = h(**kwargs)
            if not isinstance(result, str):
                return result

            parser = getattr(tool_def, "result_parser", None)
            if not parser:
                return result
            try:
                structured = parser(kwargs, result)
            except Exception:
                structured = None
            return encode_tool_result(result, structured if isinstance(structured, dict) else None)
        # 关键：复制原始 handler 的签名，让 FastMCP 看到正确的参数定义
        wrapper.__signature__ = inspect.signature(h)
        wrapper.__name__ = tool_def.name
        wrapper.__doc__ = tool_def.description
        return wrapper

    wrapped = make_wrapper(handler)

    mcp._tool_manager.add_tool(
        fn=wrapped,
        name=tool_def.name,
        description=tool_def.description,
    )


_build_server()


if __name__ == "__main__":
    mcp.run(transport="stdio")
