"""
Example MCP STDIO Client

This example demonstrates how to connect to the MCP STDIO Webhook Server
via the stdio-proxy TCP endpoint and send properly framed MCP messages.

Usage:
    python examples/stdio_client.py --help
    python examples/stdio_client.py --event file.save --path /repo/file.py
    python examples/stdio_client.py --event file.open --file /repo/other.py --auth token1
"""

import argparse
import asyncio
import json
import struct
import sys
from pathlib import Path
from typing import Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp_webhook.envelope import Envelope


class MCPFramingError(Exception):
    """Raised when there's an error with MCP message framing."""
    pass


class MCPClient:
    """A client for connecting to MCP servers over TCP with proper framing."""

    def __init__(self, host: str = "localhost", port: int = 9000):
        """Initialize the MCP client.

        Args:
            host: The host to connect to
            port: The port to connect to
        """
        self.host = host
        self.port = port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.request_id = 0

    async def connect(self) -> None:
        """Connect to the MCP server."""
        try:
            self.reader, self.writer = await asyncio.open_connection(
                self.host, self.port
            )
            print(f"✓ Connected to {self.host}:{self.port}")
        except ConnectionRefusedError:
            raise MCPFramingError(
                f"Could not connect to {self.host}:{self.port}. "
                f"Ensure the server is running (docker-compose up --build)"
            )

    async def close(self) -> None:
        """Close the connection."""
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
            print("✓ Connection closed")

    @staticmethod
    def _pack_message(message: dict) -> bytes:
        """Pack a message with MCP framing (4-byte length prefix).

        Args:
            message: The message dict to pack

        Returns:
            Framed message bytes
        """
        json_str = json.dumps(message, ensure_ascii=False)
        json_bytes = json_str.encode("utf-8")
        length = len(json_bytes)
        return struct.pack("<I", length) + json_bytes

    @staticmethod
    def _unpack_message(data: bytes) -> dict:
        """Unpack a framed message.

        Args:
            data: The raw bytes to unpack

        Returns:
            The unpacked message dict
        """
        if len(data) < 4:
            raise MCPFramingError("Message too short for length prefix")

        length = struct.unpack("<I", data[:4])[0]
        if len(data) < 4 + length:
            raise MCPFramingError(
                f"Incomplete message: expected {length} bytes, "
                f"got {len(data) - 4}"
            )

        json_bytes = data[4:4 + length]
        return json.loads(json_bytes.decode("utf-8"))

    async def _send_message(self, message: dict) -> None:
        """Send a framed message to the server.

        Args:
            message: The message dict to send
        """
        if not self.writer:
            raise MCPFramingError("Not connected to server")

        framed = self._pack_message(message)
        self.writer.write(framed)
        await self.writer.drain()

    async def _receive_message(self) -> dict:
        """Receive a framed message from the server.

        Returns:
            The received message dict
        """
        if not self.reader:
            raise MCPFramingError("Not connected to server")

        # Read length prefix
        length_data = await self.reader.readexactly(4)
        length = struct.unpack("<I", length_data)[0]

        # Read message payload
        message_data = await self.reader.readexactly(length)
        return json.loads(message_data.decode("utf-8"))

    async def initialize(self) -> dict:
        """Initialize the MCP session.

        Returns:
            The server's initialization response
        """
        print("Sending initialize request...")
        self.request_id += 1

        init_request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "example-stdio-client",
                    "version": "1.0.0"
                }
            }
        }

        await self._send_message(init_request)
        response = await self._receive_message()
        print(f"✓ Initialized: {json.dumps(response, indent=2)}")
        return response

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool.

        Args:
            tool_name: The name of the tool to call
            arguments: Tool arguments as a dict

        Returns:
            The tool result
        """
        print(f"\nCalling tool: {tool_name}")
        print(f"Arguments: {json.dumps(arguments, indent=2)}")

        self.request_id += 1

        tool_request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        await self._send_message(tool_request)
        response = await self._receive_message()

        if "error" in response:
            print(f"✗ Error: {json.dumps(response['error'], indent=2)}")
            raise MCPFramingError(f"Tool call failed: {response['error']}")

        result = response.get("result", {})
        print(f"✓ Result: {json.dumps(result, indent=2)}")
        return result

    async def send_envelope(
        self,
        event_type: str,
        payload: dict,
        auth: Optional[str] = None
    ) -> dict:
        """Send an event envelope via the envelope_router tool.

        Args:
            event_type: The event type (e.g., "file.save")
            payload: The event payload
            auth: Optional bearer token for authentication

        Returns:
            The result from processing the envelope
        """
        # Create envelope
        envelope_dict = {
            "type": "event",
            "event_type": event_type,
            "payload": payload,
            "meta": {
                "auth": auth,
                "id": f"example-{asyncio.get_event_loop().time()}",
                "timestamp": asyncio.get_event_loop().time()
            }
        }

        # Send via envelope_router tool
        arguments = {
            "envelope": envelope_dict
        }

        return await self.call_tool("envelope_router", arguments)

    async def list_recent_events(self) -> dict:
        """List recent processed events.

        Returns:
            Recent events list
        """
        print("\nListing recent events...")
        result = await self.call_tool("list_recent_events", {})
        return result


async def main():
    """Main entry point for the example client."""
    parser = argparse.ArgumentParser(
        description="Example MCP STDIO Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Send a file.save event
  python stdio_client.py --event file.save --path /repo/file.py --auth token1

  # Send a file.open event
  python stdio_client.py --event file.open --file /repo/other.py

  # List recent events
  python stdio_client.py --list-events

  # Custom envelope
  python stdio_client.py --event custom --data '{"key":"value"}' --auth mytoken
        """
    )

    parser.add_argument(
        "--host",
        default="localhost",
        help="Server host (default: localhost)"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=9000,
        help="Server port (default: 9000)"
    )

    parser.add_argument(
        "--event",
        help="Event type to send (e.g., file.save, file.open)"
    )

    parser.add_argument(
        "--path",
        help="File path (for file.save events)"
    )

    parser.add_argument(
        "--file",
        help="File path (for file.open events)"
    )

    parser.add_argument(
        "--auth",
        help="Bearer token for authentication"
    )

    parser.add_argument(
        "--list-events",
        action="store_true",
        help="List recent events instead of sending a new event"
    )

    parser.add_argument(
        "--data",
        help="Custom payload as JSON string"
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.list_events and not args.event:
        parser.error("Either --event or --list-events is required")

    client = MCPClient(host=args.host, port=args.port)

    try:
        # Connect to server
        await client.connect()

        # Initialize session
        await client.initialize()

        # Execute requested action
        if args.list_events:
            # List recent events
            result = await client.list_recent_events()
            events = result.get("events", [])
            if events:
                print(f"\nRecent events ({len(events)}):")
                for i, event in enumerate(events, 1):
                    print(f"  {i}. {event.get('event_type', 'unknown')} "
                          f"at {event.get('timestamp', 'N/A')}")
            else:
                print("\nNo recent events found")
        else:
            # Build payload based on event type
            payload = {}

            if args.data:
                # Use custom JSON payload
                payload = json.loads(args.data)
            elif args.event == "file.save" and args.path:
                # file.save payload
                payload = {
                    "path": args.path,
                    "user": {"id": "example-user"}
                }
            elif args.event == "file.open" and args.file:
                # file.open payload
                payload = {
                    "path": args.file,
                    "user": {"id": "example-user"}
                }
            else:
                # Generic payload
                payload = {
                    "source": "example-client",
                    "timestamp": asyncio.get_event_loop().time()
                }

            # Send envelope
            result = await client.send_envelope(
                event_type=args.event,
                payload=payload,
                auth=args.auth
            )

            print(f"\n✓ Envelope processed successfully")
            print(f"Status: {result.get('status', 'unknown')}")

    except json.JSONDecodeError as e:
        print(f"✗ JSON decode error: {e}", file=sys.stderr)
        sys.exit(1)
    except MCPFramingError as e:
        print(f"✗ MCP framing error: {e}", file=sys.stderr)
        sys.exit(1)
    except ConnectionRefusedError as e:
        print(f"✗ Connection refused: {e}", file=sys.stderr)
        print("  Make sure the server is running: docker-compose up --build", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
