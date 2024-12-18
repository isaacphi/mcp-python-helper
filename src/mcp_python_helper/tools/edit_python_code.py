import logging
from typing import List, Dict, Optional
import mcp.types as types
from ..utils.ast_utils import modify_source

logger = logging.getLogger(__name__)


class EditPythonTool:
    name = "edit-python-code"
    description = (
        "Edit Python code by inserting or replacing code at a specified location"
    )

    @property
    def schema(self) -> dict:
        return {
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

    def get_definition(self) -> types.Tool:
        return types.Tool(
            name=self.name, description=self.description, inputSchema=self.schema
        )

    async def execute(
        self, arguments: Optional[Dict]
    ) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
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
            logger.error(f"Error executing edit-python-code tool: {e}")
            return [
                types.TextContent(type="text", text=f"Error modifying code: {str(e)}")
            ]

