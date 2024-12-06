import asyncio
import ast
import astor
import textwrap
from typing import Literal, Union
import logging
from ast import dump

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

server = Server("mcp-python-helper")


class CodeLocator(ast.NodeVisitor):
    """Helper class to locate where to insert/replace code in the AST."""

    def __init__(self, target_name: str):
        self.target_name = target_name
        self.target_node = None
        self.containing_node = None  # The node that contains our target in its body
        self.target_index = None  # Index in the containing node's body
        logger.debug(f"CodeLocator initialized with target: {target_name}")

    def generic_visit(self, node):
        """Implement parent tracking for specific node types"""
        # Check if this node contains a body field
        if hasattr(node, "body"):
            logger.debug(f"Checking body of {type(node).__name__}")
            # Look for nodes that match our target
            for i, child in enumerate(node.body):
                if isinstance(child, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == self.target_name
                    for target in child.targets
                ):
                    logger.debug(f"Found target assignment in {type(node).__name__}")
                    self.target_node = child
                    self.containing_node = node
                    self.target_index = i
                    return
                elif (
                    isinstance(child, (ast.ClassDef, ast.FunctionDef))
                    and child.name == self.target_name
                ):
                    logger.debug(
                        f"Found target class/function in {type(node).__name__}"
                    )
                    self.target_node = child
                    self.containing_node = node
                    self.target_index = i
                    return

        # Continue searching
        for child in ast.iter_child_nodes(node):
            self.visit(child)


def modify_source(source_code: str, new_code: str, target: str, position: str) -> str:
    """Modify source code by inserting or replacing code at the specified location."""

    logger.debug(f"Modifying source code:")
    logger.debug(f"Target: {target}")
    logger.debug(f"Position: {position}")
    logger.debug(f"New code:\n{new_code}")

    # Parse the source code into an AST
    try:
        tree = ast.parse(source_code)
    except Exception as e:
        logger.error(f"Failed to parse source code: {e}")
        raise

    # Parse the new code
    try:
        new_node = ast.parse(textwrap.dedent(new_code))
    except Exception as e:
        logger.error(f"Failed to parse new code: {e}")
        raise

    # Find the target location
    locator = CodeLocator(target)
    locator.visit(tree)

    if not locator.target_node:
        logger.error(f"Could not find target '{target}' in the source code")
        raise ValueError(f"Could not find target '{target}' in the source code")

    if not locator.containing_node:
        logger.error("Failed to find containing node")
        raise ValueError("Failed to find containing node")

    logger.debug(f"Found target node: {type(locator.target_node).__name__}")
    logger.debug(f"In container: {type(locator.containing_node).__name__}")
    logger.debug(f"At index: {locator.target_index}")

    try:
        if position == "replace":
            logger.debug("Performing replacement")
            locator.containing_node.body[
                locator.target_index : locator.target_index + 1
            ] = new_node.body

        elif position == "before":
            logger.debug("Inserting before target")
            locator.containing_node.body[
                locator.target_index : locator.target_index
            ] = new_node.body

        elif position == "after":
            logger.debug("Inserting after target")
            locator.containing_node.body[
                locator.target_index + 1 : locator.target_index + 1
            ] = new_node.body

    except Exception as e:
        logger.error(f"Error during modification: {e}", exc_info=True)
        raise

    # Generate modified source code while preserving formatting
    try:
        modified_code = astor.to_source(tree)
        logger.debug(f"Modified code:\n{modified_code}")
        return modified_code
    except Exception as e:
        logger.error(f"Failed to generate modified source: {e}")
        raise


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        types.Tool(
            name="edit-code",
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
                        "description": "Name of the target function, class, or variable to locate",
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
    """
    Handle tool execution requests.
    Tools can modify server state and notify clients of changes.
    """
    if name != "edit-code":
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
        # Read the source file
        with open(filename, "r") as f:
            source = f.read()
            logger.debug(f"Original source code:\n{source}")

        # Modify the source code
        modified_source = modify_source(source, code, target, position)

        # Write the modified code back to the file
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
    # Run the server using stdin/stdout streams
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

