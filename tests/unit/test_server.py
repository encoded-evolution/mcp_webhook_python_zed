"""Unit and integration tests for the MCP server module.

This module tests:
- FastMCP instance creation and configuration
- Tool registration
- Tool function behavior
- Server information retrieval
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
import asyncio
from typing import Any

from mcp_webhook.config import get_settings, reset_settings
from mcp_webhook.tools import clear_recent_events, get_buffer_size
from mcp_webhook.server import mcp, run_stdio_server, main


class TestFastMCPInstance:
    """Tests for FastMCP instance creation and configuration."""

    def test_mcp_instance_created(self) -> None:
        """Test that FastMCP instance is created."""
        assert mcp is not None
        assert hasattr(mcp, "name")

    def test_mcp_instance_name_from_config(self) -> None:
        """Test that MCP instance name matches configuration."""
        settings = get_settings()
        assert mcp.name == settings.mcp_name




class TestToolRegistration:
    """Tests for tool registration on the MCP server."""

    @pytest.mark.asyncio
    async def test_ack_event_tool_callable(self) -> None:
        """Test that ack_event_tool is callable and returns correct structure."""
        from mcp_webhook.server import ack_event_tool

        result = await ack_event_tool(
            event_type="test.event",
            payload={"key": "value"}
        )

        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["event_type"] == "test.event"
        assert "message" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_process_payload_tool_callable(self) -> None:
        """Test that process_payload_tool is callable and returns correct structure."""
        from mcp_webhook.server import process_payload_tool

        result = await process_payload_tool(
            path="/test/path.py",
            user_id="test_user"
        )

        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["path"] == "/test/path.py"
        assert result["user_id"] == "test_user"
        assert "result" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_list_recent_events_tool_callable(self) -> None:
        """Test that list_recent_events_tool is callable and returns correct structure."""
        from mcp_webhook.server import list_recent_events_tool

        # Clear buffer before test
        clear_recent_events()

        result = await list_recent_events_tool(max_count=10)

        assert isinstance(result, dict)
        assert "count" in result
        assert "events" in result
        assert "buffer_size" in result
        assert isinstance(result["events"], list)

    @pytest.mark.asyncio
    async def test_list_recent_events_with_events(self) -> None:
        """Test list_recent_events_tool returns actual events."""
        from mcp_webhook.server import ack_event_tool, list_recent_events_tool

        # Clear buffer before test
        clear_recent_events()

        # Add some events
        await ack_event_tool(event_type="event1", payload={})
        await ack_event_tool(event_type="event2", payload={})

        # List events
        result = await list_recent_events_tool(max_count=10)

        assert result["count"] == 2
        assert len(result["events"]) == 2
        assert result["events"][0]["event_type"] in ["event1", "event2"]

    @pytest.mark.asyncio
    async def test_get_server_info_tool(self) -> None:
        """Test that get_server_info returns server configuration."""
        from mcp_webhook.server import get_server_info

        result = await get_server_info()

        assert isinstance(result, dict)
        assert "name" in result
        assert "port" in result
        assert "auth_enabled" in result
        assert "async_processing" in result
        assert "log_level" in result
        assert "mapping_file" in result


class TestToolBehavior:
    """Tests for tool behavior with various inputs."""

    @pytest.mark.asyncio
    async def test_ack_event_tool_with_different_event_types(self) -> None:
        """Test ack_event_tool handles various event types correctly."""
        from mcp_webhook.server import ack_event_tool

        event_types = [
            "file.save",
            "file.open",
            "user.login",
            "custom.event",
        ]

        for event_type in event_types:
            result = await ack_event_tool(event_type=event_type, payload={})
            assert result["success"] is True
            assert result["event_type"] == event_type

    @pytest.mark.asyncio
    async def test_process_payload_tool_with_complex_paths(self) -> None:
        """Test process_payload_tool handles various file paths."""
        from mcp_webhook.server import process_payload_tool

        paths = [
            "/repo/file.py",
            "/src/module/__init__.py",
            "/nested/directory/structure/file.txt",
            "relative/path/file.md",
        ]

        for path in paths:
            result = await process_payload_tool(path=path, user_id="user123")
            assert result["success"] is True
            assert result["path"] == path

    @pytest.mark.asyncio
    async def test_list_recent_events_max_count_limit(self) -> None:
        """Test list_recent_events_tool respects max_count parameter."""
        from mcp_webhook.server import ack_event_tool, list_recent_events_tool

        # Clear buffer before test
        clear_recent_events()

        # Add more events than max_count
        for i in range(10):
            await ack_event_tool(event_type=f"event_{i}", payload={"index": i})

        # Request fewer events than available
        result = await list_recent_events_tool(max_count=5)

        assert result["count"] == 5
        assert len(result["events"]) == 5

    @pytest.mark.asyncio
    async def test_list_recent_events_max_count_zero(self) -> None:
        """Test list_recent_events_tool with max_count=0 returns no events."""
        from mcp_webhook.server import list_recent_events_tool

        # Clear buffer before test
        clear_recent_events()

        result = await list_recent_events_tool(max_count=0)

        assert result["count"] == 0
        assert len(result["events"]) == 0


class TestServerEntryPoints:
    """Tests for server entry point functions."""

    @patch("mcp_webhook.server.mcp")
    def test_run_stdio_server_calls_mcp_run(self, mock_mcp: MagicMock) -> None:
        """Test that run_stdio_server calls mcp.run()."""
        # Call the function
        run_stdio_server()

        # Verify mcp.run() was called
        mock_mcp.run.assert_called_once()

    @patch("mcp_webhook.server.run_stdio_server")
    def test_main_calls_run_stdio_server(self, mock_run: MagicMock) -> None:
        """Test that main() calls run_stdio_server()."""
        main()
        mock_run.assert_called_once()


class TestServerIntegration:
    """Integration tests for server functionality."""

    @pytest.mark.asyncio
    async def test_full_event_flow(self) -> None:
        """Test full flow: add event, process, list events."""
        from mcp_webhook.server import (
            ack_event_tool,
            process_payload_tool,
            list_recent_events_tool,
        )

        # Clear buffer
        clear_recent_events()

        # Process some events
        await ack_event_tool(event_type="file.save", payload={"path": "file.py"})
        await process_payload_tool(path="/test/file.py", user_id="alice")
        await ack_event_tool(event_type="file.open", payload={"path": "file.py"})

        # List events
        result = await list_recent_events_tool(max_count=10)

        # Verify we have 3 events
        assert result["count"] == 3
        assert len(result["events"]) == 3

        # Verify event types are present
        event_types = {e["event_type"] for e in result["events"]}
        assert "file.save" in event_types
        assert "file.open" in event_types

        # Verify process_payload result is present
        process_events = [
            e for e in result["events"]
            if e.get("result", {}).get("user_id") == "alice"
        ]
        assert len(process_events) > 0

    @pytest.mark.asyncio
    async def test_buffer_limit(self) -> None:
        """Test that the event buffer respects its size limit."""
        from mcp_webhook.server import ack_event_tool, list_recent_events_tool

        # Clear buffer
        clear_recent_events()

        # Add more events than buffer size (default is 100)
        buffer_limit = 105
        for i in range(buffer_limit):
            await ack_event_tool(event_type=f"event_{i}", payload={"index": i})

        # Check buffer size is at limit
        assert get_buffer_size() == 100

        # List events and verify we only get the most recent 100
        result = await list_recent_events_tool(max_count=200)
        assert result["count"] == 100
        assert result["buffer_size"] == 100

    @pytest.mark.asyncio
    async def test_server_info_consistency(self) -> None:
        """Test that get_server_info returns consistent configuration."""
        from mcp_webhook.server import get_server_info
        from mcp_webhook.config import get_settings

        settings = get_settings()
        result = await get_server_info()

        assert result["name"] == settings.mcp_name
        assert result["port"] == settings.port
        assert result["auth_enabled"] == settings.auth_enabled
        assert result["async_processing"] == settings.async_processing
        assert result["log_level"] == settings.log_level
        assert result["mapping_file"] == settings.mapping_file


class TestErrorHandling:
    """Tests for error handling in server tools."""

    @pytest.mark.asyncio
    async def test_tools_gracefully_handle_empty_payload(self) -> None:
        """Test that tools handle empty payloads gracefully."""
        from mcp_webhook.server import ack_event_tool

        result = await ack_event_tool(event_type="test.event", payload={})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_tools_handle_large_payloads(self) -> None:
        """Test that tools can handle large payloads."""
        from mcp_webhook.server import ack_event_tool

        large_payload = {}
        for i in range(100):
            large_payload[f"key_{i}"] = f"value_{i}"

        result = await ack_event_tool(event_type="test.event", payload=large_payload)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_list_recent_events_handles_empty_buffer(self) -> None:
        """Test list_recent_events with no events in buffer."""
        from mcp_webhook.server import list_recent_events_tool

        clear_recent_events()
        result = await list_recent_events_tool(max_count=10)

        assert result["count"] == 0
        assert len(result["events"]) == 0
