from collections.abc import AsyncGenerator, Sequence
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from mcp.types import EmbeddedResource, ImageContent, TextContent
from mcp_python_helper.tools.locate_symbol import (
    LocateSymbolArguments,
    LocateSymbolTool,
)


@pytest_asyncio.fixture(scope="module")  # type: ignore
async def symbol_tool(
    sample_project_path: Path,
) -> AsyncGenerator[LocateSymbolTool, None]:
    """Provides a LocateSymbolTool instance for testing."""
    tool = LocateSymbolTool()
    args = LocateSymbolArguments(
        symbol="MyClass",
        workspace_root=str(sample_project_path),
    )
    await tool.execute(args)
    yield tool
    if tool.server:
        await tool.server.shutdown()


@pytest.mark.asyncio
async def test_locate_class(
    symbol_tool: LocateSymbolTool, sample_project_path: Path
) -> None:
    """Test locating a class definition."""
    args = LocateSymbolArguments(
        symbol="MyClass",
        workspace_root=str(sample_project_path),
    )

    results: Sequence[
        TextContent | ImageContent | EmbeddedResource
    ] = await symbol_tool.execute(args)
    assert len(results) == 1
    result = cast(TextContent, results[0])

    assert "MyClass" in result.text
    assert "main.py" in result.text
    assert "Line 4" in result.text


@pytest.mark.asyncio
async def test_locate_function(
    symbol_tool: LocateSymbolTool, sample_project_path: Path
) -> None:
    """Test locating a function definition."""
    args = LocateSymbolArguments(
        symbol="my_function",
        workspace_root=str(sample_project_path),
    )

    results: Sequence[
        TextContent | ImageContent | EmbeddedResource
    ] = await symbol_tool.execute(args)
    assert len(results) == 1
    result = cast(TextContent, results[0])

    assert "my_function" in result.text
    assert "main.py" in result.text


@pytest.mark.asyncio
async def test_locate_multiple_symbols(
    symbol_tool: LocateSymbolTool, sample_project_path: Path
) -> None:
    """Test locating multiple symbols with similar names."""
    args = LocateSymbolArguments(
        symbol="method",
        workspace_root=str(sample_project_path),
    )

    results: Sequence[
        TextContent | ImageContent | EmbeddedResource
    ] = await symbol_tool.execute(args)
    assert len(results) == 1
    result = cast(TextContent, results[0])

    assert "my_method" in result.text
    assert "another_method" in result.text
    assert result.text.count("main.py") == 2


@pytest.mark.asyncio
async def test_locate_nonexistent_symbol(
    symbol_tool: LocateSymbolTool, sample_project_path: Path
) -> None:
    """Test attempting to locate a symbol that doesn't exist."""
    args = LocateSymbolArguments(
        symbol="NonExistentSymbol",
        workspace_root=str(sample_project_path),
    )

    results: Sequence[
        TextContent | ImageContent | EmbeddedResource
    ] = await symbol_tool.execute(args)
    assert len(results) == 1
    result = cast(TextContent, results[0])
    assert "No definitions found" in result.text


@pytest.mark.asyncio
async def test_tool_reuses_server(
    symbol_tool: LocateSymbolTool, sample_project_path: Path
) -> None:
    """Test that the tool reuses the LSP server instance."""
    args = LocateSymbolArguments(
        symbol="MyClass",
        workspace_root=str(sample_project_path),
    )

    # We're using the initialized server
    original_server = symbol_tool.server
    assert original_server is not None

    # Second request should reuse server
    await symbol_tool.execute(args)
    assert symbol_tool.server is original_server
