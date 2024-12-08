import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, AsyncIterator
from dataclasses import dataclass

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@dataclass
class Position:
    line: int
    character: int


@dataclass
class Range:
    start: Position
    end: Position


@dataclass
class Location:
    uri: str
    range: Range


@dataclass
class SymbolInformation:
    name: str
    kind: int
    location: Location
    container_name: Optional[str] = None

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "SymbolInformation":
        return SymbolInformation(
            name=data["name"],
            kind=data["kind"],
            location=Location(
                uri=data["location"]["uri"],
                range=Range(
                    start=Position(**data["location"]["range"]["start"]),
                    end=Position(**data["location"]["range"]["end"]),
                ),
            ),
            container_name=data.get("containerName"),
        )


class LSPProtocolReader:
    def __init__(self, reader: asyncio.StreamReader):
        self.reader = reader

    async def read_message(self) -> Optional[Dict[str, Any]]:
        """Read a single LSP message."""
        try:
            # Read headers
            content_length = None
            while True:
                header = await self.reader.readline()
                if not header:
                    return None

                header = header.decode("utf-8").strip()
                if not header:
                    break

                if header.startswith("Content-Length: "):
                    content_length = int(header.split(": ")[1])

            if content_length is None:
                logger.warning("No Content-Length header found")
                return None

            # Read content
            content = await self.reader.readexactly(content_length)
            return json.loads(content.decode("utf-8"))

        except asyncio.IncompleteReadError:
            logger.error("Connection closed while reading")
            return None
        except Exception as e:
            logger.error(f"Error reading message: {e}")
            return None


class LSPProtocolWriter:
    def __init__(self, writer: asyncio.StreamWriter):
        self.writer = writer

    async def write_message(self, message: Dict[str, Any]):
        """Write a single LSP message."""
        try:
            body = json.dumps(message)
            content = body.encode("utf-8")
            header = f"Content-Length: {len(content)}\r\n\r\n"

            self.writer.write(header.encode("utf-8"))
            self.writer.write(content)
            await self.writer.drain()

        except Exception as e:
            logger.error(f"Error writing message: {e}")
            raise


