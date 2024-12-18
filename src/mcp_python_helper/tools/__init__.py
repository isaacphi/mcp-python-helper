from typing import Any

import mcp.types as types

from .edit_python_code import EditPythonTool
from .locate_symbol import LocateSymbolTool

TOOLS = [
    EditPythonTool(),
    LocateSymbolTool(),
]


def get_tools() -> list[types.Tool]:
    return [tool.get_definition() for tool in TOOLS]


async def handle_tool_call(name: str, arguments: dict[str, Any] | None):
    for tool in TOOLS:
        if tool.name == name:
            if not arguments:
                raise ValueError("Missing arguments")
            args = tool.arg_type(**arguments)  # type: ignore
            return await tool.execute(args)
    raise ValueError(f"Unknown tool: {name}")
