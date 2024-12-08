import asyncio
import logging
import json
import sys
from typing import Dict, Any, List
from pathlib import Path

from pylsp_jsonrpc.streams import JsonRpcStreamWriter


class CustomJsonRpcStreamReader:
    def __init__(self, rfile):
        self._rfile = rfile
        self._buffer = ""
        self._message_queue = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self.logger = logging.getLogger("LSPClient.StreamReader")

    async def listen(self, message_consumer):
        try:
            while not self._stop_event.is_set():
                try:
                    self.logger.debug("Waiting for header...")
                    header = await self._read_header()
                    if not header:
                        self.logger.warning("No header received, breaking loop")
                        break

                    content_length = self._get_content_length(header)
                    if content_length is None:
                        self.logger.warning("No content length in header")
                        continue

                    self.logger.debug(f"Reading content with length: {content_length}")
                    content = await self._rfile.read(content_length)
                    if not content:
                        self.logger.warning("No content received")
                        break

                    message = json.loads(content.decode("utf-8"))
                    self.logger.debug(f"Received message: {message}")
                    message_consumer(message)
                except Exception as e:
                    self.logger.error(f"Error reading message: {e}", exc_info=True)
                    break
        except Exception as e:
            self.logger.error(f"Error in listen loop: {e}", exc_info=True)

    async def _read_header(self):
        header = []
        while True:
            line = await self._rfile.readline()
            if not line:
                return None

            line = line.decode("utf-8").strip()
            if not line:
                break
            header.append(line)
            self.logger.debug(f"Header line: {line}")
        return header

    def _get_content_length(self, header):
        for line in header:
            if line.startswith("Content-Length: "):
                return int(line.split(": ")[1])
        return None

    def stop(self):
        self._stop_event.set()


class CustomJsonRpcStreamWriter:
    def __init__(self, wfile):
        self._wfile = wfile
        self._encoder = json.JSONEncoder()
        self.logger = logging.getLogger("LSPClient.StreamWriter")

    async def write(self, message):
        try:
            self.logger.debug(f"Writing message: {message}")
            body = self._encoder.encode(message)
            content_length = len(body.encode("utf-8"))
            response = (
                f"Content-Length: {content_length}\r\n"
                f"Content-Type: application/vscode-jsonrpc; charset=utf-8\r\n"
                f"\r\n"
                f"{body}"
            )
            self._wfile.write(response.encode("utf-8"))
            await self._wfile.drain()
            self.logger.debug("Message written successfully")
        except Exception as e:
            self.logger.error(f"Error writing to stream: {e}", exc_info=True)
            raise


