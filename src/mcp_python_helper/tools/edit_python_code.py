from typing import List, Literal
import logging
from pydantic import BaseModel
import mcp.types as types
from ..utils.ast_utils import modify_source

logger = logging.getLogger(__name__)


class EditPythonCodeArgs(BaseModel):
    filename: str
    code: str
    target: str
    position: Literal["before", "after", "replace"]

    model_config = {
        "json_schema_extra": {
            "properties": {
                "filename": {
                    "description": "Full path to the Python file to edit",
                },
                "code": {
                    "description": "Valid Python code to insert",
                },
                "target": {
                    "description": "Symbol name or full line of code to target. E.g., 'var = 3', 'my_function', 'MyClass.my_method', 'MY_CONSTANT'",
                },
                "position": {
                    "description": "Where to insert the code relative to the target",
                },
            }
        }
    }


def get_tool_definition() -> types.Tool:
    return types.Tool(
        name="edit-python-code",
        description="Edit Python code by inserting or replacing code at a specified location",
        inputSchema=EditPythonCodeArgs.model_json_schema(),
    )


async def handle_tool(arguments: dict) -> List[types.TextContent]:
    args = EditPythonCodeArgs(**arguments)

    try:
        with open(args.filename, "r") as f:
            source = f.read()

        modified_source = modify_source(source, args.code, args.target, args.position)

        with open(args.filename, "w") as f:
            f.write(modified_source)

        return [
            types.TextContent(
                type="text",
                text=f"!!!Successfully modified {args.filename} - {args.position} {args.target}",
            )
        ]
    except Exception as e:
        logger.error(f"Error in handle_tool: {e}")
        return [types.TextContent(type="text", text=f"Error modifying code: {str(e)}")]

