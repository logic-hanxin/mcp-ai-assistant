"""
Skill 基类与自动发现机制

每个 Skill 是一个独立模块，包含:
- 名称和描述
- 一组工具 (tools)
- 可选的初始化/清理逻辑

新建 Skill 只需:
1. 在 skills/ 目录下创建 xxx_skill.py
2. 继承 BaseSkill 并实现 tools() 方法
3. 在模块末尾调用 register(YourSkill)
"""

from abc import ABC, abstractmethod
import base64
from dataclasses import dataclass, field
import json
from typing import Callable, Any
import importlib
import pkgutil
import pathlib


STRUCTURED_RESULT_MARKER = "__ASSISTANT_STRUCTURED_RESULT__:"


@dataclass
class ToolDefinition:
    """工具定义，描述一个可调用的工具"""
    name: str
    description: str
    parameters: dict  # JSON Schema 格式
    handler: Callable[..., str]  # 实际执行函数
    metadata: dict[str, Any] = field(default_factory=dict)
    result_parser: Callable[[dict, str], dict[str, Any] | None] | None = None
    keywords: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)


@dataclass
class DecodedToolResult:
    text: str
    structured: dict[str, Any] | None = None


def encode_tool_result(text: str, structured: dict[str, Any] | None = None) -> str:
    """把人类可读文本和结构化结果编码成单个字符串返回。"""
    text = text or ""
    if not structured:
        return text
    payload = json.dumps(structured, ensure_ascii=False, separators=(",", ":"))
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    return f"{text}\n{STRUCTURED_RESULT_MARKER}{encoded}"


def decode_tool_result(payload: str) -> DecodedToolResult:
    """从 MCP 文本结果中提取结构化 side channel。"""
    payload = payload or ""
    marker_index = payload.rfind(STRUCTURED_RESULT_MARKER)
    if marker_index < 0:
        return DecodedToolResult(text=payload)

    text = payload[:marker_index].rstrip()
    encoded = payload[marker_index + len(STRUCTURED_RESULT_MARKER):].strip()
    if not encoded:
        return DecodedToolResult(text=text)

    try:
        decoded = base64.b64decode(encoded.encode("ascii")).decode("utf-8")
        structured = json.loads(decoded)
    except Exception:
        return DecodedToolResult(text=payload)

    if not isinstance(structured, dict):
        return DecodedToolResult(text=text)
    return DecodedToolResult(text=text, structured=structured)


class BaseSkill(ABC):
    """Skill 基类，所有自定义 Skill 必须继承此类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Skill 名称"""

    @property
    @abstractmethod
    def description(self) -> str:
        """Skill 描述"""

    @abstractmethod
    def get_tools(self) -> list[ToolDefinition]:
        """返回该 Skill 提供的工具列表"""

    def on_load(self):
        """Skill 加载时的初始化逻辑（可选覆盖）"""

    def on_unload(self):
        """Skill 卸载时的清理逻辑（可选覆盖）"""


# ============================================================
# Skill 注册表
# ============================================================
_registry: list[type[BaseSkill]] = []


def register(skill_cls: type[BaseSkill]):
    """注册一个 Skill 类"""
    if skill_cls not in _registry:
        _registry.append(skill_cls)


def get_registered_skills() -> list[type[BaseSkill]]:
    """获取所有已注册的 Skill 类"""
    return list(_registry)


def discover_and_load_skills() -> list[BaseSkill]:
    """
    自动发现 skills/ 目录下所有 *_skill.py 模块，
    导入它们（触发 register 调用），然后实例化所有 Skill。
    """
    skills_dir = pathlib.Path(__file__).parent
    for module_info in pkgutil.iter_modules([str(skills_dir)]):
        if module_info.name.endswith("_skill"):
            importlib.import_module(f"assistant.skills.{module_info.name}")

    instances = []
    for cls in _registry:
        skill = cls()
        skill.on_load()
        instances.append(skill)
    return instances


def discover_tool_metadata() -> dict[str, dict]:
    """
    返回 {tool_name: metadata}，供路由/规划/黑板等模块使用。
    """
    metadata_index: dict[str, dict] = {}
    for skill in discover_and_load_skills():
        for tool in skill.get_tools():
            metadata_index[tool.name] = {
                "skill": skill.name,
                "description": tool.description,
                "keywords": list(tool.keywords),
                "intents": list(tool.intents),
                **tool.metadata,
            }
    return metadata_index


def discover_tool_definitions() -> dict[str, ToolDefinition]:
    """
    返回 {tool_name: ToolDefinition}，保留原始定义供执行治理层使用。
    """
    definitions: dict[str, ToolDefinition] = {}
    for skill in discover_and_load_skills():
        for tool in skill.get_tools():
            definitions[tool.name] = tool
    return definitions