class LSPClient:
    def __init__(self):
        self.process = None
        self.reader = None
        self.writer = None
        self.request_id = 0
        self.response_handlers = {}
        self.notification_handlers = {}
        self.initialized = False
        self._message_loop_task = None

    async def start(self, workspace_path: Optional[str] = None):
        """Start the LSP server and initialize the connection."""
        try:
            # Start pylsp process
            self.process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pylsp",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            if not self.process.stdin or not self.process.stdout:
                raise RuntimeError("Failed to start LSP server")

            # Create StreamReader and StreamWriter
            loop = asyncio.get_event_loop()
            transport, protocol = await loop.connect_write_pipe(
                asyncio.Protocol, self.process.stdin
            )
            writer = asyncio.StreamWriter(transport, protocol, None, loop)

            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            await loop.connect_read_pipe(lambda: protocol, self.process.stdout)

            # Create protocol reader/writer
            self.reader = LSPProtocolReader(reader)
            self.writer = LSPProtocolWriter(writer)

            # Start message handling loop
            self._message_loop_task = asyncio.create_task(self._handle_messages())

            # Initialize the server
            workspace_uri = str(Path(workspace_path or Path.cwd()).absolute().as_uri())
            response = await self.send_request(
                "initialize",
                {
                    "processId": None,
                    "rootUri": workspace_uri,
                    "capabilities": {
                        "textDocument": {
                            "hover": {"contentFormat": ["markdown", "plaintext"]},
                            "definition": True,
                            "references": True,
                            "completion": {"completionItem": {"snippetSupport": True}},
                            "documentSymbol": True,
                        }
                    },
                },
            )

            logger.info(f"Server initialized: {response}")
            await self.send_notification("initialized", {})
            self.initialized = True

        except Exception as e:
            logger.error(f"Error starting LSP server: {e}")
            await self.shutdown()
            raise

    async def _handle_messages(self):
        """Handle incoming messages from the LSP server."""
        while True:
            try:
                message = await self.reader.read_message()
                if message is None:
                    break

                logger.debug(f"Received message: {message}")

                if "method" in message:  # This is a request or notification
                    if "id" in message:  # This is a request
                        response = await self._handle_request(message)
                        if response:
                            await self.writer.write_message(response)
                    else:  # This is a notification
                        await self._handle_notification(message)
                elif "id" in message:  # This is a response
                    await self._handle_response(message)

            except Exception as e:
                logger.error(f"Error handling message: {e}")
                break

    async def _handle_request(
        self, request: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Handle incoming requests from the server."""
        method = request["method"]
        handler = self.request_handlers.get(method)
        if handler:
            try:
                result = await handler(request["params"])
                return {"jsonrpc": "2.0", "id": request["id"], "result": result}
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "error": {"code": -32603, "message": str(e)},
                }
        return None

    async def _handle_notification(self, notification: Dict[str, Any]):
        """Handle incoming notifications from the server."""
        method = notification["method"]
        handler = self.notification_handlers.get(method)
        if handler:
            try:
                await handler(notification["params"])
            except Exception as e:
                logger.error(f"Error handling notification {method}: {e}")

    async def _handle_response(self, response: Dict[str, Any]):
        """Handle responses to our requests."""
        response_id = response["id"]
        handler = self.response_handlers.pop(response_id, None)
        if handler:
            if "error" in response:
                handler.set_exception(Exception(f"LSP error: {response['error']}"))
            else:
                handler.set_result(response.get("result"))

    async def send_request(self, method: str, params: Dict[str, Any]) -> Any:
        """Send a request to the LSP server and wait for the response."""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }

        logger.debug(f"Sending request: {request}")
        future = asyncio.Future()
        self.response_handlers[self.request_id] = future

        try:
            await self.writer.write_message(request)
            return await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            logger.error(f"Timeout waiting for response to {method}")
            self.response_handlers.pop(self.request_id, None)
            raise
        except Exception as e:
            logger.error(f"Error sending request {method}: {e}")
            self.response_handlers.pop(self.request_id, None)
            raise

    async def send_notification(self, method: str, params: Dict[str, Any]):
        """Send a notification to the LSP server."""
        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        logger.debug(f"Sending notification: {notification}")
        await self.writer.write_message(notification)

    async def did_open(self, file_path: str):
        """Notify the server that a file has been opened."""
        try:
            uri = str(Path(file_path).absolute().as_uri())
            with open(file_path, "r") as f:
                text = f.read()

            await self.send_notification(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "python",
                        "version": 1,
                        "text": text,
                    }
                },
            )
        except Exception as e:
            logger.error(f"Error opening document {file_path}: {e}")
            raise

    async def get_hover(
        self, file_path: str, line: int, character: int
    ) -> Optional[str]:
        """Get hover information for a position in a file."""
        try:
            uri = str(Path(file_path).absolute().as_uri())
            response = await self.send_request(
                "textDocument/hover",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": line, "character": character},
                },
            )

            if response and "contents" in response:
                contents = response["contents"]
                if isinstance(contents, dict):
                    return contents.get("value")
                elif isinstance(contents, list):
                    return "\n".join(str(c) for c in contents)
                return str(contents)
            return None
        except Exception as e:
            logger.error(f"Error getting hover info: {e}")
            return None

    async def find_references(
        self, file_path: str, line: int, character: int
    ) -> List[Location]:
        """Find all references to a symbol."""
        try:
            uri = str(Path(file_path).absolute().as_uri())
            response = await self.send_request(
                "textDocument/references",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": line, "character": character},
                    "context": {"includeDeclaration": True},
                },
            )

            return [Location(**loc) for loc in response or []]
        except Exception as e:
            logger.error(f"Error finding references: {e}")
            return []

    async def shutdown(self):
        """Shut down the LSP server."""
        try:
            if self.initialized:
                await self.send_request("shutdown", None)
                await self.send_notification("exit", None)

            if self._message_loop_task:
                self._message_loop_task.cancel()
                try:
                    await self._message_loop_task
                except asyncio.CancelledError:
                    pass

            if self.process:
                self.process.terminate()
                await self.process.wait()

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            self.initialized = False


async def main():
    # Example usage
    client = LSPClient()
    try:
        await client.start()

        # Example: Open a file and get hover information
        file_path = __file__  # Use this file as an example
        await client.did_open(file_path)

        # Get hover information for the LSPClient class definition
        hover_info = await client.get_hover(
            file_path, 85, 10
        )  # Adjust line/char as needed
        print(f"\nHover information:\n{hover_info}")

        # Find references
        references = await client.find_references(
            file_path, 85, 10
        )  # Adjust line/char as needed
        print("\nReferences:")
        for ref in references:
            print(f"- {ref.uri}:{ref.range.start.line}:{ref.range.start.character}")

    finally:
        await client.shutdown()


if __name__ == "__main__":
    asyncio.run(main())

