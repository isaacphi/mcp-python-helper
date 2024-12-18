from pathlib import Path

import pytest
import pytest_asyncio


@pytest.fixture(scope="module")
def sample_project_path() -> Path:
    """Path to the sample project used for testing."""
    return Path(__file__).parent / "fixtures" / "sample_project"


@pytest_asyncio.fixture(scope="module")
async def lsp_server(sample_project_path):
    """Provides an LSP server instance for testing."""
    from mcp_python_helper.utils.pyright_lsp import LSPServer

    server = LSPServer(sample_project_path)
    # Initialize the server once for all tests
    await server.initialize()
    yield server
    # Clean up after all tests in the module
    await server.shutdown()
