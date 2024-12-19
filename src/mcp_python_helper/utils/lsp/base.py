"""Base LSP server implementation with core protocol and utilities."""

import asyncio
import json
import logging
import os
import signal
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# Logging setup
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("lsp_debug")


def _format_lsp_message(prefix: str, msg: dict[str, Any]) -> str:
    """Format LSP message for readable logging."""
    if "method" in msg:
        if "id" in msg:
            return f"{prefix} [{msg['id']}] {msg['method']}"
        return f"{prefix} {msg['method']}"
    elif "result" in msg:
        return (
            f"{prefix} response [{msg['id']}] = {json.dumps(msg['result'], indent=2)}"
        )
    elif "error" in msg:
        return f"{prefix} error [{msg['id']}] = {json.dumps(msg['error'], indent=2)}"
    return f"{prefix} unknown message: {json.dumps(msg, indent=2)}"


class LSPServer:
    """Generic LSP server implementation."""

    def __init__(
        self,
        workspace_root: Path,
        command: Sequence[str],
        initialization_options: dict[str, Any] | None = None,
        server_settings: dict[str, Any] | None = None,
    ) -> None:
        self._process: subprocess.Popen | None = None
        self._write_pipe: os.IOBase | None = None
        self._read_pipe: os.IOBase | None = None
        self._read_fd: int | None = None
        self._write_fd: int | None = None
        self._lsp_read_fd: int | None = None
        self._lsp_write_fd: int | None = None
        self._is_initialized = False
        self._msg_id = 0
        self._server_capabilities: dict[str, Any] = {}
        self.workspace_root = workspace_root
        self.command = command
        self.initialization_options = initialization_options or {}
        self._document_versions: dict[str, int] = {}
        self.server_settings = server_settings or {}

    def _get_next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    async def initialize(self) -> None:
        """Initialize the LSP server."""
        if self._is_initialized:
            return

        # Create pipes
        self._read_fd, self._write_fd = os.pipe()
        self._lsp_read_fd, self._lsp_write_fd = os.pipe()
        self._write_pipe = os.fdopen(self._write_fd, "wb")
        self._read_pipe = os.fdopen(self._lsp_read_fd, "rb")

        workspace_uri = f"file://{self.workspace_root.absolute()}"

        # Start server
        logger.info(f"Starting LSP server: {' '.join(self.command)}")
        self._process = subprocess.Popen(
            self.command,
            stdin=self._read_fd,
            stdout=self._lsp_write_fd,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        if self._process.stderr:
            asyncio.get_event_loop().run_in_executor(None, self._log_stderr)

        # Initialize the server
        msg_id = self._get_next_id()
        init_params = {
            "processId": os.getpid(),
            "clientInfo": {"name": "mcp-python-helper", "version": "1.0.0"},
            "rootUri": workspace_uri,
            "capabilities": {
                "workspace": {
                    "configuration": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                },
                "textDocument": {
                    "synchronization": {
                        "dynamicRegistration": True,
                        "didSave": True,
                    },
                    "publishDiagnostics": {
                        "relatedInformation": True,
                        "versionSupport": True,
                    },
                },
            },
            "workspaceFolders": [
                {"uri": workspace_uri, "name": self.workspace_root.name}
            ],
            **self.initialization_options,
        }

        await self._write_message(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "method": "initialize",
                "params": init_params,
            }
        )

        # Wait for initialization response
        while True:
            msg = await self._read_message()
            if not msg:
                continue
            if msg.get("id") == msg_id and "result" in msg:
                self._server_capabilities = msg.get("result", {}).get(
                    "capabilities", {}
                )
                logger.info(
                    f"Server capabilities received: {json.dumps(self._server_capabilities, indent=2)}"
                )
                break
            elif "method" in msg and "id" in msg:
                await self._handle_server_request(msg)

        # Send initialized notification
        await self.notify("initialized", {})

        # Configure settings
        if self.server_settings:
            await self.notify(
                "workspace/didChangeConfiguration",
                {"settings": self.server_settings},
            )

        # Send didOpen for a virtual file to trigger analysis
        virtual_doc_uri = (
            f"file://{(self.workspace_root / '__virtual_init__.py').absolute()}"
        )
        self._document_versions[virtual_doc_uri] = 1

        await self.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": virtual_doc_uri,
                    "languageId": "python",
                    "version": self._document_versions[virtual_doc_uri],
                    "text": "# Virtual file to trigger pyright analysis\n",
                }
            },
        )

        # Wait for diagnostic response
        logger.info("Waiting for initial diagnostics...")
        start_time = asyncio.get_event_loop().time()
        timeout = 30  # 30 second timeout

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            if self._process and self._process.poll() is not None:
                raise Exception("Pyright process terminated unexpectedly")

            msg = await self._read_message()
            if not msg:
                await asyncio.sleep(0.1)
                continue

            if "method" in msg and "id" in msg:
                await self._handle_server_request(msg)
                continue

            if msg.get("method") == "textDocument/publishDiagnostics":
                logger.info("Initial diagnostics received")
                self._is_initialized = True
                break

        if not self._is_initialized:
            raise Exception("Timed out waiting for server initialization")

        logger.info("LSP server initialization complete")

    def _log_stderr(self) -> None:
        """Log stderr output from the LSP process."""
        if not self._process or not self._process.stderr:
            return

        while True:
            line = self._process.stderr.readline()
            if not line:
                break
            logger.debug(f"LSP stderr: {line.decode().strip()}")

    def _encode_message(self, msg: dict[str, Any]) -> bytes:
        """Encode a message according to LSP protocol."""
        content = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(content)}\r\n\r\n".encode()
        return header + content

    async def _write_message(self, msg: dict[str, Any]) -> None:
        """Write a message to the LSP server."""
        if not self._write_pipe:
            raise Exception("Server not initialized")
        encoded = self._encode_message(msg)
        logger.debug(_format_lsp_message("SEND", msg))
        self._write_pipe.write(encoded)
        self._write_pipe.flush()
        await asyncio.sleep(0.1)

    async def _read_message(self) -> dict[str, Any] | None:
        """Read a message from the LSP server."""
        if not self._read_pipe:
            raise Exception("Server not initialized")
        try:
            # Read headers
            header = b""
            while b"\r\n\r\n" not in header:
                next_char = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._read_pipe.read(1),  # type: ignore
                )
                if not next_char:
                    return None
                header += next_char

            # Parse content length
            header_str = header.decode("utf-8")
            content_length = int(header_str.split(":")[1].strip())

            # Read content
            content = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._read_pipe.read(content_length),  # type: ignore
            )

            msg = json.loads(content.decode("utf-8"))
            logger.debug(_format_lsp_message("RECV", msg))
            return msg

        except Exception as e:
            logger.error(f"Error reading LSP message: {e}")
            return None

    async def request(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Send a request to the LSP server and wait for response."""
        if not self._is_initialized:
            raise Exception("Server not initialized")

        msg_id = self._get_next_id()
        await self._write_message(
            {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
        )

        while True:
            msg = await self._read_message()
            if not msg:
                continue

            if "method" in msg and "id" in msg:
                await self._handle_server_request(msg)
                continue

            if msg.get("id") == msg_id:
                if "error" in msg:
                    logger.error(f"Error in response: {msg['error']}")
                    return None
                return msg.get("result")

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        """Send a notification to the LSP server."""
        await self._write_message(
            {"jsonrpc": "2.0", "method": method, "params": params}
        )

    async def _handle_server_request(self, msg: dict[str, Any]) -> None:
        """Handle incoming server requests."""
        method: str = msg.get("method", "")
        msg_id: Any = msg.get("id")

        if method == "client/registerCapability":
            await self._write_message({"jsonrpc": "2.0", "id": msg_id, "result": None})
        elif method == "workspace/configuration":
            await self._write_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": [self.server_settings],
                }
            )
        elif method == "window/logMessage":
            params = msg.get("params", {})
            level = params.get("type", 3)
            message = params.get("message", "")
            if level == 1:  # Error
                logger.error(f"Server: {message}")
            elif level == 2:  # Warning
                logger.warning(f"Server: {message}")
            else:  # Info or Log
                logger.info(f"Server: {message}")

    async def shutdown(self) -> None:
        """Shutdown the LSP server."""
        if not self._is_initialized:
            return

        try:
            if self._process and self._process.poll() is None:
                logger.info("Sending shutdown request...")
                await self.request("shutdown", {})
                logger.info("Sending exit notification...")
                await self.notify("exit", {})
                await asyncio.sleep(1)

                if self._process.poll() is None:
                    logger.info("Server still running, sending SIGTERM...")
                    os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)  # type: ignore
                    self._process.wait(timeout=5)

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            if self._process and self._process.poll() is None:
                try:
                    logger.warning("Forcing server termination with SIGKILL...")
                    os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)  # type: ignore
                except Exception as e2:
                    logger.error(f"Error killing server process: {e2}")

        finally:
            self._is_initialized = False
            if self._write_pipe:
                self._write_pipe.close()
            if self._read_pipe:
                self._read_pipe.close()
            logger.info("Server shutdown complete")
