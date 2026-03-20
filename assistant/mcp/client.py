"""
MCP Client - 连接 MCP Server，提供工具调用能力
"""

import sys
from dataclasses import dataclass
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from assistant.skills.base import decode_tool_result


@dataclass
class ToolCallResult:
    text: str
    structured: dict | None = None


class MCPClient:
    """MCP 客户端，负责与 Server 通信"""

    def __init__(self):
        self.session: ClientSession | None = None
        self.tools: list[dict] = []  # OpenAI function calling 格式
        self._tool_names: list[str] = []

    async def connect(self, server_script: str):
        """启动 MCP Server 子进程并建立连接"""
        server_params = StdioServerParameters(
            command=sys.executable,  # 使用当前 Python 解释器，确保虚拟环境一致
            args=[server_script],
        )
        self._stdio_ctx = stdio_client(server_params)
        transport = await self._stdio_ctx.__aenter__()
        self._read, self._write = transport

        self._session_ctx = ClientSession(self._read, self._write)
        self.session = await self._session_ctx.__aenter__()
        await self.session.initialize()

        # 发现工具
        result = await self.session.list_tools()
        self.tools = self._convert(result.tools)
        self._tool_names = [t["function"]["name"] for t in self.tools]

    def _convert(self, mcp_tools) -> list[dict]:
        """MCP 工具格式 -> OpenAI function calling 格式"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema or {"type": "object", "properties": {}},
                },
            }
            for t in mcp_tools
        ]

    async def call_tool_ex(self, name: str, args: dict) -> ToolCallResult:
        """通过 MCP 协议调用工具，并解析结构化 side channel。"""
        result = await self.session.call_tool(name, args)
        payload = result.content[0].text if result.content else ""
        decoded = decode_tool_result(payload)
        return ToolCallResult(text=decoded.text, structured=decoded.structured)

    async def call_tool(self, name: str, args: dict) -> str:
        """兼容旧接口，仅返回文本结果。"""
        return (await self.call_tool_ex(name, args)).text

    @property
    def tool_names(self) -> list[str]:
        return list(self._tool_names)

    async def close(self):
        if hasattr(self, "_session_ctx"):
            await self._session_ctx.__aexit__(None, None, None)
        if hasattr(self, "_stdio_ctx"):
            await self._stdio_ctx.__aexit__(None, None, None)
