import pytest
import pytest_asyncio
from mcp_python_helper.tools.locate_symbol import (
    LocateSymbolArguments,
    LocateSymbolTool,
)
from mcp_python_helper.utils.lsp.types import WorkspaceSymbol


@pytest_asyncio.fixture(scope="module")
async def symbol_tool(sample_project_path):
    """Provides a LocateSymbolTool instance for testing."""
    tool = LocateSymbolTool()
    # Do a first request to initialize the server
    args = LocateSymbolArguments(
        symbol="MyClass",
        workspace_root=str(sample_project_path),
    )
    await tool.execute(args)
    yield tool
    # Clean up
    if tool._server:
        await tool._server.shutdown()


@pytest.mark.asyncio
async def test_locate_class(symbol_tool, sample_project_path):
    """Test locating a class definition."""
    args = LocateSymbolArguments(
        symbol="MyClass",
        workspace_root=str(sample_project_path),
    )

    results = await symbol_tool.execute(args)
    assert len(results) == 1

    text = results[0].text
    assert "MyClass" in text
    assert "main.py" in text
    assert "Line 4" in text


@pytest.mark.asyncio
async def test_locate_function(symbol_tool, sample_project_path):
    """Test locating a function definition."""
    args = LocateSymbolArguments(
        symbol="my_function",
        workspace_root=str(sample_project_path),
    )

    results = await symbol_tool.execute(args)
    assert len(results) == 1

    text = results[0].text
    assert "my_function" in text
    assert "main.py" in text


@pytest.mark.asyncio
async def test_locate_multiple_symbols(symbol_tool, sample_project_path):
    """Test locating multiple symbols with similar names."""
    args = LocateSymbolArguments(
        symbol="method",
        workspace_root=str(sample_project_path),
    )

    results = await symbol_tool.execute(args)
    assert len(results) == 1

    text = results[0].text
    assert "my_method" in text
    assert "another_method" in text
    assert text.count("main.py") == 2


@pytest.mark.asyncio
async def test_locate_nonexistent_symbol(symbol_tool, sample_project_path):
    """Test attempting to locate a symbol that doesn't exist."""
    args = LocateSymbolArguments(
        symbol="NonExistentSymbol",
        workspace_root=str(sample_project_path),
    )

    results = await symbol_tool.execute(args)
    assert len(results) == 1
    assert "No definitions found" in results[0].text


@pytest.mark.asyncio
async def test_tool_reuses_server(symbol_tool, sample_project_path):
    """Test that the tool reuses the LSP server instance."""
    args = LocateSymbolArguments(
        symbol="MyClass",
        workspace_root=str(sample_project_path),
    )

    # We're using the initialized server
    first_server = symbol_tool._server
    assert first_server is not None

    # Second request should reuse server
    await symbol_tool.execute(args)
    assert symbol_tool._server is first_server

