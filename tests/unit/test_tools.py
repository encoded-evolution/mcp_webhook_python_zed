"""Unit tests for MCP tool implementations."""

import pytest
from datetime import datetime

from mcp_webhook.tools import (
    AckEventResponse,
    ProcessPayloadResponse,
    RecentEvent,
    ListRecentEventsResponse,
    ack_event,
    process_payload,
    list_recent_events,
    clear_recent_events,
    get_buffer_size,
)


class TestAckEventResponse:
    """Tests for the AckEventResponse Pydantic model."""

    def test_ack_event_response_creation(self):
        """Test creating a valid AckEventResponse."""
        response = AckEventResponse(
            success=True,
            event_type="file.save",
            message="Successfully acknowledged event: file.save",
            timestamp="2026-01-06T12:00:00Z"
        )
        assert response.success is True
        assert response.event_type == "file.save"
        assert "Successfully acknowledged" in response.message
        assert response.timestamp == "2026-01-06T12:00:00Z"

    def test_ack_event_response_missing_required_fields(self):
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValueError):
            AckEventResponse(
                success=True,
                event_type="file.save",
                # Missing message and timestamp
            )


class TestProcessPayloadResponse:
    """Tests for the ProcessPayloadResponse Pydantic model."""

    def test_process_payload_response_creation(self):
        """Test creating a valid ProcessPayloadResponse."""
        response = ProcessPayloadResponse(
            success=True,
            path="/repo/file.py",
            user_id="alice",
            result="Processed file: /repo/file.py",
            timestamp="2026-01-06T12:00:00Z"
        )
        assert response.success is True
        assert response.path == "/repo/file.py"
        assert response.user_id == "alice"
        assert "Processed file" in response.result
        assert response.timestamp == "2026-01-06T12:00:00Z"


class TestRecentEvent:
    """Tests for the RecentEvent Pydantic model."""

    def test_recent_event_creation(self):
        """Test creating a valid RecentEvent."""
        event = RecentEvent(
            timestamp="2026-01-06T12:00:00Z",
            event_type="file.save",
            result={"success": True, "message": "done"}
        )
        assert event.timestamp == "2026-01-06T12:00:00Z"
        assert event.event_type == "file.save"
        assert event.result == {"success": True, "message": "done"}


class TestListRecentEventsResponse:
    """Tests for the ListRecentEventsResponse Pydantic model."""

    def test_list_recent_events_response_creation(self):
        """Test creating a valid ListRecentEventsResponse."""
        event1 = RecentEvent(
            timestamp="2026-01-06T12:00:00Z",
            event_type="file.save",
            result={"success": True}
        )
        response = ListRecentEventsResponse(
            count=1,
            events=[event1],
            buffer_size=100
        )
        assert response.count == 1
        assert len(response.events) == 1
        assert response.events[0].event_type == "file.save"
        assert response.buffer_size == 100


class TestAckEvent:
    """Tests for the ack_event tool function."""

    def test_ack_event_basic(self):
        """Test basic event acknowledgement."""
        response = ack_event("file.save", {"path": "/repo/file.py"})

        assert isinstance(response, AckEventResponse)
        assert response.success is True
        assert response.event_type == "file.save"
        assert "Successfully acknowledged" in response.message
        assert "file.save" in response.message
        assert response.timestamp.endswith("Z")

    def test_ack_event_with_various_event_types(self):
        """Test acknowledging different event types."""
        event_types = ["file.save", "file.open", "user.login", "data.sync"]

        for event_type in event_types:
            response = ack_event(event_type, {"data": "test"})
            assert response.success is True
            assert response.event_type == event_type
            assert event_type in response.message

    def test_ack_event_with_complex_payload(self):
        """Test acknowledging events with complex payloads."""
        payload = {
            "user": {"id": "alice", "name": "Alice"},
            "file": {"path": "/repo/file.py", "size": 1024},
            "metadata": {"timestamp": "2026-01-06T12:00:00Z"}
        }

        response = ack_event("file.save", payload)

        assert response.success is True
        assert response.event_type == "file.save"

    def test_ack_event_stores_in_buffer(self):
        """Test that acknowledged events are stored in recent events buffer."""
        clear_recent_events()

        # Acknowledge two events
        ack_event("file.save", {"path": "/file1.py"})
        ack_event("file.open", {"path": "/file2.py"})

        # Check buffer size
        assert get_buffer_size() == 2

        # List recent events
        events_response = list_recent_events()
        assert events_response.count == 2
        assert events_response.events[0].event_type == "file.save"
        assert events_response.events[1].event_type == "file.open"


