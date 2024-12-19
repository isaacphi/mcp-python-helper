from pathlib import Path

import pytest
import pytest_asyncio

from mcp_python_helper.utils.lsp.base import LSPServer
from mcp_python_helper.utils.lsp.operations import LSPOperations


@pytest_asyncio.fixture(scope="module")
def sample_project_path():
    return Path(__file__).parent / "fixtures" / "sample_project"


@pytest_asyncio.fixture(scope="module")
async def lsp(sample_project_path):
    """Provides an LSP server instance for testing."""

    server = LSPServer(
        workspace_root=sample_project_path,
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
    operations = LSPOperations(server)

    # Initialize the server once for all tests
    await server.initialize()
    yield operations
    # Clean up after all tests in the module
    await server.shutdown()