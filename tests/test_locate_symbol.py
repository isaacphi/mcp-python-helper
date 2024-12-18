import pytest

from mcp_python_helper.tools.locate_symbol import (
    LocateSymbolTool,
    LocateSymbolArguments,
)


@pytest.mark.asyncio
async def test_locate_class(sample_project_path):
    """Test locating a class definition."""
    tool = LocateSymbolTool()
    args = LocateSymbolArguments(
        symbol="MyClass",
        workspace_root=str(sample_project_path),
    )

    results = await tool.execute(args)
    assert len(results) == 1

    text = results[0].text
    assert "MyClass" in text
    assert "main.py" in text
    assert "Line 4" in text  # 1-based line numbers in output


@pytest.mark.asyncio
async def test_locate_function(sample_project_path):
    """Test locating a function definition."""
    tool = LocateSymbolTool()
    args = LocateSymbolArguments(
        symbol="my_function",
        workspace_root=str(sample_project_path),
    )

    results = await tool.execute(args)
    assert len(results) == 1

    text = results[0].text
    assert "my_function" in text
    assert "main.py" in text


@pytest.mark.asyncio
async def test_locate_multiple_symbols(sample_project_path):
    """Test locating multiple symbols with similar names."""
    tool = LocateSymbolTool()
    args = LocateSymbolArguments(
        symbol="method",
        workspace_root=str(sample_project_path),
    )

    results = await tool.execute(args)
    assert len(results) == 1  # One text result containing multiple locations

    text = results[0].text
    assert "my_method" in text
    assert "another_method" in text
    assert text.count("main.py") == 2  # Should mention the file twice


@pytest.mark.asyncio
async def test_locate_nonexistent_symbol(sample_project_path):
    """Test attempting to locate a symbol that doesn't exist."""
    tool = LocateSymbolTool()
    args = LocateSymbolArguments(
        symbol="NonExistentSymbol",
        workspace_root=str(sample_project_path),
    )

    results = await tool.execute(args)
    assert len(results) == 1
    assert "No definitions found" in results[0].text


@pytest.mark.asyncio
async def test_tool_reuses_server(sample_project_path):
    """Test that the tool reuses the LSP server instance."""
    tool = LocateSymbolTool()

    # First request should create server
    args = LocateSymbolArguments(
        symbol="MyClass",
        workspace_root=str(sample_project_path),
    )
    await tool.execute(args)

    # Store the server instance
    first_server = tool._server
    assert first_server is not None

    # Second request should reuse server
    await tool.execute(args)
    assert tool._server is first_server
