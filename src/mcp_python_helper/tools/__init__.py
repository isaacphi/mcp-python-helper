from typing import List
import mcp.types as types
from .edit_python_code import EditPythonTool

# List of all available tools
TOOLS = [
    EditPythonTool(),
]


def get_tools() -> List[types.Tool]:
    return [tool.get_definition() for tool in TOOLS]


async def handle_tool_call(name: str, arguments: dict | None):
    for tool in TOOLS:
        if tool.name == name:
            return await tool.execute(arguments)
    raise ValueError(f"Unknown tool: {name}")
