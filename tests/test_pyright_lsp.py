import logging

import pytest
from mcp_python_helper.utils.lsp.operations import LSPOperations
from mcp_python_helper.utils.lsp.types import Location, Range, Position, WorkspaceSymbol

# Set up logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("pyright_test")


@pytest.mark.asyncio
async def test_lsp_server_initialization(lsp: LSPOperations):
    """Test that the LSP server initializes correctly."""
    assert lsp._server._is_initialized, "Server failed to initialize"  # pyright: ignore


@pytest.mark.asyncio
async def test_find_class(lsp: LSPOperations):
    """Test finding a class definition."""
    results = await lsp.find_symbol("MyClass")

    assert len(results) == 1, f"Expected 1 result for MyClass, got {len(results)}"
    result = results[0]
    assert isinstance(result, WorkspaceSymbol)
    assert result.name == "MyClass"
    assert "main.py" in result.location.uri
    assert result.location.range.start.line == 3


@pytest.mark.asyncio
async def test_find_function(lsp: LSPOperations):
    """Test finding a function definition."""
    results = await lsp.find_symbol("my_function")
    assert len(results) == 1
    result = results[0]
    assert isinstance(result, WorkspaceSymbol)
    assert result.name == "my_function"
    assert "main.py" in result.location.uri
    assert result.location.range.start.line == 11


@pytest.mark.asyncio
async def test_find_constant(lsp: LSPOperations):
    """Test finding a constant definition."""
    results = await lsp.find_symbol("CONSTANT")
    assert len(results) == 1, f"Expected 1 result for CONSTANT, got {len(results)}"
    result = results[0]
    assert isinstance(result, WorkspaceSymbol)
    assert result.name == "CONSTANT", f"Expected 'CONSTANT', got '{result.name}'"
    assert "main.py" in result.location.uri
    assert result.location.range.start.line == 15


@pytest.mark.asyncio
async def test_find_nonexistent_symbol(lsp: LSPOperations):
    """Test finding a symbol that doesn't exist."""
    results = await lsp.find_symbol("NonExistentSymbol")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_find_multiple_symbols(lsp: LSPOperations):
    """Test finding multiple symbols with similar names."""
    results = await lsp.find_symbol("method")
    assert len(results) == 2, f"Expected 2 results for 'method', got {len(results)}"
    names = {r.name for r in results}
    assert "my_method" in names
    assert "another_method" in names


@pytest.mark.asyncio
async def test_server_shutdown(lsp: LSPOperations):
    """Test that the server shuts down cleanly."""
    assert lsp._server._is_initialized  # pyright: ignore
    await lsp._server.shutdown()  # pyright: ignore
    assert not lsp._server._is_initialized  # pyright: ignore
    process_status = lsp._server._process.poll() if lsp._server._process else None  # pyright: ignore
    assert lsp._server._process is None or process_status is not None  # pyright: ignore

