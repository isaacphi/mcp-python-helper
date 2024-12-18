import logging
from typing import Literal, TypedDict

import mcp.types as types

from mcp_python_helper.utils.ast_utils import modify_source

logger = logging.getLogger(__name__)


class EditPythonDict(TypedDict):
    filename: str
    code: str
    target: str
    position: Literal["before", "after", "replace"]


SCHEMA = {
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
}


class EditPythonTool:
    name = "edit-python-code"
    description = (
        "Edit Python code by inserting or replacing code at a specified location"
    )

    def get_definition(self) -> types.Tool:
        return types.Tool(
            name=self.name, description=self.description, inputSchema=SCHEMA
        )

    async def execute(
        self,
        arguments: EditPythonDict | None,
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if not arguments:
            raise ValueError("Missing arguments")

        target = arguments.get("target")
        filename = arguments.get("filename")
        code = arguments.get("code")
        position = arguments.get("position")

        try:
            with open(filename) as f:
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
            logger.error(f"Error executing edit-python-code tool: {e}")
            return [types.TextContent(type="text", text=f"Error modifying code: {e!s}")]
