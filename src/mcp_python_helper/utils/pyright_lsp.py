import asyncio
import json
import logging
import os
import signal
import subprocess
from pathlib import Path
from typing import Any, Optional

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("pyright_debug")


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
    def __init__(self, workspace_root: Path) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._write_pipe: Optional[os.IOBase] = None
        self._read_pipe: Optional[os.IOBase] = None
        self._read_fd: Optional[int] = None
        self._write_fd: Optional[int] = None
        self._lsp_read_fd: Optional[int] = None
        self._lsp_write_fd: Optional[int] = None
        self._is_initialized = False
        self._msg_id = 0
        self._server_capabilities: dict[str, Any] = {}
        self._workspace_folders: list[dict[str, str]] = []
        self._document_versions: dict[str, int] = {}
        self.workspace_root: Path = workspace_root

    def _get_next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    async def initialize(self) -> None:
        if self._is_initialized:
            return

        # Create pipes
        self._read_fd, self._write_fd = os.pipe()
        self._lsp_read_fd, self._lsp_write_fd = os.pipe()

        self._write_pipe = os.fdopen(self._write_fd, "wb")
        self._read_pipe = os.fdopen(self._lsp_read_fd, "rb")

        workspace_uri = f"file://{self.workspace_root.absolute()}"
        self._workspace_folders = [
            {"uri": workspace_uri, "name": self.workspace_root.name}
        ]

        # Start server with debug logging
        logger.info("Starting pyright-langserver...")
        self._process = subprocess.Popen(
            ["pyright-langserver", "--stdio", "--verbose"],
            stdin=self._read_fd,
            stdout=self._lsp_write_fd,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        if self._process.stderr:
            asyncio.get_event_loop().run_in_executor(None, self._log_stderr)

        # Initialize the server
        logger.info("Initializing LSP server...")
        response = await self._request(
            "initialize",
            {
                "processId": os.getpid(),
                "clientInfo": {"name": "mcp-python-helper", "version": "1.0.0"},
                "rootUri": workspace_uri,
                "capabilities": {
                    "workspace": {
                        "configuration": True,
                        "didChangeConfiguration": {"dynamicRegistration": True},
                        "didChangeWatchedFiles": {"dynamicRegistration": True},
                        "symbol": {
                            "dynamicRegistration": True,
                            "symbolKind": {
                                "valueSet": [
                                    1,  # File
                                    2,  # Module
                                    3,  # Namespace
                                    4,  # Package
                                    5,  # Class
                                    6,  # Method
                                    7,  # Property
                                    8,  # Field
                                    9,  # Constructor
                                    10,  # Enum
                                    11,  # Interface
                                    12,  # Function
                                    13,  # Variable
                                    14,  # Constant
                                    15,  # String
                                    16,  # Number
                                    17,  # Boolean
                                    18,  # Array
                                    19,  # Object
                                    20,  # Key
                                    21,  # Null
                                    22,  # EnumMember
                                    23,  # Struct
                                    24,  # Event
                                    25,  # Operator
                                    26,  # TypeParameter
                                ]
                            },
                        },
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
                "workspaceFolders": self._workspace_folders,
            },
        )

        if not response:
            raise Exception("Failed to initialize LSP server: No response")
        elif "error" in response:
            raise Exception(f"Failed to initialize LSP server: {response['error']}")

        self._server_capabilities = response.get("capabilities", {})
        logger.info(
            f"Server capabilities received: {json.dumps(self._server_capabilities, indent=2)}"
        )

        # Send initialized notification
        logger.info("Sending initialized notification...")
        await self._notify("initialized", {})

        # Load pyright configuration if it exists
        pyrightconfig_path = self.workspace_root / "pyrightconfig.json"
        config = {}
        if pyrightconfig_path.exists():
            try:
                with open(pyrightconfig_path) as f:
                    config = json.load(f)
                    logger.info(
                        f"Loaded pyrightconfig.json: {json.dumps(config, indent=2)}"
                    )
            except Exception as e:
                logger.warning(f"Failed to load pyrightconfig.json: {e}")

        # Configure settings
        logger.info("Configuring workspace settings...")
        await self._notify(
            "workspace/didChangeConfiguration",
            {
                "settings": {
                    "python": {
                        "analysis": config.get(
                            "analysis",
                            {
                                "autoSearchPaths": True,
                                "diagnosticMode": "workspace",
                                "typeCheckingMode": "basic",
                                "useLibraryCodeForTypes": True,
                            },
                        )
                    }
                }
            },
        )

        # Open a document to trigger project analysis
        main_py = self.workspace_root / "main.py"
        if main_py.exists():
            logger.info(f"Opening main.py to trigger analysis: {main_py}")
            try:
                content = main_py.read_text()
                logger.debug(f"main.py content:\n{content}")
                doc_uri = f"file://{main_py.absolute()}"
                self._document_versions[doc_uri] = 1
                await self._notify(
                    "textDocument/didOpen",
                    {
                        "textDocument": {
                            "uri": doc_uri,
                            "languageId": "python",
                            "version": self._document_versions[doc_uri],
                            "text": content,
                        }
                    },
                )

                doc_symbols = await self._request(
                    "textDocument/documentSymbol", {"textDocument": {"uri": doc_uri}}
                )
                if not doc_symbols:
                    logger.warning(
                        "No document symbols found, indexing may not be complete"
                    )

            except Exception as e:
                logger.error(f"Error opening main.py: {e}")

        # Wait for analysis
        logger.info("Waiting for initial analysis...")
        await asyncio.sleep(2)

        self._is_initialized = True
        logger.info("LSP server initialization complete")

    def _log_stderr(self) -> None:
        """Log stderr output from the pyright process."""
        if not self._process or not self._process.stderr:
            return

        while True:
            line = self._process.stderr.readline()
            if not line:
                break
            logger.debug(f"pyright stderr: {line.decode().strip()}")

    def _encode_message(self, msg: dict[str, Any]) -> bytes:
        content = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(content)}\r\n\r\n".encode()
        return header + content

    async def _write_message(self, msg: dict[str, Any]) -> None:
        if not self._write_pipe:
            raise Exception("Server not initialized")
        encoded = self._encode_message(msg)
        logger.debug(_format_lsp_message("SEND", msg))
        self._write_pipe.write(encoded)
        self._write_pipe.flush()
        await asyncio.sleep(0.1)

    async def _read_message(self) -> Optional[dict[str, Any]]:
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

    async def _request(
        self, method: str, params: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        msg_id = self._get_next_id()
        await self._write_message(
            {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
        )

        while True:
            msg = await self._read_message()
            if not msg:
                continue

            # Handle server requests that might come before our response
            if "method" in msg and "id" in msg:
                await self._handle_server_request(msg)
                continue

            if msg.get("id") == msg_id:
                if "error" in msg:
                    logger.error(f"Error in response: {msg['error']}")
                    return None
                return msg.get("result")

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._write_message(
            {"jsonrpc": "2.0", "method": method, "params": params}
        )

    async def _handle_server_request(self, msg: dict[str, Any]) -> None:
        method: str = msg.get("method", "")
        msg_id: Any = msg.get("id")

        if method == "client/registerCapability":
            await self._write_message({"jsonrpc": "2.0", "id": msg_id, "result": None})
        elif method == "workspace/configuration":
            await self._write_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": [
                        {
                            "analysis": {
                                "autoSearchPaths": True,
                                "diagnosticMode": "workspace",
                                "typeCheckingMode": "basic",
                                "useLibraryCodeForTypes": True,
                            }
                        }
                    ],
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

    async def find_symbol(self, symbol_name: str) -> list[dict[str, Any]]:
        """Find the location of a symbol in the workspace."""
        if not self._is_initialized:
            raise Exception("Server not initialized")

        logger.info(f"Searching for symbol: {symbol_name}")
        response = await self._request("workspace/symbol", {"query": symbol_name})

        if response is None:
            logger.warning("No response from workspace/symbol request")
            return []

        logger.info(f"Found {len(response)} symbols")
        return [
            {
                "filename": str(Path(symbol["location"]["uri"].replace("file://", ""))),
                "start": symbol["location"]["range"]["start"],
                "end": symbol["location"]["range"]["end"],
                "kind": symbol["kind"],
                "name": symbol["name"],
            }
            for symbol in response
        ]

    async def shutdown(self) -> None:
        """Properly shutdown the LSP server."""
        if not self._is_initialized:
            return

        try:
            if self._process and self._process.poll() is None:
                logger.info("Sending shutdown request...")
                await self._request("shutdown", {})
                logger.info("Sending exit notification...")
                await self._notify("exit", {})
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
