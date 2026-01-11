"""Envelope models and extraction utilities for MCP webhook server.

This module provides Pydantic models for validating incoming event envelopes
and utilities for extracting values from nested payload structures using
dot-path syntax.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class Meta(BaseModel):
    """Metadata for an event envelope.

    Attributes:
        auth: Optional bearer token for authentication
        id: Optional unique identifier for this envelope
        timestamp: Optional ISO 8601 timestamp
    """

    auth: Optional[str] = Field(
        default=None,
        description="Bearer token for authentication",
    )
    id: Optional[str] = Field(
        default=None,
        description="Unique identifier for this envelope",
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp",
    )


class Envelope(BaseModel):
    """Event envelope containing event type, payload, and optional metadata.

    This model validates the structure of incoming event envelopes from clients.

    Attributes:
        type: The message type (typically "event")
        event_type: The specific event type (e.g., "file.save")
        payload: The event payload containing event-specific data
        meta: Optional metadata including auth token, envelope ID, and timestamp
    """

    type: str = Field(
        default="event",
        description="Message type (typically 'event')",
    )
    event_type: str = Field(
        ...,
        description="Specific event type (e.g., 'file.save', 'file.open')",
    )
    payload: Dict[str, Any] = Field(
        ...,
        description="Event payload containing event-specific data",
    )
    meta: Optional[Meta] = Field(
        default=None,
        description="Optional metadata including auth and timestamps",
    )

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        """Validate that event_type is not empty."""
        if not v or not v.strip():
            raise ValueError("event_type cannot be empty")
        return v.strip()

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validate that type is 'event'."""
        if v.lower() != "event":
            raise ValueError(f"type must be 'event', got '{v}'")
        return v.lower()


def extract_value(payload: Dict[str, Any], dot_path: str) -> Any:
    """Extract a value from a nested dictionary using dot-path syntax.

    This function allows extracting nested values using a dot-separated path.
    For example, "payload.user.id" would extract payload["user"]["id"].

    Args:
        payload: The dictionary to extract from
        dot_path: Dot-separated path (e.g., "user.id", "payload.user.id")

    Returns:
        The value at the specified path

    Raises:
        ValueError: If dot_path is empty or invalid
        KeyError: If the path cannot be resolved (key not found)
        TypeError: If intermediate value is not a dict

    Examples:
        >>> payload = {"user": {"id": "alice", "name": "Alice"}}
        >>> extract_value(payload, "user.id")
        'alice'
        >>> extract_value(payload, "user.name")
        'Alice'
        >>> extract_value(payload, "user.email")
        KeyError: 'email'
    """
    if not dot_path:
        raise ValueError("Dot path cannot be empty")

    if not isinstance(payload, dict):
        raise TypeError(
            f"Payload must be a dict, got {type(payload).__name__}"
        )

    keys = dot_path.split(".")
    current = payload

    for i, key in enumerate(keys):
        if not key:
            raise ValueError(
                f"Invalid dot path: empty key at position {i} in '{dot_path}'"
            )

        if not isinstance(current, dict):
            raise TypeError(
                f"Cannot access key '{key}' at path '{'.'.join(keys[:i])}' "
                f"because parent value is not a dict (got {type(current).__name__})"
            )

        if key not in current:
            path_so_far = ".".join(keys[:i + 1])
            raise KeyError(
                f"Key '{key}' not found at path '{path_so_far}' "
                f"in dot path '{dot_path}'"
            )

        current = current[key]

    return current


def extract_value_with_default(
    payload: Dict[str, Any],
    dot_path: str,
    default: Any = None,
) -> Any:
    """Extract a value from a nested dictionary with a default on failure.

    This is a safe version of extract_value that returns a default value
    instead of raising an exception when the path cannot be resolved.

    Args:
        payload: The dictionary to extract from
        dot_path: Dot-separated path (e.g., "user.id", "payload.user.id")
        default: Value to return if extraction fails (default: None)

    Returns:
        The value at the specified path, or default if extraction fails

    Examples:
        >>> payload = {"user": {"id": "alice", "name": "Alice"}}
        >>> extract_value_with_default(payload, "user.id", "unknown")
        'alice'
        >>> extract_value_with_default(payload, "user.email", "unknown")
        'unknown'
        >>> extract_value_with_default(payload, "invalid.path", "fallback")
        'fallback'
    """
    try:
        return extract_value(payload, dot_path)
    except (ValueError, KeyError, TypeError):
        return default
