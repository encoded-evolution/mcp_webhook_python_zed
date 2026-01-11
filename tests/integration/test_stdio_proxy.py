"""
End-to-end integration tests for stdio-proxy.

These tests verify the complete TCP -> proxy -> server -> tool -> response flow:
- Starting the proxy (which spawns the MCP server subprocess)
- Connecting via a test TCP client
- Performing MCP protocol handshake (initialize, initialized)
- Calling MCP tools and verifying responses
- Sending event envelopes and verifying routing
- Handling graceful shutdown
"""

import asyncio
import json
import pytest
from typing import Optional
from pytest_asyncio import fixture

from mcp_webhook.config import reset_settings, get_settings


@fixture
def clean_config():
    """Reset settings before each test."""
    reset_settings()
    yield
    reset_settings()


@fixture
async def proxy_with_test_port(clean_config):
    """Create a proxy instance with a test port.

    Uses port 19999 to avoid conflicts with the default 9000 port.
    """
    from mcp_webhook.proxy import StdioProxy

    proxy = StdioProxy()
    # Override port for testing
    proxy.settings.port = 19999
    yield proxy


class MCPProtocolClient:
    """Simple MCP protocol client for testing.

    This client handles MCP stdio framing (JSON-RPC 2.0 over stdio).
    Each message is sent as a line of JSON with a length prefix.
    """

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.request_id = 0

    async def send_request(self, method: str, params: Optional[dict] = None) -> dict:
        """Send a JSON-RPC request and wait for response.

        Args:
            method: The JSON-RPC method name
            params: Optional parameters dict

        Returns:
            The JSON-RPC response dict
        """
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        # Send as JSON line (MCP stdio framing)
        request_json = json.dumps(request)
        self.writer.write(request_json.encode("utf-8") + b"\n")
        await self.writer.drain()

        # Read response
        response_line = await asyncio.wait_for(self.reader.readline(), timeout=10.0)
        response = json.loads(response_line.decode("utf-8"))

        return response

    async def initialize(self) -> dict:
        """Perform MCP initialize handshake.

        Returns:
            The initialize response
        """
        params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0",
            },
        }
        return await self.send_request("initialize", params)

    async def list_tools(self) -> dict:
        """List available MCP tools.

        Returns:
            The tools list response
        """
        return await self.send_request("tools/list")

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Call an MCP tool.

        Args:
            name: The tool name
            arguments: Tool arguments dict

        Returns:
            The tool call response
        """
        params = {
            "name": name,
            "arguments": arguments,
        }
        return await self.send_request("tools/call", params)

    async def close(self) -> None:
        """Close the connection."""
        self.writer.close()
        await self.writer.wait_closed()


async def create_client(port: int) -> MCPProtocolClient:
    """Create and connect an MCP client.

    Args:
        port: The port to connect to

    Returns:
        Connected MCPProtocolClient instance
    """
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    client = MCPProtocolClient(reader, writer)
    return client


@pytest.mark.asyncio
async def test_end_to_end_mcp_handshake(proxy_with_test_port):
    """Test complete MCP protocol handshake through proxy."""
    proxy = proxy_with_test_port

    # Start proxy in background task
    proxy_task = asyncio.create_task(proxy.run())

    try:
        # Wait for startup
        await asyncio.sleep(3.0)

        # Connect client
        client = await create_client(19999)

        try:
            # Perform initialize handshake
            init_response = await client.initialize()

            # Verify response
            assert init_response.get("jsonrpc") == "2.0"
            assert init_response.get("id") == 1
            assert "result" in init_response
            assert "serverInfo" in init_response["result"]

            # Verify server info
            server_info = init_response["result"]["serverInfo"]
            assert server_info["name"] == "MCP-STDIO-Server"  # Default from config

        finally:
            await client.close()

    finally:
        await proxy.shutdown()
        try:
            await proxy_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_end_to_end_list_tools(proxy_with_test_port):
    """Test listing available tools through proxy."""
    proxy = proxy_with_test_port

    proxy_task = asyncio.create_task(proxy.run())

    try:
        await asyncio.sleep(3.0)

        client = await create_client(19999)

        try:
            # Initialize
            await client.initialize()

            # List tools
            tools_response = await client.list_tools()

            # Verify response structure
            assert "result" in tools_response
            assert "tools" in tools_response["result"]

            # Verify expected tools are present
            tools = tools_response["result"]["tools"]
            tool_names = {tool["name"] for tool in tools}

            expected_tools = {
                "ack_event_tool",
                "process_payload_tool",
                "list_recent_events_tool",
                "get_server_info",
                "get_metrics_tool",
                "reset_metrics_tool",
            }

            assert expected_tools.issubset(tool_names), \
                f"Expected tools {expected_tools} not found in {tool_names}"

        finally:
            await client.close()

    finally:
        await proxy.shutdown()
        try:
            await proxy_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_end_to_end_call_ack_event_tool(proxy_with_test_port):
    """Test calling ack_event_tool through proxy."""
    proxy = proxy_with_test_port

    proxy_task = asyncio.create_task(proxy.run())

    try:
        await asyncio.sleep(3.0)

        client = await create_client(19999)

        try:
            await client.initialize()

            # Call ack_event_tool
            response = await client.call_tool(
                name="ack_event_tool",
                arguments={
                    "event_type": "test.event",
                    "payload": {"key": "value"},
                }
            )

            # Verify response
            assert "result" in response
            result = response["result"]

            # Tool responses are wrapped in a "content" array with text items
            assert "content" in result
            assert len(result["content"]) > 0

            # Parse the tool result from content
            content_text = result["content"][0].get("text", "")
            tool_result = json.loads(content_text)

            # Verify structure
            assert tool_result["success"] is True
            assert tool_result["event_type"] == "test.event"
            assert "timestamp" in tool_result

        finally:
            await client.close()

    finally:
        await proxy.shutdown()
        try:
            await proxy_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_end_to_end_call_process_payload_tool(proxy_with_test_port):
    """Test calling process_payload_tool through proxy."""
    proxy = proxy_with_test_port

    proxy_task = asyncio.create_task(proxy.run())

    try:
        await asyncio.sleep(3.0)

        client = await create_client(19999)

        try:
            await client.initialize()

            # Call process_payload_tool
            response = await client.call_tool(
                name="process_payload_tool",
                arguments={
                    "path": "/test/file.py",
                    "user_id": "alice",
                }
            )

            # Verify response
            assert "result" in response
            result = response["result"]

            assert "content" in result
            content_text = result["content"][0].get("text", "")
            tool_result = json.loads(content_text)

            # Verify structure
            assert tool_result["success"] is True
            assert tool_result["path"] == "/test/file.py"
            assert tool_result["user_id"] == "alice"
            assert "timestamp" in tool_result

        finally:
            await client.close()

    finally:
        await proxy.shutdown()
        try:
            await proxy_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_end_to_end_recent_events_persistence(proxy_with_test_port):
    """Test that events persist in the recent events buffer."""
    proxy = proxy_with_test_port

    proxy_task = asyncio.create_task(proxy.run())

    try:
        await asyncio.sleep(3.0)

        client = await create_client(19999)

        try:
            await client.initialize()

            # Call multiple tools to generate events
            await client.call_tool(
                name="ack_event_tool",
                arguments={"event_type": "event1", "payload": {}}
            )
            await client.call_tool(
                name="process_payload_tool",
                arguments={"path": "/file1.py", "user_id": "alice"}
            )
            await client.call_tool(
                name="ack_event_tool",
                arguments={"event_type": "event2", "payload": {}}
            )

            # List recent events
            response = await client.call_tool(
                name="list_recent_events_tool",
                arguments={"max_count": 10}
            )

            # Verify events were captured
            assert "result" in response
            result = response["result"]

            assert "content" in result
            content_text = result["content"][0].get("text", "")
            events_response = json.loads(content_text)

            assert events_response["count"] >= 3
            assert len(events_response["events"]) >= 3

        finally:
            await client.close()

    finally:
        await proxy.shutdown()
        try:
            await proxy_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_end_to_end_server_info(proxy_with_test_port):
    """Test get_server_info tool through proxy."""
    proxy = proxy_with_test_port

    proxy_task = asyncio.create_task(proxy.run())

    try:
        await asyncio.sleep(3.0)

        client = await create_client(19999)

        try:
            await client.initialize()

            # Get server info
            response = await client.call_tool(
                name="get_server_info",
                arguments={}
            )

            # Verify response
            assert "result" in response
            result = response["result"]

            assert "content" in result
            content_text = result["content"][0].get("text", "")
            server_info = json.loads(content_text)

            # Verify server info structure
            assert "name" in server_info
            assert "port" in server_info
            assert "auth_enabled" in server_info
            assert "async_processing" in server_info
            assert "log_level" in server_info
            assert "metrics" in server_info

            # Verify default values
            assert server_info["name"] == "MCP-STDIO-Server"
            assert server_info["port"] == 9000  # Server uses default port from settings
            assert server_info["auth_enabled"] is False  # No tokens configured

        finally:
            await client.close()

    finally:
        await proxy.shutdown()
        try:
            await proxy_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_end_to_end_metrics_tracking(proxy_with_test_port):
    """Test that metrics are tracked across tool calls."""
    proxy = proxy_with_test_port

    proxy_task = asyncio.create_task(proxy.run())

    try:
        await asyncio.sleep(3.0)

        client = await create_client(19999)

        try:
            await client.initialize()

            # Call various tools
            await client.call_tool(
                name="ack_event_tool",
                arguments={"event_type": "test1", "payload": {}}
            )
            await client.call_tool(
                name="process_payload_tool",
                arguments={"path": "/file.py", "user_id": "user1"}
            )
            await client.call_tool(
                name="ack_event_tool",
                arguments={"event_type": "test2", "payload": {}}
            )

            # Get metrics
            response = await client.call_tool(
                name="get_metrics_tool",
                arguments={}
            )

            # Verify metrics were tracked
            assert "result" in response
            result = response["result"]

            assert "content" in result
            content_text = result["content"][0].get("text", "")
            metrics = json.loads(content_text)

            # Should have metrics for the tools we called
            assert "ack_event_tool" in metrics
            assert "process_payload_tool" in metrics

            # Should have success counts
            assert "success" in metrics["ack_event_tool"]
            assert metrics["ack_event_tool"]["success"] >= 2
            assert metrics["process_payload_tool"]["success"] >= 1

        finally:
            await client.close()

    finally:
        await proxy.shutdown()
        try:
            await proxy_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_end_to_end_multiple_sequential_clients(proxy_with_test_port):
    """Test that proxy handles multiple sequential client connections."""
    proxy = proxy_with_test_port

    proxy_task = asyncio.create_task(proxy.run())

    try:
        await asyncio.sleep(3.0)

        # Connect multiple clients sequentially
        success_count = 0
        for i in range(3):
            client = await create_client(19999)

            try:
                await client.initialize()

                # Call a tool
                response = await client.call_tool(
                    name="ack_event_tool",
                    arguments={"event_type": f"client_{i}", "payload": {}}
                )

                # Verify success
                if "result" in response:
                    success_count += 1

            finally:
                await client.close()

            # Add a small delay between clients to ensure proper cleanup
            # This allows the proxy to finish forwarding tasks for the previous client
            await asyncio.sleep(0.5)

        # Verify all client connections succeeded
        assert success_count == 3, f"Expected 3 successful connections, got {success_count}"

    finally:
        await proxy.shutdown()
        try:
            await proxy_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_end_to_end_error_handling(proxy_with_test_port):
    """Test error handling for invalid tool calls."""
    proxy = proxy_with_test_port

    proxy_task = asyncio.create_task(proxy.run())

    try:
        await asyncio.sleep(3.0)

        client = await create_client(19999)

        try:
            await client.initialize()

            # Try to call non-existent tool
            response = await client.call_tool(
                name="non_existent_tool",
                arguments={}
            )

            # Should get an error response
            # MCP protocol returns errors with "error" key
            assert "error" in response or "result" in response

            if "error" in response:
                # Direct error from MCP protocol
                assert response["error"]["code"] == -32601  # Method not found
            else:
                # Tool returned error in result
                result = response["result"]
                assert "content" in result
                # Error messages are typically in text content or isError flag

        finally:
            await client.close()

    finally:
        await proxy.shutdown()
        try:
            await proxy_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_end_to_end_graceful_shutdown(proxy_with_test_port):
    """Test graceful shutdown with active connection."""
    proxy = proxy_with_test_port

    proxy_task = asyncio.create_task(proxy.run())

    try:
        await asyncio.sleep(3.0)

        client = await create_client(19999)

        try:
            await client.initialize()

            # Close client first
            await client.close()

            # Small delay to allow cleanup
            await asyncio.sleep(0.2)

            # Trigger shutdown
            await proxy.shutdown()

            # Wait for proxy to complete with CancelledError handling
            try:
                await asyncio.wait_for(proxy_task, timeout=5.0)
            except asyncio.CancelledError:
                # This is expected during shutdown
                pass

            # Verify server process was terminated
            assert proxy.server_process is not None
            assert proxy.server_process.returncode is not None

        finally:
            await client.close()

    finally:
        try:
            await proxy_task
        except asyncio.CancelledError:
            pass


# Keep existing basic proxy tests for backward compatibility and specific proxy functionality testing

async def test_proxy_starts_and_listens(proxy_with_test_port):
    """Test that proxy starts TCP server and listens on configured port."""
    proxy = proxy_with_test_port

    proxy_task = asyncio.create_task(proxy.run())

    try:
        await asyncio.sleep(2.0)

        # Try to connect to the port
        reader, writer = await asyncio.open_connection("127.0.0.1", 19999)
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.shutdown()
        try:
            await proxy_task
        except asyncio.CancelledError:
            pass


async def test_proxy_server_subprocess_starts(proxy_with_test_port):
    """Test that proxy spawns the MCP server subprocess."""
    proxy = proxy_with_test_port

    proxy_task = asyncio.create_task(proxy.run())

    try:
        await asyncio.sleep(3.0)

        assert proxy.server_process is not None
        assert proxy.server_process.returncode is None
        assert proxy.server_process.pid > 0

    finally:
        await proxy.shutdown()
        try:
            await proxy_task
        except asyncio.CancelledError:
            pass
