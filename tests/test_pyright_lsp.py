import pytest
import logging
import json
from pathlib import Path

from mcp_python_helper.utils.pyright_lsp import LSPServer

# Set up logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("pyright_test")


@pytest.mark.asyncio
async def test_lsp_server_initialization(
    lsp_server: LSPServer, sample_project_path: Path
):
    """Test that the LSP server initializes correctly."""
    logger.info(
        f"Starting initialization test with project path: {sample_project_path}"
    )
    await lsp_server.initialize(sample_project_path)
    logger.info("Server initialization completed")
    assert lsp_server._is_initialized, "Server failed to initialize"
    logger.info(
        "Server capabilities: %s", json.dumps(lsp_server._server_capabilities, indent=2)
    )


@pytest.mark.asyncio
async def test_find_class(lsp_server: LSPServer, sample_project_path: Path):
    """Test finding a class definition."""
    await lsp_server.initialize(sample_project_path)

    results = await lsp_server.find_symbol("MyClass")

    assert len(results) == 1, f"Expected 1 result for MyClass, got {len(results)}"
    result = results[0]

    assert result["name"] == "MyClass"
    assert "main.py" in result["filename"]
    assert result["start"]["line"] == 3


@pytest.mark.asyncio
async def test_find_function(lsp_server: LSPServer, sample_project_path: Path):
    """Test finding a function definition."""
    await lsp_server.initialize(sample_project_path)

    results = await lsp_server.find_symbol("my_function")

    assert len(results) == 1
    result = results[0]

    assert result["name"] == "my_function"
    assert "main.py" in result["filename"]
    assert result["start"]["line"] == 11


@pytest.mark.asyncio
async def test_find_constant(lsp_server: LSPServer, sample_project_path: Path):
    """Test finding a constant definition."""

    await lsp_server.initialize(sample_project_path)

    results = await lsp_server.find_symbol("CONSTANT")

    assert len(results) == 1, f"Expected 1 result for CONSTANT, got {len(results)}"
    result = results[0]

    assert result["name"] == "CONSTANT", f"Expected 'CONSTANT', got '{result['name']}'"
    assert "main.py" in result["filename"]
    assert result["start"]["line"] == 15


@pytest.mark.asyncio
async def test_find_nonexistent_symbol(
    lsp_server: LSPServer, sample_project_path: Path
):
    """Test finding a symbol that doesn't exist."""

    await lsp_server.initialize(sample_project_path)

    results = await lsp_server.find_symbol("NonExistentSymbol")

    assert len(results) == 0


@pytest.mark.asyncio
async def test_find_multiple_symbols(lsp_server: LSPServer, sample_project_path: Path):
    """Test finding multiple symbols with similar names."""

    await lsp_server.initialize(sample_project_path)

    results = await lsp_server.find_symbol("method")

    assert len(results) == 2, f"Expected 2 results for 'method', got {len(results)}"

    names = {r["name"] for r in results}

    assert "my_method" in names
    assert "another_method" in names


@pytest.mark.asyncio
async def test_server_shutdown(lsp_server: LSPServer, sample_project_path: Path):
    """Test that the server shuts down cleanly."""

    await lsp_server.initialize(sample_project_path)

    assert lsp_server._is_initialized, "Server should be initialized before shutdown"

    await lsp_server.shutdown()

    assert not lsp_server._is_initialized

    process_status = lsp_server._process.poll() if lsp_server._process else None

    assert lsp_server._process is None or process_status is not None

