"""Integration tests for logging, metrics, and recent events buffer.

These tests verify:
- Structured JSON logging configuration
- Metrics tracking and retrieval
- Recent events buffer functionality
- Extra context support for enhanced tracing
"""

import json
import sys
import pytest
import logging
from pathlib import Path
from collections import defaultdict
from io import StringIO

from mcp_webhook.config import reset_settings, get_settings, configure_logging
from mcp_webhook.tools import (
    ack_event,
    process_payload,
    list_recent_events,
    clear_recent_events,
    get_buffer_size,
)
from mcp_webhook.server import increment_metric, get_metrics, reset_metrics


@pytest.fixture(autouse=True)
def clean_state():
    """Reset state before and after each test."""
    reset_settings()
    clear_recent_events()
    reset_metrics()
    yield
    clear_recent_events()
    reset_metrics()
    reset_settings()


class TestStructuredLogging:
    """Tests for structured JSON logging configuration."""

    def test_configure_logging_returns_logger(self, clean_state):
        """Test that configure_logging returns a logger instance."""
        settings = get_settings()
        logger = configure_logging(settings)

        assert logger is not None
        assert isinstance(logger, logging.Logger)
        assert logger.name == "mcp_webhook"

    def test_log_level_from_settings(self, clean_state):
        """Test that logging respects LOG_LEVEL from settings."""
        # Set DEBUG log level
        from mcp_webhook.config import Settings
        settings = Settings(log_level="DEBUG")

        logger = configure_logging(settings)
        assert logger.level == logging.DEBUG

    def test_json_formatter_output(self, clean_state, capsys):
        """Test that logs are formatted as JSON."""
        from mcp_webhook.config import JSONFormatter
        import json

        # Create logger with JSON formatter
        logger = logging.getLogger("test_json")
        # Clear existing handlers to avoid duplicates
        logger.handlers.clear()
        handler = logging.StreamHandler(sys.stdout)
        formatter = JSONFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False  # Prevent double logging

        # Log a message
        logger.info("Test message")

        # Capture stdout and verify JSON format
        captured = capsys.readouterr().out
        parsed = json.loads(captured.strip())

        assert "timestamp" in parsed
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test_json"
        assert parsed["message"] == "Test message"

    def test_json_formatter_handles_extra_fields(self, clean_state):
        """Test that JSON formatter includes extra fields."""
        from mcp_webhook.config import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Add custom extra field
        record.event_type = "file.save"
        record.user_id = "alice"

        # Format and parse as JSON
        formatted = formatter.format(record)
        parsed = json.loads(formatted)

        # Extra fields are now nested under "extra" key
        assert "extra" in parsed
        assert "event_type" in parsed["extra"]
        assert parsed["extra"]["event_type"] == "file.save"
        assert "user_id" in parsed["extra"]
        assert parsed["extra"]["user_id"] == "alice"

    def test_json_formatter_handles_exceptions(self, clean_state):
        """Test that JSON formatter includes exception info."""
        from mcp_webhook.config import JSONFormatter

        formatter = JSONFormatter()

        try:
            raise ValueError("Test exception")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info(),  # Use actual exception info tuple
            )

        # Format and parse as JSON
        formatted = formatter.format(record)
        parsed = json.loads(formatted)

        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]
        assert "Test exception" in parsed["exception"]


class TestMetricsStub:
    """Tests for metrics tracking functionality."""

    def test_increment_metric_basic(self, clean_state):
        """Test that increment_metric increments a counter."""
        increment_metric("test_metric", "success")

        metrics = get_metrics()

        assert "test_metric" in metrics
        assert "success" in metrics["test_metric"]
        assert metrics["test_metric"]["success"] == 1

    def test_increment_metric_multiple_times(self, clean_state):
        """Test that increment_metric increments multiple times."""
        for _ in range(5):
            increment_metric("test_metric", "success")

        metrics = get_metrics()

        assert metrics["test_metric"]["success"] == 5

    def test_increment_metric_different_status(self, clean_state):
        """Test that increment_metric tracks different statuses."""
        increment_metric("test_metric", "success")
        increment_metric("test_metric", "error")
        increment_metric("test_metric", "timeout")

        metrics = get_metrics()

        assert metrics["test_metric"]["success"] == 1
        assert metrics["test_metric"]["error"] == 1
        assert metrics["test_metric"]["timeout"] == 1

    def test_get_metrics_returns_dict(self, clean_state):
        """Test that get_metrics returns proper dict structure."""
        increment_metric("tool1", "success")
        increment_metric("tool2", "error")

        metrics = get_metrics()

        assert isinstance(metrics, dict)
        assert len(metrics) == 2
        assert not isinstance(metrics["tool1"], defaultdict)
        assert isinstance(metrics["tool1"], dict)

    def test_reset_metrics_clears_all(self, clean_state):
        """Test that reset_metrics clears all counters."""
        increment_metric("metric1", "success")
        increment_metric("metric2", "error")

        # Verify metrics exist
        metrics_before_reset = get_metrics()
        assert len(metrics_before_reset) > 0

        # Reset
        reset_metrics()

        # Verify cleared
        metrics_after_reset = get_metrics()
        assert len(metrics_after_reset) == 0

    def test_metrics_multiple_tools(self, clean_state):
        """Test tracking metrics for multiple tools."""
        increment_metric("ack_event_tool", "success")
        increment_metric("process_payload_tool", "success")
        increment_metric("list_recent_events_tool", "success")

        metrics = get_metrics()

        assert len(metrics) == 3
        assert all("success" in metrics[tool] for tool in metrics)


