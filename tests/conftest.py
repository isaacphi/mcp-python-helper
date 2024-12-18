import asyncio
import os
from pathlib import Path

import pytest
import pytest_asyncio


@pytest.fixture
def sample_project_path() -> Path:
    """Path to the sample project used for testing."""
    return Path(__file__).parent / "fixtures" / "sample_project"


@pytest_asyncio.fixture
async def lsp_server():
    """Provides an LSP server instance for testing."""
    from mcp_python_helper.utils.pyright_lsp import LSPServer

    server = LSPServer()
    yield server

    # Clean up after tests
    await server.shutdown()
