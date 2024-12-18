import logging
from enum import Enum
from typing import Any

import mcp.types as types
from pydantic import BaseModel, Field

from mcp_python_helper.utils.ast_utils import modify_source

logger = logging.getLogger(__name__)


class Position(str, Enum):
    BEFORE = "before"
    AFTER = "after"
    REPLACE = "replace"


class EditPythonArguments(BaseModel):
    filename: str = Field(..., description="Full path to the Python file to edit")
    code: str = Field(..., description="Valid Python code to insert")
    target: str = Field(
        ...,
        description="Symbol name or full line of code to target. E.g., 'var = 3', 'my_function', 'MyClass.my_method', 'MY_CONSTANT'",
    )
    position: Position = Field(
        ..., description="Where to insert the code relative to the target"
    )


class EditPythonTool:
    name = "edit-python-code"
    description = (
        "Edit Python code by inserting or replacing code at a specified location"
    )

    @property
    def schema(self) -> dict[str, Any]:
        return EditPythonArguments.model_json_schema()

    @property
    def arg_type(self):
        return EditPythonArguments

    def get_definition(self) -> types.Tool:
        return types.Tool(
            name=self.name, description=self.description, inputSchema=self.schema
        )

    async def execute(
        self,
        args: EditPythonArguments,
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        try:
            with open(args.filename) as f:
                source = f.read()
            modified_source = modify_source(
                source, args.code, args.target, args.position
            )
            with open(args.filename, "w") as f:
                f.write(modified_source)
            return [
                types.TextContent(
                    type="text",
                    text=f"Successfully modified {args.filename} - {args.position} {args.target}",
                )
            ]
        except Exception as e:
            logger.error(f"Error executing edit-python-code tool: {e}")
            return [types.TextContent(type="text", text=f"Error modifying code: {e!s}")]
