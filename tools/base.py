"""工具抽象基类与注册中心。

Tool ABC：所有具体工具必须实现 execute()，并提供 name/description/parameters。
TerminalOutputTool：继承 Tool，terminal=True 固定，各项目实现自己的输出格式。
ToolRegistry：管理工具注册、配额追踪、生成 OpenAI function calling 格式的工具定义。
"""
import json
from abc import ABC, abstractmethod
from typing import Any, Callable


class Tool(ABC):
    """工具抽象基类。"""

    # 工具名称（snake_case）
    name: str = ''
    # 工具描述（LLM 看到的内容）
    description: str = ''
    # JSON Schema 格式的参数定义
    parameters: dict = {}
    # 全局最大调用次数（None = 无限制）
    max_calls: int | None = None
    # 是否为终结工具（设为 True 后，Orchestrator 执行后立即结束循环）
    terminal: bool = False

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """执行工具逻辑，返回可 JSON 序列化的结果。"""
        ...

    def to_openai_tool(self) -> dict:
        """转换为 OpenAI function calling 格式。"""
        return {
            'type': 'function',
            'function': {
                'name': self.name,
                'description': self.description,
                'parameters': self.parameters,
            },
        }


class TerminalOutputTool(Tool):
    """终结输出工具接口。

    各项目必须继承此类，实现自己的输出格式。
    terminal 固定为 True，Orchestrator 通过此标记自动识别。
    """
    terminal = True

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """执行后 Orchestrator 立即结束循环，返回该 dict。"""
        ...


class ToolRegistry:
    """工具注册中心，维护工具列表与调用配额。"""

    def __init__(self, on_tool_call: Callable[[str], None] | None = None):
        self._tools: dict[str, Tool] = {}
        self._usage: dict[str, int] = {}
        self._on_tool_call = on_tool_call

    def register(self, tool: Tool):
        """注册一个工具实例。"""
        if not tool.name:
            raise ValueError(f'Tool {type(tool).__name__} has empty name')
        self._tools[tool.name] = tool
        self._usage[tool.name] = 0
        tool._registry = self  # type: ignore[attr-defined]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    @property
    def all_tools(self) -> list[Tool]:
        return list(self._tools.values())

    @property
    def terminal_tool_name(self) -> str | None:
        """返回第一个被标记为 terminal 的工具名。"""
        for name, tool in self._tools.items():
            if tool.terminal:
                return name
        return None

    # ── 配额管理 ──

    def increment(self, name: str):
        """增加工具的调用计数（运行时 + 可选持久化）。"""
        if name in self._usage:
            self._usage[name] += 1
        if self._on_tool_call:
            self._on_tool_call(name)

    def usage_count(self, name: str) -> int:
        """获取工具已调用次数。"""
        return self._usage.get(name, 0)

    def is_exhausted(self, name: str) -> bool:
        """检查工具配额是否已耗尽。"""
        tool = self._tools.get(name)
        if tool is None or tool.max_calls is None:
            return False
        return self._usage.get(name, 0) >= tool.max_calls

    def exhausted_tool_names(self) -> set[str]:
        """返回所有配额已耗尽的工具名称集合。"""
        return {name for name in self._tools if self.is_exhausted(name)}

    # ── OpenAI 格式生成 ──

    def get_openai_tool_defs(self) -> list[dict]:
        """生成 OpenAI function calling 格式的工具列表（排除配额耗尽项）。

        terminal 工具始终可用。
        """
        exhausted = self.exhausted_tool_names()
        terminal_names = {name for name, t in self._tools.items() if t.terminal}
        return [
            tool.to_openai_tool()
            for name, tool in self._tools.items()
            if name not in (exhausted - terminal_names)
        ]

    def get_openai_tool_defs_all(self) -> list[dict]:
        """生成所有工具定义，常用于主循环末尾强制提交。"""
        return [tool.to_openai_tool() for tool in self._tools.values()]

    def execute(self, name: str, arguments: str | dict) -> Any:
        """执行工具并返回结果。"""
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f'Unknown tool: {name}')

        if isinstance(arguments, str):
            kwargs = json.loads(arguments)
        else:
            kwargs = arguments

        return tool.execute(**kwargs)
