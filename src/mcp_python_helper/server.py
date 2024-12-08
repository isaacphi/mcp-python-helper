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


def normalize_code(code: str) -> str:
    """Normalize code by removing indentation and extra whitespace"""
    lines = code.strip().split("\n")
    # Remove empty lines
    lines = [line.strip() for line in lines if line.strip()]
    return "\n".join(lines)


class CodeLocator(ast.NodeVisitor):
    """Helper class to locate where to insert/replace code in the AST."""

    def __init__(self, target_code: str):
        self.target_code = normalize_code(target_code)
        self.target_node = None
        self.containing_node = None
        self.target_index = None
        logger.debug(
            f"CodeLocator initialized with normalized target code: {self.target_code}"
        )

    def check_node_match(self, node) -> bool:
        """Check if a node matches our target code"""
        try:
            node_code = normalize_code(astor.to_source(node))
            logger.debug(
                f"Comparing normalized codes:\nTarget: {self.target_code}\nNode  : {node_code}"
            )
            return node_code == self.target_code
        except Exception as e:
            logger.debug(f"Error comparing node: {e}")
            return False

    def visit(self, node):
        """Visit a node and check for matches"""
        if hasattr(node, "body"):
            logger.debug(f"Checking body of {type(node).__name__}")
            for i, child in enumerate(node.body):
                if self.check_node_match(child):
                    logger.debug(f"Found matching node in {type(node).__name__}")
                    self.target_node = child
                    self.containing_node = node
                    self.target_index = i
                    return
                # Continue searching in this child's body if it has one
                self.visit(child)
        else:
            # For nodes without a body, visit their children
            super().generic_visit(node)


def modify_source(source_code: str, new_code: str, target: str, position: str) -> str:
    """Modify source code by inserting or replacing code at the specified location."""

    logger.debug(f"Modifying source code:")
    logger.debug(f"Target code: {target}")
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
        logger.error(f"Could not find target code in the source")
        raise ValueError(f"Could not find target code in the source")

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
                        "description": "The code snippet to target (e.g., 'var = 3' or 'def my_function():'). Indentation is ignored.",
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

