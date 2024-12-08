import sys
import subprocess
import json
import logging
import time
import os
from typing import Optional, Dict, Any, List
from pathlib import Path
import asyncio
import tempfile

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("pyright_symbol")


class PyrightSymbolLookup:
    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path).resolve()
        self.server_process: Optional[subprocess.Popen] = None
        self.websocket = None
        self.request_id = 0
        self.python_version = ".".join(
            map(str, sys.version_info[:2])
        )  # Get current Python version

        # Create a temporary file for pyright logs
        self.log_file = tempfile.NamedTemporaryFile(
            prefix="pyright_", suffix=".log", delete=False, mode="w"
        )
        logger.info(f"Pyright server logs will be written to: {self.log_file.name}")

    #

    async def start_server(self) -> bool:
        """Start the pyright language server."""
        try:
            logger.info("Starting pyright language server...")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.workspace_path)
            env["PYRIGHT_PYTHON_DEBUG"] = "1"  # Enable verbose debugging
            env["PYRIGHT_DEBUG_LOG_PATH"] = self.log_file.name
            env["PYRIGHT_PROJECT_ROOT"] = str(self.workspace_path)

            # Use npm directly to ensure latest compatible version
            npm_install = subprocess.run(
                ["npm", "install", "pyright", "--global"],
                capture_output=True,
                text=True,
            )
            if npm_install.returncode != 0:
                logger.error(
                    f"Failed to install pyright globally: {npm_install.stderr}"
                )
                return False

            # Now use the globally installed pyright-langserver
            command = [
                "pyright-langserver",
                "--stdio",
                "--verbose",
                "--project",
                str(self.workspace_path),
                "--venv-path",
                str(Path(self.workspace_path) / ".venv"),
            ]

            self.server_process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )

            async def read_stderr():
                while True:
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, self.server_process.stderr.readline
                    )
                    if not line:
                        break
                    logger.debug(f"Pyright stderr: {line.strip()}")

            asyncio.create_task(read_stderr())
            await asyncio.sleep(2)

            if self.server_process.poll() is not None:
                stderr = (
                    self.server_process.stderr.read()
                    if self.server_process.stderr
                    else "No error output"
                )
                logger.error(
                    f"Server failed to start. Exit code: {self.server_process.returncode}"
                )
                logger.error(f"Server error output: {stderr}")
                return False

            logger.info("Pyright server started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start pyright server: {str(e)}")
            return False

    # async def start_server(self) -> bool:
    #     try:
    #         logger.info("Starting pyright language server...")
    #         env = os.environ.copy()
    #         env["PYTHONPATH"] = str(self.workspace_path)
    #         env["PYRIGHT_PYTHON_FORCE_VERSION"] = self.python_version
    #         env["PYRIGHT_PYTHON_DEBUG"] = "1"
    #         env["PYRIGHT_DEBUG_LOG_PATH"] = self.log_file.name
    #
    #         # Use Python module directly instead of command line tool
    #         command = [
    #             sys.executable,
    #             "-m",
    #             "pyright.langserver",
    #             "--stdio",
    #             "--verbose",
    #         ]
    #
    #         self.server_process = subprocess.Popen(
    #             command,
    #             stdin=subprocess.PIPE,
    #             stdout=subprocess.PIPE,
    #             stderr=subprocess.PIPE,
    #             text=True,
    #             bufsize=1,
    #             env=env,
    #         )
    #
    #         async def read_stderr():
    #             while True:
    #                 line = await asyncio.get_event_loop().run_in_executor(
    #                     None, self.server_process.stderr.readline
    #                 )
    #                 if not line:
    #                     break
    #                 logger.debug(f"Pyright stderr: {line.strip()}")
    #
    #         asyncio.create_task(read_stderr())
    #         await asyncio.sleep(2)
    #
    #         if self.server_process.poll() is not None:
    #             stderr = (
    #                 self.server_process.stderr.read()
    #                 if self.server_process.stderr
    #                 else "No error output"
    #             )
    #             logger.error(
    #                 f"Server failed to start. Exit code: {self.server_process.returncode}"
    #             )
    #             logger.error(f"Server error output: {stderr}")
    #             return False
    #
    #         logger.info("Pyright server started successfully")
    #         return True
    #
    #     except Exception as e:
    #         logger.error(f"Failed to start pyright server: {str(e)}")
    #         return False
    #
    async def initialize_connection(self) -> bool:
        try:
            init_params = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": "initialize",
                "params": {
                    "processId": os.getpid(),
                    "rootPath": str(self.workspace_path),
                    "rootUri": f"file://{self.workspace_path}",
                    "workspaceFolders": [
                        {
                            "uri": f"file://{self.workspace_path}",
                            "name": self.workspace_path.name,
                        }
                    ],
                    "capabilities": {
                        "workspace": {
                            "workspaceFolders": True,
                            "configuration": True,
                            "didChangeConfiguration": {"dynamicRegistration": True},
                            "symbol": {
                                "dynamicRegistration": True,
                                "symbolKind": {
                                    "valueSet": list(
                                        range(1, 27)
                                    )  # Support all symbol kinds
                                },
                            },
                        },
                        "textDocument": {
                            "synchronization": {
                                "dynamicRegistration": True,
                                "willSave": True,
                                "willSaveWaitUntil": True,
                                "didSave": True,
                            },
                            "completion": {
                                "dynamicRegistration": True,
                                "completionItem": {
                                    "snippetSupport": True,
                                    "commitCharactersSupport": True,
                                    "documentationFormat": ["markdown", "plaintext"],
                                    "deprecatedSupport": True,
                                    "preselectSupport": True,
                                },
                                "completionItemKind": {"valueSet": list(range(1, 26))},
                            },
                            "hover": {
                                "dynamicRegistration": True,
                                "contentFormat": ["markdown", "plaintext"],
                            },
                            "definition": {"dynamicRegistration": True},
                            "references": {"dynamicRegistration": True},
                            "implementation": {"dynamicRegistration": True},
                            "typeDefinition": {"dynamicRegistration": True},
                        },
                    },
                    "initializationOptions": {
                        "analysis": {
                            "autoSearchPaths": True,
                            "useLibraryCodeForTypes": True,
                            "diagnosticMode": "workspace",
                            "typeCheckingMode": "basic",
                            "pythonVersion": self.python_version,
                            "extraPaths": [str(self.workspace_path)],
                            "stubPath": str(self.workspace_path),
                        }
                    },
                },
            }

            logger.debug(
                f"Sending initialization request: {json.dumps(init_params, indent=2)}"
            )

            if not self.server_process or not self.server_process.stdin:
                logger.error("Server process or stdin not available")
                return False

            # Send initialization request
            json.dump(init_params, self.server_process.stdin)
            self.server_process.stdin.write("\n")
            self.server_process.stdin.flush()

            # Wait for response with increased timeout
            response = await asyncio.wait_for(self._read_response(), timeout=60.0)
            if not response or "error" in response:
                logger.error(f"Initialization failed: {response}")
                return False

            # Send configuration after successful initialization
            config_notification = {
                "jsonrpc": "2.0",
                "method": "workspace/didChangeConfiguration",
                "params": {
                    "settings": {
                        "python": {
                            "analysis": {
                                "autoSearchPaths": True,
                                "useLibraryCodeForTypes": True,
                                "typeCheckingMode": "basic",
                                "diagnosticMode": "workspace",
                                "pythonVersion": self.python_version,
                                "extraPaths": [str(self.workspace_path)],
                                "stubPath": str(self.workspace_path),
                            },
                            "pythonPath": sys.executable,
                            "venvPath": str(Path(self.workspace_path) / ".venv"),
                        }
                    }
                },
            }

            logger.debug(
                f"Sending configuration: {json.dumps(config_notification, indent=2)}"
            )
            json.dump(config_notification, self.server_process.stdin)
            self.server_process.stdin.write("\n")
            self.server_process.stdin.flush()

            logger.info("Server initialization successful")
            return True

        except asyncio.TimeoutError:
            logger.error("Server initialization timed out")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize connection: {str(e)}")
            return False

    # Rest of the class methods remain the same...

    async def lookup_symbol(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """
        Look up symbols in the workspace matching the query.

        Args:
            query: The symbol query string (supports fuzzy matching)

        Returns:
            List of matching symbols with their locations and details
        """
        try:
            if not self.server_process or not self.server_process.stdin:
                logger.error("Server not running")
                return None

            self.request_id += 1
            request = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": "workspace/symbol",
                "params": {"query": query},
            }

            logger.debug(
                f"Sending workspace symbol request: {json.dumps(request, indent=2)}"
            )

            json.dump(request, self.server_process.stdin)
            self.server_process.stdin.write("\n")
            self.server_process.stdin.flush()

            response = await self._read_response()
            if response and "result" in response:
                symbols = response["result"]
                logger.info(f"Found {len(symbols)} symbols matching '{query}'")

                # Log detailed symbol information for debugging
                for symbol in symbols:
                    logger.debug(f"Symbol found: {json.dumps(symbol, indent=2)}")

                return symbols
            else:
                logger.warning(f"No symbols found matching '{query}'")
                return None

        except Exception as e:
            logger.error(f"Error looking up symbol {query}: {str(e)}")
            return None

    async def get_server_status(self) -> Optional[Dict[str, Any]]:
        """Get workspace status information from the server."""
        try:
            if not self.server_process or not self.server_process.stdin:
                logger.error("Server not running")
                return None

            self.request_id += 1
            request = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": "workspace/workspaceFolders",  # This gets the current workspace folders
                "params": None,
            }

            logger.debug(
                f"Sending workspace status request: {json.dumps(request, indent=2)}"
            )

            json.dump(request, self.server_process.stdin)
            self.server_process.stdin.write("\n")
            self.server_process.stdin.flush()

            response = await self._read_response()
            if response:
                logger.info(f"Workspace status: {json.dumps(response, indent=2)}")
                return response
            return None
        except Exception as e:
            logger.error(f"Error getting server status: {str(e)}")
            return None

    async def _read_response(self, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """Read and parse response from the server with proper LSP message handling."""
        try:
            if not self.server_process or not self.server_process.stdout:
                return None

            response_received = asyncio.Event()
            response_data = {"headers": {}, "content": None}

            async def read_stdout():
                try:
                    # Read headers
                    while True:
                        line = await asyncio.get_event_loop().run_in_executor(
                            None, self.server_process.stdout.readline
                        )
                        line = line.strip()

                        # Empty line signals end of headers
                        if not line:
                            break

                        # Parse header
                        if ":" in line:
                            key, value = line.split(":", 1)
                            response_data["headers"][key.strip()] = value.strip()

                    # Get content length from headers
                    content_length = int(
                        response_data["headers"].get("Content-Length", 0)
                    )
                    if content_length:
                        # Read exact number of bytes for the content
                        content = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: self.server_process.stdout.read(content_length),
                        )
                        response_data["content"] = content
                        response_received.set()

                except Exception as e:
                    logger.error(f"Error reading from stdout: {str(e)}")

            # Start reading task with timeout
            read_task = asyncio.create_task(read_stdout())
            try:
                await asyncio.wait_for(response_received.wait(), timeout)
            except asyncio.TimeoutError:
                logger.error(
                    f"Timeout waiting for server response after {timeout} seconds"
                )
                self._log_pyright_server_output()
                return None
            finally:
                read_task.cancel()

            if response_data["content"]:
                try:
                    return json.loads(response_data["content"])
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse server response: {str(e)}")
                    logger.debug(f"Raw headers: {response_data['headers']}")
                    logger.debug(f"Raw content: {response_data['content']}")
                    return None
            return None

        except Exception as e:
            logger.error(f"Error reading server response: {str(e)}")
            logger.debug("Current response data:", response_data)
            return None

    def _log_pyright_server_output(self):
        """Read and log the current contents of the pyright server log file."""
        try:
            with open(self.log_file.name, "r") as f:
                logs = f.read()
                logger.debug("=== Pyright Server Logs ===")
                logger.debug(logs)
                logger.debug("==========================")
        except Exception as e:
            logger.error(f"Failed to read pyright server logs: {str(e)}")

    async def shutdown(self):
        """Cleanly shut down the pyright server."""
        try:
            if self.server_process:
                # Send shutdown request
                shutdown_request = {
                    "jsonrpc": "2.0",
                    "id": self.request_id + 1,
                    "method": "shutdown",
                }
                json.dump(shutdown_request, self.server_process.stdin)
                self.server_process.stdin.write("\n")
                self.server_process.stdin.flush()

                # Wait briefly for shutdown acknowledgment
                await asyncio.sleep(1)

                # Send exit notification
                exit_notification = {"jsonrpc": "2.0", "method": "exit"}
                json.dump(exit_notification, self.server_process.stdin)
                self.server_process.stdin.write("\n")
                self.server_process.stdin.flush()

                # Log final server output before shutting down
                self._log_pyright_server_output()

                # Terminate process if it hasn't exited
                await asyncio.sleep(1)
                if self.server_process.poll() is None:
                    self.server_process.terminate()
                    await asyncio.sleep(1)
                    if self.server_process.poll() is None:
                        self.server_process.kill()

                # Clean up log file
                try:
                    os.unlink(self.log_file.name)
                except Exception as e:
                    logger.warning(f"Failed to clean up log file: {str(e)}")

                logger.info("Server shutdown complete")

        except Exception as e:
            logger.error(f"Error during server shutdown: {str(e)}")
            if self.server_process and self.server_process.poll() is None:
                self.server_process.kill()


