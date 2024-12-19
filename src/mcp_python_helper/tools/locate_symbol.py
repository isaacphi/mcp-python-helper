import logging
from pathlib import Path
from typing import Any

import mcp.types as types
from pydantic import BaseModel, Field

from mcp_python_helper.utils.lsp.base import LSPServer
from mcp_python_helper.utils.lsp.operations import LSPOperations

logger = logging.getLogger(__name__)


class LocateSymbolArguments(BaseModel):
    symbol: str = Field(
        ...,
        description="Name of the symbol to locate (e.g. 'MyClass', 'my_function')",
    )
    workspace_root: str = Field(
        ...,
        description="Root directory of the Python project",
    )


class LocateSymbolTool:
    name = "locate-python-symbol"
    description = "Locate the definition of a Python symbol in the codebase"

    def __init__(self) -> None:
        self._server: LSPServer | None = None
        self.lsp: LSPOperations | None = None

    @property
    def schema(self) -> dict[str, Any]:
        return LocateSymbolArguments.model_json_schema()

    @property
    def arg_type(self):
        return LocateSymbolArguments

    def get_definition(self) -> types.Tool:
        return types.Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.schema,
        )

    async def execute(
        self, args: LocateSymbolArguments
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        try:
            # Initialize server if needed
            workspace_path = Path(args.workspace_root)

            if not self._server or self._server.workspace_root != workspace_path:
                self._server = LSPServer(
                    workspace_root=workspace_path,
                    command=["pyright-langserver", "--stdio", "--verbose"],
                    server_settings={
                        "python": {
                            "analysis": {
                                "autoSearchPaths": True,
                                "diagnosticMode": "workspace",
                                "typeCheckingMode": "basic",
                                "useLibraryCodeForTypes": True,
                            }
                        }
                    },
                )

                await self._server.shutdown()
                await self._server.initialize()
                self.lsp = LSPOperations(self._server)

            # Find the symbol
            locations = await self.lsp.find_symbol(args.symbol)

            if not locations:
                return [
                    types.TextContent(
                        type="text",
                        text=f"No definitions found for symbol '{args.symbol}'",
                    )
                ]

            # Format the results
            results = []
            for loc in locations:
                relative_path = Path(loc["filename"]).relative_to(workspace_path)
                result = (
                    f"Found {loc['name']} ({loc['kind']}) in:\n"
                    f"  File: {relative_path}\n"
                    f"  Line {loc['start']['line'] + 1}, "
                    f"Column {loc['start']['character'] + 1}"
                )
                results.append(result)

            return [
                types.TextContent(
                    type="text",
                    text="\n\n".join(results),
                )
            ]

        except Exception as e:
            logger.error(f"Error executing locate-symbol tool: {e}")
            return [
                types.TextContent(
                    type="text",
                    text=f"Error locating symbol: {e!s}",
                )
            ]