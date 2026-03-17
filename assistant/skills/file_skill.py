"""文件系统操作 Skill"""

from pathlib import Path
from assistant.skills.base import BaseSkill, ToolDefinition, register


class FileSkill(BaseSkill):
    name = "file"
    description = "本地文件读取和目录浏览"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="read_file",
                description="读取本地文件内容。支持文本文件。",
                parameters={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件绝对路径或相对路径"},
                    },
                    "required": ["file_path"],
                },
                handler=self._read_file,
            ),
            ToolDefinition(
                name="list_directory",
                description="列出目录下的文件和文件夹。",
                parameters={
                    "type": "object",
                    "properties": {
                        "dir_path": {"type": "string", "description": "目录路径", "default": "."},
                    },
                },
                handler=self._list_directory,
            ),
        ]

    def _read_file(self, file_path: str) -> str:
        path = Path(file_path).expanduser()
        if not path.exists():
            return f"文件不存在: {file_path}"
        if not path.is_file():
            return f"不是文件: {file_path}"
        try:
            content = path.read_text(encoding="utf-8")
            if len(content) > 5000:
                content = content[:5000] + f"\n\n... (已截取前5000字符，总长: {len(content)})"
            return content
        except Exception as e:
            return f"读取失败: {e}"

    def _list_directory(self, dir_path: str = ".") -> str:
        path = Path(dir_path).expanduser()
        if not path.exists():
            return f"目录不存在: {dir_path}"
        if not path.is_dir():
            return f"不是目录: {dir_path}"
        items = sorted(path.iterdir())
        lines = []
        for item in items[:50]:
            prefix = "[DIR]" if item.is_dir() else "[FILE]"
            lines.append(f"  {prefix} {item.name}")
        if len(items) > 50:
            lines.append(f"  ... 还有 {len(items) - 50} 项")
        return "\n".join(lines) if lines else "空目录"


register(FileSkill)
