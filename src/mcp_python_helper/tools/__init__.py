from typing import Dict, Any, Callable, Awaitable, List
import mcp.types as types
from . import edit_python_code

# Type for tool handler functions
ToolHandler = Callable[
    [Dict[str, Any]], 
    Awaitable[List[types.TextContent | types.ImageContent | types.EmbeddedResource]]
]

# Map of tool names to their handler functions
TOOL_HANDLERS: Dict[str, ToolHandler] = {
    "edit-python-code": edit_python_code.handle_tool,
}

# List of all available tools
TOOLS = [
    edit_python_code.get_tool_definition(),
]

async def get_tools() -> List[types.Tool]:
    return TOOLS

async def call_tool(name: str, arguments: Dict[str, Any] | None) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name not in TOOL_HANDLERS:
        raise ValueError(f"Unknown tool: {name}")

    if not arguments:
        raise ValueError("Missing arguments")

    return await TOOL_HANDLERS[name](arguments)