class TestProcessPayload:
    """Tests for the process_payload tool function."""

    def test_process_payload_basic(self):
        """Test basic payload processing."""
        response = process_payload("/repo/file.py", "alice")

        assert isinstance(response, ProcessPayloadResponse)
        assert response.success is True
        assert response.path == "/repo/file.py"
        assert response.user_id == "alice"
        assert "Processed file" in response.result
        assert "/repo/file.py" in response.result
        assert response.timestamp.endswith("Z")

    def test_process_payload_with_various_paths(self):
        """Test processing files with various paths."""
        paths = [
            "/repo/file.py",
            "/home/user/project/main.go",
            "/var/log/app.log",
            "relative/path/to/file.txt"
        ]
        user_id = "test_user"

        for path in paths:
            response = process_payload(path, user_id)
            assert response.success is True
            assert response.path == path
            assert response.user_id == user_id
            assert path in response.result

    def test_process_payload_with_various_users(self):
        """Test processing files with various user IDs."""
        user_ids = ["alice", "bob", "charlie", "system"]
        path = "/repo/file.py"

        for user_id in user_ids:
            response = process_payload(path, user_id)
            assert response.success is True
            assert response.path == path
            assert response.user_id == user_id

    def test_process_payload_stores_in_buffer(self):
        """Test that processed payloads are stored in recent events buffer."""
        clear_recent_events()

        # Process two payloads
        process_payload("/file1.py", "alice")
        process_payload("/file2.py", "bob")

        # Check buffer size
        assert get_buffer_size() == 2

        # List recent events
        events_response = list_recent_events()
        assert events_response.count == 2

        # Both should be process_payload events
        for event in events_response.events:
            assert event.event_type == "process_payload"
            assert event.result["success"] is True


class TestListRecentEvents:
    """Tests for the list_recent_events tool function."""

    def test_list_recent_events_empty(self):
        """Test listing recent events when buffer is empty."""
        clear_recent_events()

        response = list_recent_events()

        assert isinstance(response, ListRecentEventsResponse)
        assert response.count == 0
        assert len(response.events) == 0
        assert response.buffer_size == 100

    def test_list_recent_events_with_data(self):
        """Test listing recent events with data in buffer."""
        clear_recent_events()

        # Add some events
        ack_event("file.save", {"path": "/file1.py"})
        process_payload("/file2.py", "alice")
        ack_event("file.open", {"path": "/file3.py"})

        response = list_recent_events()

        assert response.count == 3
        assert len(response.events) == 3
        assert response.buffer_size == 100

        # Check event types
        assert response.events[0].event_type == "file.save"
        assert response.events[1].event_type == "process_payload"
        assert response.events[2].event_type == "file.open"

    def test_list_recent_events_with_max_count(self):
        """Test listing recent events with max_count limit."""
        clear_recent_events()

        # Add 5 events
        for i in range(5):
            ack_event(f"event.{i}", {"index": i})

        # Request only last 2 events
        response = list_recent_events(max_count=2)

        assert response.count == 2
        assert len(response.events) == 2

        # Should be the last 2 events (most recent first)
        assert response.events[0].event_type == "event.4"
        assert response.events[1].event_type == "event.3"

    def test_list_recent_events_max_count_larger_than_buffer(self):
        """Test listing events when max_count is larger than buffer size."""
        clear_recent_events()

        # Add 3 events
        ack_event("event.1", {})
        process_payload("/file.py", "user")
        ack_event("event.2", {})

        # Request 10 events (more than available)
        response = list_recent_events(max_count=10)

        assert response.count == 3
        assert len(response.events) == 3

    def test_list_recent_events_max_count_zero(self):
        """Test listing events with max_count=0 returns all."""
        clear_recent_events()

        ack_event("event.1", {})
        ack_event("event.2", {})

        response = list_recent_events(max_count=0)

        assert response.count == 2
        assert len(response.events) == 2

    def test_list_recent_events_max_count_none(self):
        """Test listing events with max_count=None returns all."""
        clear_recent_events()

        ack_event("event.1", {})
        ack_event("event.2", {})

        response = list_recent_events(max_count=None)

        assert response.count == 2
        assert len(response.events) == 2

    def test_list_recent_events_default_no_limit(self):
        """Test listing events without max_count parameter returns all."""
        clear_recent_events()

        ack_event("event.1", {})
        ack_event("event.2", {})

        response = list_recent_events()

        assert response.count == 2
        assert len(response.events) == 2

    def test_list_recent_events_includes_full_result(self):
        """Test that recent events include full result data."""
        clear_recent_events()

        # Process a payload
        process_payload("/repo/file.py", "alice")

        response = list_recent_events()

        assert response.count == 1
        event = response.events[0]
        assert event.event_type == "process_payload"

        # Check that result data is complete
        result = event.result
        assert result["success"] is True
        assert result["path"] == "/repo/file.py"
        assert result["user_id"] == "alice"
        assert "result" in result
        assert "timestamp" in result

    def test_list_recent_events_timestamp_order(self):
        """Test that events are listed in chronological order."""
        clear_recent_events()

        # Add events with expected order
        ack_event("first", {})
        ack_event("second", {})
        ack_event("third", {})

        response = list_recent_events()

        assert response.count == 3
        assert response.events[0].event_type == "first"
        assert response.events[1].event_type == "second"
        assert response.events[2].event_type == "third"