class TestRecentEventsBuffer:
    """Tests for in-memory recent events buffer."""

    def test_buffer_initially_empty(self, clean_state):
        """Test that buffer is initially empty."""
        assert get_buffer_size() == 0

    def test_ack_event_stores_in_buffer(self, clean_state):
        """Test that ack_event stores event in buffer."""
        result = ack_event(
            event_type="test.event",
            payload={"test": "data"},
        )

        assert get_buffer_size() == 1

    def test_process_payload_stores_in_buffer(self, clean_state):
        """Test that process_payload stores event in buffer."""
        result = process_payload(
            path="/test/file.txt",
            user_id="test_user",
        )

        assert get_buffer_size() == 1

    def test_multiple_events_in_buffer(self, clean_state):
        """Test that multiple events are stored."""
        for i in range(5):
            ack_event(
                event_type=f"event.{i}",
                payload={"index": i},
            )

        assert get_buffer_size() == 5

    def test_list_recent_events_returns_all(self, clean_state):
        """Test that list_recent_events returns all events."""
        # Add 3 events
        for i in range(3):
            ack_event(
                event_type=f"event.{i}",
                payload={"index": i},
            )

        # List all events
        result = list_recent_events()

        assert result.count == 3
        assert len(result.events) == 3
        assert result.buffer_size == 100  # Default buffer size

    def test_list_recent_events_with_max_count(self, clean_state):
        """Test that list_recent_events respects max_count."""
        # Add 5 events
        for i in range(5):
            ack_event(
                event_type=f"event.{i}",
                payload={"index": i},
            )

        # List only 2 events
        result = list_recent_events(max_count=2)

        assert result.count == 2
        assert len(result.events) == 2

    def test_list_recent_events_most_recent_first(self, clean_state):
        """Test that list_recent_events returns most recent events first."""
        # Add events in order
        ack_event(event_type="event1", payload={})
        ack_event(event_type="event2", payload={})
        ack_event(event_type="event3", payload={})

        # List with limit
        result = list_recent_events(max_count=2)

        # Should return last 2 events (most recent) in reverse order
        assert len(result.events) == 2
        assert result.events[0].event_type == "event3"
        assert result.events[1].event_type == "event2"

    def test_clear_recent_events(self, clean_state):
        """Test that clear_recent_events empties buffer."""
        # Add events
        for _ in range(3):
            ack_event(event_type="test", payload={})

        assert get_buffer_size() == 3

        # Clear
        clear_recent_events()

        assert get_buffer_size() == 0

    def test_buffer_overflows_at_max_size(self, clean_state):
        """Test that buffer discards old events when full.

        The buffer has a max size of 100. Adding more than 100 events
        should keep only the most recent 100.
        """
        # Try to add more than max buffer size
        for i in range(150):
            ack_event(event_type=f"event.{i}", payload={"index": i})

        # Buffer should only hold 100
        assert get_buffer_size() == 100

    def test_event_data_structure(self, clean_state):
        """Test that stored events have correct structure."""
        result = ack_event(
            event_type="test.event",
            payload={"test": "data"},
        )

        # List events
        events_result = list_recent_events()

        assert len(events_result.events) == 1
        event = events_result.events[0]

        assert hasattr(event, "timestamp")
        assert hasattr(event, "event_type")
        assert hasattr(event, "result")
        assert event.event_type == "test.event"


class TestIntegration:
    """Integration tests combining logging, metrics, and events."""

    def test_tool_call_increments_metrics(self, clean_state):
        """Test that calling tools increments metrics."""
        # This would require running the actual MCP server
        # For now, we test the metric functions directly

        initial_metrics = get_metrics()
        initial_count = sum(
            sum(status_counts.values())
            for status_counts in initial_metrics.values()
        )

        # Simulate tool calls
        increment_metric("ack_event_tool", "success")
        increment_metric("process_payload_tool", "success")

        final_metrics = get_metrics()
        final_count = sum(
            sum(status_counts.values())
            for status_counts in final_metrics.values()
        )

        assert final_count == initial_count + 2

    def test_logging_with_context(self, clean_state, capsys):
        """Test that logging can include context information."""
        from mcp_webhook.config import JSONFormatter
        import json

        logger = logging.getLogger("test_context")
        # Clear existing handlers to avoid duplicates
        logger.handlers.clear()
        handler = logging.StreamHandler(sys.stdout)
        formatter = JSONFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False  # Prevent double logging

        # Log with context (simulated via extra fields)
        logger.info(
            "Processing event",
            extra={"event_type": "file.save", "user_id": "alice"}
        )

        # Verify context was included in JSON output
        captured = capsys.readouterr().out
        parsed = json.loads(captured.strip())

        assert parsed["message"] == "Processing event"
        assert "extra" in parsed
        assert parsed["extra"]["event_type"] == "file.save"
        assert parsed["extra"]["user_id"] == "alice"