class LSPClient:
    def __init__(self):
        self.server_process = None
        self.writer = None
        self.reader = None
        self.request_id = 0
        self._response_futures = {}
        self.logger = logging.getLogger("LSPClient.LSPClient")

    async def start_server(self):
        """Start the LSP server process."""
        try:
            self.logger.info("Starting LSP server...")
            self.server_process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pylsp",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            if self.server_process.stdin is None or self.server_process.stdout is None:
                raise RuntimeError("Failed to establish subprocess pipes")

            self.reader = CustomJsonRpcStreamReader(self.server_process.stdout)
            self.writer = CustomJsonRpcStreamWriter(self.server_process.stdin)

            # Start error output monitoring
            self._stderr_task = asyncio.create_task(self._monitor_stderr())

            # Start message handling task
            self._message_task = asyncio.create_task(
                self.reader.listen(self._handle_message)
            )

            self.logger.info("Initializing LSP server...")
            # Initialize the LSP server
            init_response = await self.initialize()
            self.logger.info(f"Server initialized with response: {init_response}")

            return init_response
        except Exception as e:
            self.logger.error(f"Error starting server: {e}", exc_info=True)
            await self.close()
            raise

    async def _monitor_stderr(self):
        """Monitor the server's stderr for debugging purposes."""
        while True:
            if self.server_process.stderr:
                line = await self.server_process.stderr.readline()
                if line:
                    self.logger.warning(f"LSP Server stderr: {line.decode().strip()}")
                else:
                    break

    def _handle_message(self, message):
        self.logger.debug(f"Handling message: {message}")
        if "id" in message and message["id"] in self._response_futures:
            future = self._response_futures.pop(message["id"])
            if not future.done():
                if "error" in message:
                    self.logger.error(f"Error in response: {message['error']}")
                    future.set_exception(Exception(f"LSP error: {message['error']}"))
                else:
                    self.logger.debug(f"Setting result for request {message['id']}")
                    future.set_result(message.get("result", {}))

    async def initialize(self):
        """Initialize the LSP connection."""
        params = {
            "processId": None,
            "rootUri": str(Path.cwd().as_uri()),
            "capabilities": {
                "textDocument": {
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                    "definition": True,
                    "references": True,
                    "completion": {"completionItem": {"snippetSupport": True}},
                }
            },
        }

        response = await self.send_request("initialize", params)
        await self.send_notification("initialized", {})
        return response

    async def send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a request to the LSP server and wait for the response."""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }

        self.logger.debug(f"Sending request {self.request_id}: {method}")
        self.logger.debug(f"Parameters: {params}")

        # Create a future for this request
        future = asyncio.Future()
        self._response_futures[self.request_id] = future

        # Send the request
        await self.writer.write(request)

        try:
            response = await asyncio.wait_for(future, timeout=5.0)
            self.logger.debug(
                f"Received response for request {self.request_id}: {response}"
            )
            return response
        except asyncio.TimeoutError:
            self.logger.error(
                f"Timeout waiting for response to request {self.request_id}"
            )
            self._response_futures.pop(self.request_id, None)
            return {}
        except Exception as e:
            self.logger.error(
                f"Error processing request {self.request_id}: {e}", exc_info=True
            )
            return {}

    async def send_notification(self, method: str, params: Dict[str, Any]):
        """Send a notification to the LSP server."""
        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        await self.writer.write(notification)

    async def get_hover_info(self, file_path: str, line: int, character: int) -> str:
        """Get hover information for a specific position in a file."""
        params = {
            "textDocument": {"uri": str(Path(file_path).absolute().as_uri())},
            "position": {"line": line, "character": character},
        }

        response = await self.send_request("textDocument/hover", params)
        print(response)
        if "contents" in response:
            if isinstance(response["contents"], dict):
                return response["contents"].get(
                    "value", "No hover information available"
                )
            return str(response["contents"])
        return "No hover information available"

    async def get_definitions(
        self, file_path: str, line: int, character: int
    ) -> List[Dict[str, Any]]:
        """Get definitions for a symbol at a specific position."""
        params = {
            "textDocument": {"uri": str(Path(file_path).absolute().as_uri())},
            "position": {"line": line, "character": character},
        }

        return await self.send_request("textDocument/definition", params)

    async def get_references(
        self, file_path: str, line: int, character: int
    ) -> List[Dict[str, Any]]:
        """Get all references to a symbol at a specific position."""
        params = {
            "textDocument": {"uri": str(Path(file_path).absolute().as_uri())},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": True},
        }

        return await self.send_request("textDocument/references", params)

    async def initialize(self):
        """Initialize the LSP connection."""
        params = {
            "processId": None,
            "rootUri": str(Path.cwd().as_uri()),
            "capabilities": {
                "textDocument": {
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                    "definition": True,
                    "references": True,
                    "completion": {"completionItem": {"snippetSupport": True}},
                }
            },
        }

        response = await self.send_request("initialize", params)
        await self.send_notification("initialized", {})
        return response

    async def did_open(self, file_path: str):
        """Notify the server that a file has been opened."""
        with open(file_path, "r") as f:
            text = f.read()

        params = {
            "textDocument": {
                "uri": str(Path(file_path).absolute().as_uri()),
                "languageId": "python",
                "version": 1,
                "text": text,
            }
        }

        self.logger.info(f"Sending textDocument/didOpen for {file_path}")
        await self.send_notification("textDocument/didOpen", params)

    async def close(self):
        """Properly shut down the LSP server."""
        try:
            if hasattr(self, "_message_task"):
                self.reader.stop()
                await self._message_task

            if self.server_process:
                await self.send_request("shutdown", None)
                await self.send_notification("exit", None)
                self.server_process.terminate()
                await self.server_process.wait()
        except Exception as e:
            print(f"Error during shutdown: {e}")


async def main():
    # Example usage
    client = LSPClient()
    await client.start_server()

    # Example file path - replace with your actual Python file
    file_path = "example.py"

    try:
        # First, notify the server that we're opening the file
        await client.did_open(file_path)

        # Wait a moment for the server to process the file
        await asyncio.sleep(1)

        # Get hover information for a symbol
        hover_info = await client.get_hover_info(file_path, 6, 0)
        print(f"Hover information: {hover_info}")

        # Get definitions
        definitions = await client.get_definitions(file_path, 6, 0)
        print(f"Definitions: {definitions}")

        # Get references
        references = await client.get_references(file_path, 7, 0)
        print(f"References: {references}")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())