class TestClearRecentEvents:
    """Tests for the clear_recent_events function."""

    def test_clear_recent_events_empty_buffer(self):
        """Test clearing an already empty buffer."""
        clear_recent_events()
        assert get_buffer_size() == 0

        clear_recent_events()
        assert get_buffer_size() == 0

    def test_clear_recent_events_with_data(self):
        """Test clearing buffer with data."""
        # Add events
        ack_event("event.1", {})
        ack_event("event.2", {})
        assert get_buffer_size() == 2

        # Clear
        clear_recent_events()
        assert get_buffer_size() == 0

        # Verify cleared
        response = list_recent_events()
        assert response.count == 0
        assert len(response.events) == 0

    def test_clear_recent_events_multiple_times(self):
        """Test clearing buffer multiple times."""
        # Add events
        ack_event("event.1", {})
        ack_event("event.2", {})
        assert get_buffer_size() == 2

        # Clear once
        clear_recent_events()
        assert get_buffer_size() == 0

        # Clear again
        clear_recent_events()
        assert get_buffer_size() == 0

        # Add more events
        ack_event("event.3", {})
        assert get_buffer_size() == 1

        # Clear again
        clear_recent_events()
        assert get_buffer_size() == 0


class TestGetBufferSize:
    """Tests for the get_buffer_size function."""

    def test_get_buffer_size_empty(self):
        """Test getting buffer size when empty."""
        clear_recent_events()
        size = get_buffer_size()
        assert size == 0

    def test_get_buffer_size_with_events(self):
        """Test getting buffer size with events."""
        clear_recent_events()

        assert get_buffer_size() == 0

        ack_event("event.1", {})
        assert get_buffer_size() == 1

        ack_event("event.2", {})
        assert get_buffer_size() == 2

        process_payload("/file.py", "user")
        assert get_buffer_size() == 3

    def test_get_buffer_size_after_clear(self):
        """Test getting buffer size after clearing."""
        clear_recent_events()

        ack_event("event.1", {})
        ack_event("event.2", {})
        assert get_buffer_size() == 2

        clear_recent_events()
        assert get_buffer_size() == 0

    def test_get_buffer_size_incremental(self):
        """Test buffer size increases incrementally."""
        clear_recent_events()

        for i in range(10):
            ack_event(f"event.{i}", {})
            assert get_buffer_size() == i + 1


class TestIntegration:
    """Integration tests for tool interactions."""

    def test_full_workflow_acknowledge_list(self):
        """Test full workflow: acknowledge events and list them."""
        clear_recent_events()

        # Acknowledge events
        ack_event("file.save", {"path": "/file1.py"})
        ack_event("file.open", {"path": "/file2.py"})
        ack_event("file.close", {"path": "/file3.py"})

        # List them
        response = list_recent_events()

        assert response.count == 3
        assert len(response.events) == 3

        # Verify each event
        assert response.events[0].event_type == "file.save"
        assert response.events[1].event_type == "file.open"
        assert response.events[2].event_type == "file.close"

        # Verify timestamps exist and are valid
        for event in response.events:
            assert event.timestamp
            assert event.timestamp.endswith("Z")
            # Parse timestamp to ensure it's valid ISO format
            datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))

    def test_full_workflow_process_list(self):
        """Test full workflow: process payloads and list them."""
        clear_recent_events()

        # Process payloads
        process_payload("/file1.py", "alice")
        process_payload("/file2.py", "bob")
        process_payload("/file3.py", "charlie")

        # List them
        response = list_recent_events()

        assert response.count == 3

        # Verify each processed payload
        for i, event in enumerate(response.events):
            assert event.event_type == "process_payload"
            assert event.result["success"] is True
            assert f"/file{i+1}.py" in event.result["path"]
            assert event.result["user_id"] in ["alice", "bob", "charlie"]

    def test_full_workflow_mixed_operations(self):
        """Test workflow with mixed operations."""
        clear_recent_events()

        # Mix of different operations
        ack_event("startup", {})
        process_payload("/config.yaml", "system")
        ack_event("login", {"user": "alice"})
        process_payload("/data.json", "alice")
        ack_event("logout", {"user": "alice"})

        # List them
        response = list_recent_events()

        assert response.count == 5
        assert response.events[0].event_type == "startup"
        assert response.events[1].event_type == "process_payload"
        assert response.events[2].event_type == "login"
        assert response.events[3].event_type == "process_payload"
        assert response.events[4].event_type == "logout"

        # Verify with max_count
        response_limited = list_recent_events(max_count=2)
        assert response_limited.count == 2
        assert response_limited.events[0].event_type == "logout"
        assert response_limited.events[1].event_type == "process_payload"

    def test_full_workflow_with_clear(self):
        """Test workflow that clears and starts fresh."""
        clear_recent_events()

        # Add some events
        ack_event("event.1", {})
        process_payload("/file.py", "user")
        assert get_buffer_size() == 2

        # Clear
        clear_recent_events()
        assert get_buffer_size() == 0

        # Add new events
        ack_event("new.1", {})
        ack_event("new.2", {})
        process_payload("/new.py", "admin")

        # Verify only new events
        response = list_recent_events()
        assert response.count == 3
        assert response.events[0].event_type == "new.1"
        assert response.events[1].event_type == "new.2"
        assert response.events[2].event_type == "process_payload"
