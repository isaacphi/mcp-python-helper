from typing import Any, Protocol, cast

from .types import (
    DocumentSymbol,
    Hover,
    HoverParams,
    Location,
    Position,
    ReferenceContext,
    ReferenceParams,
    RenameParams,
    TextDocumentIdentifier,
    TextDocumentPositionParams,
    WorkspaceSymbol,
    WorkspaceSymbolParams,
)


class LSPRequester(Protocol):
    """Protocol for LSP request functionality."""

    async def request(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any] | None: ...
    async def notify(self, method: str, params: dict[str, Any]) -> None: ...


class LSPOperations:
    """High-level operations for working with LSP servers."""

    def __init__(self, server: LSPRequester):
        self.server = server

    async def find_symbol(self, symbol_name: str) -> list[WorkspaceSymbol]:
        """Find the location of a symbol in the workspace."""
        params = WorkspaceSymbolParams(query=symbol_name)
        response = await self.server.request("workspace/symbol", params.model_dump())
        if not response:
            return []

        return [
            WorkspaceSymbol.model_validate(s)
            for s in cast(list[dict[str, Any]], response)
        ]

    async def get_type_definition(
        self, file_uri: str, position: Position
    ) -> list[Location]:
        """Get type definition for symbol at position."""
        params = TextDocumentPositionParams(
            textDocument=TextDocumentIdentifier(uri=file_uri),
            position=position,
        )
        response = await self.server.request(
            "textDocument/typeDefinition", params.model_dump()
        )

        if not response:
            return []

        raw_locations = cast(dict[str, Any] | list[dict[str, Any]], response)
        return (
            [Location.model_validate(raw_locations)]
            if isinstance(raw_locations, dict)
            else [Location.model_validate(loc) for loc in raw_locations]
        )

    async def find_references(
        self, file_uri: str, position: Position, include_declaration: bool = True
    ) -> list[Location]:
        """Find all references to symbol at position."""
        params = ReferenceParams(
            textDocument=TextDocumentIdentifier(uri=file_uri),
            position=position,
            context=ReferenceContext(includeDeclaration=include_declaration),
        )
        response = await self.server.request(
            "textDocument/references", params.model_dump()
        )

        if not response:
            return []

        return [
            Location.model_validate(loc) for loc in cast(list[dict[str, Any]], response)
        ]

    async def get_hover_info(self, file_uri: str, position: Position) -> Hover | None:
        """Get hover information for symbol at position."""
        params = HoverParams(
            textDocument=TextDocumentIdentifier(uri=file_uri),
            position=position,
        )
        response = await self.server.request("textDocument/hover", params.model_dump())

        if not response:
            return None

        return Hover.model_validate(response)

    async def get_document_symbols(self, file_uri: str) -> list[DocumentSymbol]:
        """Get all symbols in a document."""
        response = await self.server.request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": file_uri}},
        )

        if not response:
            return []

        return [DocumentSymbol.model_validate(symbol) for symbol in response]

    async def get_implementation(
        self, file_uri: str, position: Position
    ) -> list[Location]:
        """Get implementation locations for symbol at position."""
        params = TextDocumentPositionParams(
            textDocument=TextDocumentIdentifier(uri=file_uri),
            position=position,
        )
        response = await self.server.request(
            "textDocument/implementation", params.model_dump()
        )

        if not response:
            return []

        raw_locations = cast(dict[str, Any] | list[dict[str, Any]], response)
        return (
            [Location.model_validate(raw_locations)]
            if isinstance(raw_locations, dict)
            else [Location.model_validate(loc) for loc in raw_locations]
        )

    async def get_definition(self, file_uri: str, position: Position) -> list[Location]:
        """Get definition locations for symbol at position."""
        params = TextDocumentPositionParams(
            textDocument=TextDocumentIdentifier(uri=file_uri),
            position=position,
        )
        response = await self.server.request(
            "textDocument/definition", params.model_dump()
        )

        if not response:
            return []

        raw_locations = cast(dict[str, Any] | list[dict[str, Any]], response)
        return (
            [Location.model_validate(raw_locations)]
            if isinstance(raw_locations, dict)
            else [Location.model_validate(loc) for loc in raw_locations]
        )

    async def prepare_rename(
        self, file_uri: str, position: Position
    ) -> dict[str, Any] | None:
        """Check if symbol at position can be renamed."""
        params = TextDocumentPositionParams(
            textDocument=TextDocumentIdentifier(uri=file_uri),
            position=position,
        )
        return await self.server.request(
            "textDocument/prepareRename", params.model_dump()
        )

    async def rename_symbol(
        self, file_uri: str, position: Position, new_name: str
    ) -> dict[str, Any] | None:
        """Rename symbol at position."""
        params = RenameParams(
            textDocument=TextDocumentIdentifier(uri=file_uri),
            position=position,
            newName=new_name,
        )
        return await self.server.request("textDocument/rename", params.model_dump())