# Example usage
async def main():
    # Initialize with your workspace path
    lookup = PyrightSymbolLookup("/Users/phil/dev/mcp-python-helper")

    try:
        # Start server and initialize connection
        if not await lookup.start_server():
            logger.error("Failed to start server")
            return

        if not await lookup.initialize_connection():
            logger.error("Failed to initialize connection")
            return

        document_notification = {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": f"file://{lookup.workspace_path}/example.py",
                    "languageId": "python",
                    "version": 1,
                    "text": Path("example.py").read_text(),
                }
            },
        }

        logger.debug(
            f"Sending document open notification: {json.dumps(document_notification, indent=2)}"
        )
        json.dump(document_notification, lookup.server_process.stdin)
        lookup.server_process.stdin.write("\n")
        lookup.server_process.stdin.flush()

        status = await lookup.get_server_status()
        print("Server status:", status)
        # Look up symbols
        symbols = await lookup.lookup_symbol("")

        if symbols:
            print("Found symbols:")
            for symbol in symbols:
                print(f"\nName: {symbol.get('name')}")
                print(f"Kind: {symbol.get('kind')}")
                if "location" in symbol:
                    loc = symbol["location"]
                    print(f"File: {loc.get('uri', '').replace('file://', '')}")
                    if "range" in loc:
                        start = loc["range"]["start"]
                        print(
                            f"Line: {start.get('line')}, Character: {start.get('character')}"
                        )
        else:
            print("No symbols found")

    finally:
        # Clean up
        await lookup.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
