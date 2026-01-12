"""Stdio-proxy: TCP to STDIO bridge for MCP webhook server.

This module implements an asyncio-based TCP proxy that forwards bytes
between TCP clients and a child MCP server process running on STDIO.

Key features:
- Accepts TCP connections on a configurable port
- Spawns MCP server as subprocess with piped STDIO
- Bidirectional byte forwarding (TCP <-> STDIO)
- Graceful shutdown handling
- Structured logging
"""

import asyncio
import logging
import signal
from typing import Optional

from mcp_webhook.config import get_settings


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class StdioProxy:
    """TCP to STDIO proxy for MCP server.

    This class manages:
    - TCP server listening on configured port
    - Child MCP server subprocess
    - Bidirectional byte forwarding
    - Graceful shutdown
    """

    def __init__(self) -> None:
        """Initialize proxy with configuration."""
        self.settings = get_settings()
        self.server: Optional[asyncio.Server] = None
        self.server_process: Optional[asyncio.subprocess.Process] = None
        self.shutdown_event = asyncio.Event()
        self._logger = logger

    async def forward(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, name: str) -> None:
        """Forward bytes from reader to writer.

        Args:
            reader: Source stream to read from
            writer: Destination stream to write to
            name: Descriptive name for logging
        """
        try:
            while not self.shutdown_event.is_set():
                data = await reader.read(4096)
                if not data:
                    self._logger.debug(f"{name}: Connection closed (EOF)")
                    break
                writer.write(data)
                await writer.drain()
                self._logger.debug(f"{name}: Forwarded {len(data)} bytes")
        except asyncio.CancelledError:
            self._logger.debug(f"{name}: Forward cancelled")
        except ConnectionResetError:
            self._logger.warning(f"{name}: Connection reset by peer")
        except Exception as e:
            self._logger.error(f"{name}: Error forwarding data: {e}", exc_info=True)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                self._logger.error(f"{name}: Error closing writer: {e}")

    async def handle_client(self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
        """Handle a single TCP client connection.

        This method:
        - Ensures server process is running
        - Sets up bidirectional forwarding between client and server
        - Handles connection closure and cleanup

        Args:
            client_reader: Stream reader for TCP client
            client_writer: Stream writer for TCP client
        """
        client_addr = client_writer.get_extra_info("peername")
        self._logger.info(f"Client connected: {client_addr}")

        try:
            # Ensure server process is running
            if self.server_process is None or self.server_process.returncode is not None:
                await self.start_server_process()

            if self.server_process is None or self.server_process.returncode is not None:
                self._logger.error("Failed to start server process")
                client_writer.close()
                await client_writer.wait_closed()
                return

            # Check if stdin is still available
            if self.server_process.stdin is None or self.server_process.stdin.is_closing():
                self._logger.error("Server process stdin is closed, cannot communicate")
                client_writer.close()
                await client_writer.wait_closed()
                return

            # Set up bidirectional forwarding
            # Client -> Server stdin
            client_to_server = asyncio.create_task(
                self.forward(client_reader, self.server_process.stdin, f"{client_addr}->server"),
            )

            # Server stdout -> Client
            server_to_client = asyncio.create_task(
                self.forward(self.server_process.stdout, client_writer, f"server->{client_addr}"),
            )

            # Wait for either direction to complete
            done, pending = await asyncio.wait(
                [client_to_server, server_to_client],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            self._logger.info(f"Client disconnected: {client_addr}")

        except Exception as e:
            self._logger.error(f"Error handling client {client_addr}: {e}", exc_info=True)
        finally:
            try:
                client_writer.close()
                await client_writer.wait_closed()
            except Exception:
                pass

    async def start_server_process(self) -> None:
        """Start MCP server as a subprocess with piped STDIO.

        The server is started using the Python module mcp_webhook.server
        and will communicate via STDIO. Stderr is captured for logging.
        """
        # Check if server process is already running
        if self.server_process is not None and self.server_process.returncode is None:
            self._logger.debug(f"MCP server process already running with PID: {self.server_process.pid}")
            return

        self._logger.info("Starting MCP server process...")

        # Build command to start MCP server
        cmd = ["python", "-m", "mcp_webhook.server"]

        try:
            self.server_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            self._logger.info(f"MCP server process started with PID: {self.server_process.pid}")

            # Start task to log server stderr
            asyncio.create_task(self._log_server_stderr())

        except Exception as e:
            self._logger.error(f"Failed to start server process: {e}", exc_info=True)
            raise

    async def _log_server_stderr(self) -> None:
        """Log server stderr output."""
        if self.server_process is None:
            return

        try:
            while True:
                line = await self.server_process.stderr.readline()
                if not line:
                    break
                # Decode line and log it
                try:
                    line_str = line.decode("utf-8").rstrip()
                    self._logger.info(f"[SERVER] {line_str}")
                except UnicodeDecodeError:
                    self._logger.info(f"[SERVER] <binary data: {len(line)} bytes>")
        except Exception as e:
            self._logger.error(f"Error reading server stderr: {e}", exc_info=True)

    async def run(self) -> None:
        """Run the TCP proxy server.

        This method:
        - Starts MCP server subprocess
        - Creates TCP listener on configured port
        - Accepts client connections and handles them
        - Handles shutdown signals
        """
        self._logger.info(f"Starting stdio-proxy on port {self.settings.port}")

        # Start MCP server process
        await self.start_server_process()

        # Create TCP server
        self.server = await asyncio.start_server(
            self.handle_client,
            host="0.0.0.0",
            port=self.settings.port,
        )

        # Log listening address
        addr = self.server.sockets[0].getsockname()
        self._logger.info(f"Proxy listening on {addr}")

        # Set up signal handlers for graceful shutdown
        # Note: Signal handlers are not supported on Windows
        loop = asyncio.get_running_loop()
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(
                    sig,
                    lambda s=sig: asyncio.create_task(self.shutdown(s)),
                )
        except NotImplementedError:
            # Windows doesn't support signal handlers
            # Shutdown will be handled via task cancellation or external process termination
            self._logger.info("Signal handlers not available on this platform")

        # Serve until shutdown
        async with self.server:
            await self.server.serve_forever()

    async def shutdown(self, signal: Optional[signal.Signals] = None) -> None:
        """Gracefully shutdown the proxy and server process.

        Args:
            signal: The signal that triggered shutdown (if any)
        """
        if signal:
            self._logger.info(f"Received signal {signal.name}, shutting down...")

        self.shutdown_event.set()

        # Stop accepting new connections
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self._logger.info("Proxy server closed")

        # Terminate server process
        if self.server_process and self.server_process.returncode is None:
            self._logger.info("Stopping MCP server process...")
            self.server_process.terminate()

            try:
                await asyncio.wait_for(self.server_process.wait(), timeout=5.0)
                self._logger.info("MCP server process terminated gracefully")
            except asyncio.TimeoutError:
                self._logger.warning("MCP server process did not terminate, killing...")
                self.server_process.kill()
                await self.server_process.wait()
                self._logger.info("MCP server process killed")

        self._logger.info("Proxy shutdown complete")


async def main() -> None:
    """Main entry point for the stdio-proxy."""
    proxy = StdioProxy()
    try:
        await proxy.run()
    except Exception as e:
        logger.error(f"Proxy error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Proxy interrupted")
