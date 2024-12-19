"""LSP type definitions according to the Language Server Protocol specification.

Based on LSP 3.17 specification:
https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#workspace_symbol
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# Base LSP types
LSPAny = dict[str, Any] | list[Any] | str | int | float | bool | None
Uri = str  # LSP uses strings for URIs


class Position(BaseModel):
    """Position in a text document expressed as zero-based line and character offset."""

    line: int  # Zero-based line position
    character: int  # Zero-based character offset


class Range(BaseModel):
    """A range in a text document expressed as start/end positions."""

    start: Position
    end: Position


class Location(BaseModel):
    """Represents a location inside a resource, such as a line inside a text file."""

    uri: Uri
    range: Range


class WorkspaceSymbolParams(BaseModel):
    """The parameters of a Workspace Symbol Request."""

    query: str


class DocumentUri(BaseModel):
    """Document URI identifier."""

    uri: str


class TextDocumentIdentifier(BaseModel):
    """Text document identifier using URI."""

    uri: str


class TextDocumentItem(BaseModel):
    """An item to transfer a text document."""

    uri: str
    languageId: str  # noqa N815
    version: int
    text: str


class SymbolTag:
    """Constants for symbol tags."""

    Deprecated = 1


class WorkspaceSymbolKind:
    """Constants for symbol kinds, as defined in LSP specification."""

    File = 1
    Module = 2
    Namespace = 3
    Package = 4
    Class = 5
    Method = 6
    Property = 7
    Field = 8
    Constructor = 9
    Enum = 10
    Interface = 11
    Function = 12
    Variable = 13
    Constant = 14
    String = 15
    Number = 16
    Boolean = 17
    Array = 18
    Object = 19
    Key = 20
    Null = 21
    EnumMember = 22
    Struct = 23
    Event = 24
    Operator = 25
    TypeParameter = 26


class WorkspaceSymbol(BaseModel):
    """Represents information about programming constructs like variables, classes, etc."""

    name: str
    kind: int = Field(description="See WorkspaceSymbolKind")
    location: Location
    containerName: str | None = None  # noqa N815
    tags: list[int] | None = None  # SymbolTag[] in LSP spec


class TextDocumentPositionParams(BaseModel):
    """Parameters for requests that operate on a text document and a position."""

    textDocument: TextDocumentIdentifier  # noqa N815
    position: Position


class ReferenceContext(BaseModel):
    """Context for finding references."""

    includeDeclaration: bool  # noqa N815


class ReferenceParams(TextDocumentPositionParams):
    """Parameters for reference requests."""

    context: ReferenceContext


class HoverParams(TextDocumentPositionParams):
    """Parameters for hover requests."""

    pass


class MarkupContent(BaseModel):
    """Contains human-readable content like hover info."""

    kind: Literal["plaintext", "markdown"]
    value: str


class Hover(BaseModel):
    """Response to a hover request."""

    contents: MarkupContent | str | list[MarkupContent | str]
    range: Range | None = None


class DocumentSymbol(BaseModel):
    """Represents programming constructs in a hierarchical structure."""

    name: str
    detail: str | None = None
    kind: int
    tags: list[int] | None = None
    deprecated: bool | None = None
    range: Range
    selectionRange: Range  # noqa N815
    children: list["DocumentSymbol"] | None = None


# Response types for your operations
SymbolInformation = WorkspaceSymbol  # For backward compatibility
DocumentSymbolResponse = list[DocumentSymbol | SymbolInformation]
LocationResponse = Location | list[Location] | None
HoverResponse = Hover | None


class RenameParams(BaseModel):
    """Parameters for rename operations."""

    textDocument: TextDocumentIdentifier  # noqa N815
    position: Position
    newName: str  # noqa N815
