import sys
import subprocess
import json
import logging
import asyncio
import os
from pathlib import Path
import signal

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("pyright_debug")

read_fd, write_fd = os.pipe()  # pipe for sending to LSP
lsp_read_fd, lsp_write_fd = os.pipe()  # pipe for receiving from LSP

# Create file objects for your end of the pipes
write_pipe = os.fdopen(write_fd, "wb")
read_pipe = os.fdopen(lsp_read_fd, "rb")


async def test_diagnostics():
    # Start server with binary mode
    process = subprocess.Popen(
        ["pyright-langserver", "--stdio", "--verbose"],
        # stdin=subprocess.PIPE,
        # stdout=subprocess.PIPE,
        stdin=read_fd,
        stdout=lsp_write_fd,
        stderr=subprocess.PIPE,  # not sure if I should make pipe for this too
        bufsize=0,  # Unbuffered
    )

    def encode_message(msg):
        content = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(content)}\r\n\r\n".encode("utf-8")
        return header + content

    async def write_message(msg):
        encoded = encode_message(msg)
        logger.debug(f"-> {msg.get('method', 'response')}")
        # process.stdin.write(encoded)
        # process.stdin.flush()
        write_pipe.write(encoded)
        write_pipe.flush()
        await asyncio.sleep(0.1)

    async def read_message():
        try:
            # Read headers
            header = b""
            while b"\r\n\r\n" not in header:
                next_char = await asyncio.get_event_loop().run_in_executor(
                    # None, lambda: process.stdout.read(1)
                    None,
                    lambda: read_pipe.read(1),
                )
                if not next_char:
                    return None
                header += next_char

            # Parse content length
            header_str = header.decode("utf-8")
            content_length = int(header_str.split(":")[1].strip())

            # Read content
            content = await asyncio.get_event_loop().run_in_executor(
                # None, lambda: process.stdout.read(content_length)
                None,
                lambda: read_pipe.read(content_length),
            )

            try:
                msg = json.loads(content.decode("utf-8"))
                logger.debug(
                    f"<- {msg.get('method', 'response')}: {json.dumps(msg, indent=2)}"
                )
                return msg
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
                logger.error(f"Raw content: {content}")
                return None

        except Exception as e:
            logger.error(f"Error reading: {e}")
            return None

    async def handle_server_request(msg):
        method = msg.get("method")
        msg_id = msg.get("id")

        if method == "client/registerCapability":
            await write_message({"jsonrpc": "2.0", "id": msg_id, "result": None})

        elif method == "workspace/configuration":
            await write_message(
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

    try:
        # Initialize
        await write_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "processId": os.getpid(),
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                    "rootPath": str(Path.cwd()),
                    "rootUri": f"file://{Path.cwd()}",
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
                        {"uri": f"file://{Path.cwd()}", "name": "test-workspace"}
                    ],
                },
            }
        )

        # Handle initialization
        while True:
            msg = await read_message()
            if not msg:
                continue
            if msg.get("id") == 1 and "result" in msg:
                break
            elif "method" in msg and "id" in msg:
                await handle_server_request(msg)

        # Send initialized
        await write_message({"jsonrpc": "2.0", "method": "initialized", "params": {}})

        # Configure settings
        await write_message(
            {
                "jsonrpc": "2.0",
                "method": "workspace/didChangeConfiguration",
                "params": {
                    "settings": {
                        "python": {
                            "analysis": {
                                "autoSearchPaths": True,
                                "diagnosticMode": "workspace",
                                "typeCheckingMode": "basic",
                                "useLibraryCodeForTypes": True,
                            }
                        }
                    }
                },
            }
        )

        # Open document
        doc_uri = f"file://{Path('example.py').absolute()}"
        doc_content = Path("example.py").read_text()

        await write_message(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": doc_uri,
                        "languageId": "python",
                        "version": 1,
                        "text": doc_content,
                    }
                },
            }
        )

        logger.info("Waiting for messages (30 sec timeout)...")

        # Read messages with timeout
        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) < 30:
            if process.poll() is not None:
                stderr = process.stderr.read()
                logger.error(f"Process exited with code {process.poll()}")
                if stderr:
                    logger.error(f"Stderr: {stderr}")
                break

            msg = await read_message()
            if not msg:
                await asyncio.sleep(0.1)
                continue

            # Handle server requests
            if "method" in msg and "id" in msg:
                await handle_server_request(msg)
                continue

            if msg.get("method") == "textDocument/publishDiagnostics":
                logger.info("Got diagnostics!")
                logger.info(json.dumps(msg, indent=2))
                return

            logger.debug(f"Got message: {json.dumps(msg, indent=2)}")

    finally:
        logger.info("Cleaning up...")
        if process.poll() is None:
            try:
                await write_message({"jsonrpc": "2.0", "id": 99, "method": "shutdown"})
                await write_message({"jsonrpc": "2.0", "method": "exit"})
                await asyncio.sleep(1)
                if process.poll() is None:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    process.wait(timeout=5)
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except:
                    pass


if __name__ == "__main__":
    asyncio.run(test_diagnostics())
