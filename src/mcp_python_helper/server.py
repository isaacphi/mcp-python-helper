import logging
from typing import Dict, Any, List
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

from . import tools

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

server = Server("mcp-python-helper")


@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    return await tools.get_tools()


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: Dict[str, Any] | None
) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    return await tools.call_tool(name, arguments)


async def main() -> None:
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