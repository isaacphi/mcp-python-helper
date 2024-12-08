import logging

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

from .ast_tools import modify_source

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

server = Server("mcp-python-helper")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="edit-python-code",
            description="Edit Python code by inserting or replacing code at a specified location",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Full path to the Python file to edit",
                    },
                    "code": {
                        "type": "string",
                        "description": "Valid Python code to insert",
                    },
                    "target": {
                        "type": "string",
                        "description": "Symbol name or full line of code to target. E.g., 'var = 3', 'my_function', 'MyClass.my_method', 'MY_CONSTANT'",
                    },
                    "position": {
                        "type": "string",
                        "enum": ["before", "after", "replace"],
                        "description": "Where to insert the code relative to the target",
                    },
                },
                "required": ["filename", "code", "target", "position"],
            },
        )
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name != "edit-python-code":
        raise ValueError(f"Unknown tool: {name}")

    if not arguments:
        raise ValueError("Missing arguments")

    filename = arguments.get("filename")
    code = arguments.get("code")
    target = arguments.get("target")
    position = arguments.get("position")

    if not all([filename, code, target, position]):
        raise ValueError("Missing required arguments")

    try:
        with open(filename, "r") as f:
            source = f.read()

        modified_source = modify_source(source, code, target, position)

        with open(filename, "w") as f:
            f.write(modified_source)

        return [
            types.TextContent(
                type="text",
                text=f"Successfully modified {filename} - {position} {target}",
            )
        ]
    except Exception as e:
        logger.error(f"Error in handle_call_tool: {e}")
        return [types.TextContent(type="text", text=f"Error modifying code: {str(e)}")]


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-python-helper",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
