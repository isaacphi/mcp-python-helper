"""High-level LSP operations."""

from pathlib import Path
import re
from typing import Any, List, Optional, Protocol


class LSPRequester(Protocol):
    """Protocol for LSP request functionality."""

    async def request(
        self, method: str, params: dict[str, Any]
    ) -> Optional[dict[str, Any]]: ...
    async def notify(self, method: str, params: dict[str, Any]) -> None: ...


class LSPOperations:
    """High-level operations for working with LSP servers."""

    def __init__(self, server: LSPRequester):
        self._server = server

    async def find_symbol(self, symbol_name: str) -> list[dict[str, Any]]:
        """Find the location of a symbol in the workspace."""
        response = await self._server.request(
            "workspace/symbol", {"query": symbol_name}
        )
        print(response)
        if response is None:
            return []

        return [
            {
                "filename": str(Path(symbol["location"]["uri"].replace("file://", ""))),
                "start": symbol["location"]["range"]["start"],
                "end": symbol["location"]["range"]["end"],
                "kind": symbol["kind"],
                "name": symbol["name"],
            }
            for symbol in response
        ]

    async def get_type_definition(
        self, file_uri: str, position: dict[str, int]
    ) -> list[dict[str, Any]]:
        """Get type definition for symbol at position."""
        response = await self._server.request(
            "textDocument/typeDefinition",
            {"textDocument": {"uri": file_uri}, "position": position},
        )

        if response is None:
            return []

        # Handle both single location and location array responses
        locations = response if isinstance(response, list) else [response]
        return [
            {
                "filename": str(Path(loc["uri"].replace("file://", ""))),
                "start": loc["range"]["start"],
                "end": loc["range"]["end"],
            }
            for loc in locations
        ]

    async def find_references(
        self, file_uri: str, position: dict[str, int], include_declaration: bool = True
    ) -> list[dict[str, Any]]:
        """Find all references to symbol at position."""
        response = await self._server.request(
            "textDocument/references",
            {
                "textDocument": {"uri": file_uri},
                "position": position,
                "context": {"includeDeclaration": include_declaration},
            },
        )

        if response is None:
            return []

        return [
            {
                "filename": str(Path(ref["uri"].replace("file://", ""))),
                "start": ref["range"]["start"],
                "end": ref["range"]["end"],
            }
            for ref in response
        ]

    async def get_hover_info(
        self, file_uri: str, position: dict[str, int]
    ) -> Optional[str]:
        """Get hover information for symbol at position."""
        response = await self._server.request(
            "textDocument/hover",
            {"textDocument": {"uri": file_uri}, "position": position},
        )

        if response is None or "contents" not in response:
            return None

        contents = response["contents"]
        if isinstance(contents, dict):
            return contents.get("value", "")
        elif isinstance(contents, str):
            return contents
        elif isinstance(contents, list):
            return "\n".join(
                str(content.get("value", ""))
                if isinstance(content, dict)
                else str(content)
                for content in contents
            )
        return None

    async def get_document_symbols(self, file_uri: str) -> list[dict[str, Any]]:
        """Get all symbols in a document."""
        response = await self._server.request(
            "textDocument/documentSymbol", {"textDocument": {"uri": file_uri}}
        )

        if response is None:
            return []

        def process_symbol(symbol: dict[str, Any]) -> dict[str, Any]:
            result = {
                "name": symbol["name"],
                "kind": symbol["kind"],
                "range": symbol["range"],
                "selection_range": symbol["selectionRange"],
            }
            if "children" in symbol:
                result["children"] = [
                    process_symbol(child) for child in symbol["children"]
                ]
            return result

        return [process_symbol(symbol) for symbol in response]

    async def get_implementation(
        self, file_uri: str, position: dict[str, int]
    ) -> list[dict[str, Any]]:
        """Get implementation locations for symbol at position."""
        response = await self._server.request(
            "textDocument/implementation",
            {"textDocument": {"uri": file_uri}, "position": position},
        )

        if response is None:
            return []

        # Handle both single location and location array responses
        locations = response if isinstance(response, list) else [response]
        return [
            {
                "filename": str(Path(loc["uri"].replace("file://", ""))),
                "start": loc["range"]["start"],
                "end": loc["range"]["end"],
            }
            for loc in locations
        ]

    async def get_definition(
        self, file_uri: str, position: dict[str, int]
    ) -> list[dict[str, Any]]:
        """Get definition locations for symbol at position."""
        response = await self._server.request(
            "textDocument/definition",
            {"textDocument": {"uri": file_uri}, "position": position},
        )

        if response is None:
            return []

        # Handle both single location and location array responses
        locations = response if isinstance(response, list) else [response]
        return [
            {
                "filename": str(Path(loc["uri"].replace("file://", ""))),
                "start": loc["range"]["start"],
                "end": loc["range"]["end"],
            }
            for loc in locations
        ]

    async def prepare_rename(
        self, file_uri: str, position: dict[str, int]
    ) -> Optional[dict[str, Any]]:
        """Check if symbol at position can be renamed."""
        return await self._server.request(
            "textDocument/prepareRename",
            {"textDocument": {"uri": file_uri}, "position": position},
        )

    async def rename_symbol(
        self, file_uri: str, position: dict[str, int], new_name: str
    ) -> Optional[dict[str, Any]]:
        """Rename symbol at position."""
        return await self._server.request(
            "textDocument/rename",
            {
                "textDocument": {"uri": file_uri},
                "position": position,
                "newName": new_name,
            },
        )
