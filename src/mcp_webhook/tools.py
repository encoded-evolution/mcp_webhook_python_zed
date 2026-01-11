"""MCP tool implementations for the webhook server.

This module provides the core tool functions that can be called by the
envelope router to process incoming events. Tools return structured
outputs via Pydantic models for validation and documentation.
"""

from typing import Any, Dict, Optional
from collections import deque
from datetime import datetime
from pydantic import BaseModel, Field


# In-memory buffer for recent events
# Stores tuples of (timestamp, event_type, result)
_recent_events_buffer: deque = deque(maxlen=100)


class AckEventResponse(BaseModel):
    """Response from ack_event tool."""

    success: bool = Field(..., description="Whether the event was acknowledged")
    event_type: str = Field(..., description="The event type that was acknowledged")
    message: str = Field(..., description="Acknowledgement message")
    timestamp: str = Field(..., description="ISO 8601 timestamp of acknowledgement")


class ProcessPayloadResponse(BaseModel):
    """Response from process_payload tool."""

    success: bool = Field(..., description="Whether the payload was processed")
    path: str = Field(..., description="The file path that was processed")
    user_id: str = Field(..., description="The user who triggered the processing")
    result: str = Field(..., description="Processing result description")
    timestamp: str = Field(..., description="ISO 8601 timestamp of processing")


class RecentEvent(BaseModel):
    """Represents a single recent event."""

    timestamp: str = Field(..., description="When the event was processed")
    event_type: str = Field(..., description="The type of event")
    result: Dict[str, Any] = Field(..., description="Processing result")


class ListRecentEventsResponse(BaseModel):
    """Response from list_recent_events tool."""

    count: int = Field(..., description="Number of recent events")
    events: list[RecentEvent] = Field(..., description="List of recent events")
    buffer_size: int = Field(..., description="Maximum buffer size")


def ack_event(event_type: str, payload: Dict[str, Any]) -> AckEventResponse:
    """Acknowledge receipt of an event.

    This tool simply acknowledges that an event was received.
    It's useful for testing and for events that don't require processing.

    Args:
        event_type: The type of event being acknowledged
        payload: The event payload (for logging purposes)

    Returns:
        AckEventResponse: Structured response indicating successful acknowledgement
    """
    timestamp = datetime.utcnow().isoformat() + "Z"

    response = AckEventResponse(
        success=True,
        event_type=event_type,
        message=f"Successfully acknowledged event: {event_type}",
        timestamp=timestamp,
    )

    # Store in recent events buffer
    _store_recent_event(event_type, response.model_dump())

    return response


def process_payload(path: str, user_id: str) -> ProcessPayloadResponse:
    """Process a file payload.

    This tool simulates processing of a file path for a given user.
    In a real implementation, this could trigger file analysis,
    linting, or other operations.

    Args:
        path: The file path to process
        user_id: The user who is requesting the processing

    Returns:
        ProcessPayloadResponse: Structured response with processing results
    """
    timestamp = datetime.utcnow().isoformat() + "Z"

    # Simulate processing logic
    # In a real implementation, this would perform actual operations
    result = f"Processed file: {path}"

    response = ProcessPayloadResponse(
        success=True,
        path=path,
        user_id=user_id,
        result=result,
        timestamp=timestamp,
    )

    # Store in recent events buffer
    _store_recent_event("process_payload", response.model_dump())

    return response


def list_recent_events(max_count: Optional[int] = None) -> ListRecentEventsResponse:
    """List recently processed events.

    Returns a list of events that have been processed, stored in an
    in-memory buffer. Useful for debugging and monitoring.

    Args:
        max_count: Maximum number of events to return. If None, returns all.

    Returns:
        ListRecentEventsResponse: Structured response with recent events
    """
    # Convert buffer to list of RecentEvent objects
    events = []
    for timestamp, event_type, result in _recent_events_buffer:
        events.append(
            RecentEvent(
                timestamp=timestamp,
                event_type=event_type,
                result=result,
            )
        )

    # Limit by max_count if specified (returns most recent first)
    if max_count is not None and max_count > 0:
        # Take the last max_count events and reverse them to show most recent first
        events = events[-max_count:]
        events.reverse()

    response = ListRecentEventsResponse(
        count=len(events),
        events=events,
        buffer_size=_recent_events_buffer.maxlen or 0,
    )

    return response


def _store_recent_event(event_type: str, result: Dict[str, Any]) -> None:
    """Store an event in the recent events buffer.

    Args:
        event_type: The type of event
        result: The processing result to store
    """
    timestamp = datetime.utcnow().isoformat() + "Z"
    _recent_events_buffer.append((timestamp, event_type, result))


def clear_recent_events() -> None:
    """Clear the recent events buffer.

    Useful for testing and for resetting the event history.
    """
    _recent_events_buffer.clear()


def get_buffer_size() -> int:
    """Get the current size of the recent events buffer.

    Returns:
        The number of events currently stored in the buffer.
    """
    return len(_recent_events_buffer)
