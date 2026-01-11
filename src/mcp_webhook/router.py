"""Envelope router for mapping events to MCP tools.

This module provides the core routing logic that:
- Validates incoming event envelopes
- Resolves event types to MCP tools using mapping configuration
- Extracts arguments from envelope payload using dot-path syntax
- Validates bearer tokens if authentication is enabled
- Invokes tool functions and returns structured results
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel

from mcp_webhook.config import get_settings
from mcp_webhook.envelope import Envelope, Meta
from mcp_webhook.mapping import find_mapping_for_event, load_mapping_config, MappingConfig
from mcp_webhook.tools import (
    ack_event,
    process_payload,
    list_recent_events,
)


class AuthError(Exception):
    """Exception raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed") -> None:
        self.message = message
        super().__init__(self.message)


class RouterError(Exception):
    """Exception raised when routing or tool invocation fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class RoutingResponse(BaseModel):
    """Standard response from router operations.

    Attributes:
        success: Whether the routing was successful
        tool: The name of the tool that was invoked (or None if failed)
        result: The result returned by the tool (or None if failed)
        error: Error message if operation failed (or None if successful)
    """

    success: bool
    tool: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


def validate_auth(envelope: Envelope) -> None:
    """Validate bearer token authentication if enabled.

    Args:
        envelope: The envelope containing auth metadata

    Raises:
        AuthError: If authentication is required and token is invalid
    """
    settings = get_settings()

    # If auth is not enabled, skip validation
    if not settings.auth_enabled:
        return

    # If envelope has no metadata, raise error
    if envelope.meta is None:
        raise AuthError(
            "Authentication required: envelope missing 'meta' field with 'auth' token"
        )

    # Check if auth token is present
    if envelope.meta.auth is None:
        raise AuthError(
            "Authentication required: envelope missing 'auth' token in 'meta' field"
        )

    # Validate token against configured tokens
    if envelope.meta.auth not in settings.bearer_tokens_list:
        raise AuthError(
            f"Authentication failed: invalid token. "
            f"Provided token does not match any configured bearer tokens"
        )


def resolve_tool_mapping(event_type: str, mapping_config: MappingConfig) -> Dict[str, Any]:
    """Resolve event type to tool function and arguments.

    Args:
        event_type: The event type to resolve (e.g., "file.save")
        mapping_config: The mapping configuration to search

    Returns:
        Dictionary containing 'tool', 'tool_func', 'args', and 'kwargs'

    Raises:
        RouterError: If no mapping found for the event type
    """
    mapping = find_mapping_for_event(mapping_config, event_type)

    if mapping is None:
        raise RouterError(
            f"No mapping found for event type: '{event_type}'",
            details={"event_type": event_type}
        )

    # Map tool name to actual function
    tool_registry = {
        "ack_event": ack_event,
        "process_payload": process_payload,
        "list_recent_events": list_recent_events,
    }

    if mapping.tool not in tool_registry:
        raise RouterError(
            f"Tool '{mapping.tool}' is not registered",
            details={"tool": mapping.tool}
        )

    return {
        "tool": mapping.tool,
        "tool_func": tool_registry[mapping.tool],
        "args": mapping.args,
    }


def extract_tool_args(
    mapping_args: Dict[str, str],
    envelope: Envelope
) -> Dict[str, Any]:
    """Extract tool arguments from envelope using mapping templates.

    Args:
        mapping_args: Dictionary mapping argument names to dot-path templates
        envelope: The envelope containing the payload

    Returns:
        Dictionary with resolved argument values

    Raises:
        RouterError: If argument extraction fails
    """
    from mcp_webhook.envelope import extract_value

    resolved = {}

    for arg_name, dot_path in mapping_args.items():
        if not dot_path:
            raise RouterError(
                f"Argument '{arg_name}' has empty dot path in mapping",
                details={"arg_name": arg_name}
            )

        try:
            # Extract from envelope payload
            value = extract_value(envelope.payload, dot_path)
            resolved[arg_name] = value
        except (KeyError, ValueError) as e:
            raise RouterError(
                f"Failed to extract argument '{arg_name}' from envelope: {e}",
                details={"arg_name": arg_name, "dot_path": dot_path, "error": str(e)}
            )

    return resolved


def invoke_tool(
    tool_func,
    resolved_args: Dict[str, Any],
    **kwargs
) -> Dict[str, Any]:
    """Invoke a tool function with resolved arguments.

    Args:
        tool_func: The tool function to invoke
        resolved_args: Dictionary of resolved argument values
        **kwargs: Additional keyword arguments to pass to the tool

    Returns:
        Dictionary representation of the tool result

    Raises:
        RouterError: If tool invocation fails
    """
    try:
        # Merge resolved args with any additional kwargs
        all_args = {**resolved_args, **kwargs}

        # Invoke the tool function
        result = tool_func(**all_args)

        # Convert Pydantic model to dict if needed
        if hasattr(result, 'model_dump'):
            return result.model_dump()
        elif hasattr(result, 'dict'):
            return result.dict()
        else:
            return {"result": result}

    except TypeError as e:
        raise RouterError(
            f"Tool invocation failed: {e}",
            details={"error": str(e)}
        )
    except Exception as e:
        raise RouterError(
            f"Tool invocation failed: {e}",
            details={"error": str(e)}
        )


def route_envelope(
    envelope: Envelope,
    mapping_config: Optional[MappingConfig] = None
) -> RoutingResponse:
    """Route an envelope to the appropriate MCP tool.

    This is the main entry point for envelope routing. It:
    1. Validates authentication if enabled
    2. Loads mapping configuration (if not provided)
    3. Resolves the event type to a tool
    4. Extracts tool arguments from the envelope
    5. Invokes the tool synchronously or enqueues for async processing
    6. Returns the result or acknowledgement

    Args:
        envelope: The validated envelope to route
        mapping_config: Optional pre-loaded mapping configuration.
                     If None, loads from settings.

    Returns:
        RoutingResponse with the tool result or error information

    Examples:
        >>> from mcp_webhook.envelope import Envelope
        >>> envelope = Envelope(
        ...     event_type="file.save",
        ...     payload={"path": "/repo/file.py", "user": {"id": "alice"}},
        ...     meta=Meta(auth="token123")
        ... )
        >>> response = route_envelope(envelope)
        >>> response.success
        True
        >>> response.tool
        'process_payload'
    """
    try:
        # Step 1: Validate authentication
        validate_auth(envelope)

        # Step 2: Load mapping configuration
        if mapping_config is None:
            mapping_config = load_mapping_config()

        # Step 3: Resolve tool mapping
        mapping_info = resolve_tool_mapping(envelope.event_type, mapping_config)

        # Step 4: Check if async processing is enabled
        settings = get_settings()
        if settings.async_processing:
            return _route_async(envelope, mapping_info)

        # Step 5: Extract tool arguments (synchronous path)
        resolved_args = extract_tool_args(mapping_info["args"], envelope)

        # Step 6: Invoke tool synchronously
        result = invoke_tool(mapping_info["tool_func"], resolved_args)

        # Return successful response
        return RoutingResponse(
            success=True,
            tool=mapping_info["tool"],
            result=result,
            error=None,
        )

    except AuthError as e:
        # Return authentication error response
        return RoutingResponse(
            success=False,
            tool=None,
            result=None,
            error=e.message,
        )

    except RouterError as e:
        # Return routing error response
        return RoutingResponse(
            success=False,
            tool=None,
            result=None,
            error=e.message,
        )

    except Exception as e:
        # Return unexpected error response
        return RoutingResponse(
            success=False,
            tool=None,
            result=None,
            error=f"Unexpected error: {e}",
        )


def _route_async(envelope: Envelope, mapping_info: Dict[str, Any]) -> RoutingResponse:
    """Route envelope asynchronously by enqueuing for background processing.

    Args:
        envelope: The validated envelope to route
        mapping_info: Dictionary containing tool info and args

    Returns:
        RoutingResponse with acknowledgement information

    Raises:
        RuntimeError: If async worker is not running
    """
    from mcp_webhook.worker import get_worker, WorkerTask
    import uuid

    # Get worker instance
    worker = get_worker()

    # Check if worker is running
    if not worker.is_running:
        raise RuntimeError(
            "Async processing is enabled but worker is not running. "
            "Call await worker.start() first."
        )

    # Create task
    task_id = str(uuid.uuid4())
    task = WorkerTask(
        envelope_dict=envelope.model_dump(),
        mapping_info=mapping_info,
        task_id=task_id,
    )

    # Enqueue task (synchronous call)
    enqueued = worker.enqueue(task)

    if not enqueued:
        return RoutingResponse(
            success=False,
            tool=None,
            result=None,
            error="Task queue is full, please retry later",
        )

    # Return acknowledgement response
    return RoutingResponse(
        success=True,
        tool=mapping_info.get("tool"),
        result={
            "task_id": task_id,
            "status": "enqueued",
            "message": "Task has been enqueued for async processing",
        },
        error=None,
    )


def route_envelope_with_dict(
    envelope_dict: Dict[str, Any],
    mapping_config: Optional[MappingConfig] = None
) -> RoutingResponse:
    """Route an envelope from a dictionary.

    Convenience function that converts a dictionary to an Envelope
    before routing.

    Args:
        envelope_dict: Dictionary containing envelope data
        mapping_config: Optional pre-loaded mapping configuration

    Returns:
        RoutingResponse with the tool result or error information
    """
    try:
        # Validate envelope
        envelope = Envelope(**envelope_dict)
    except Exception as e:
        return RoutingResponse(
            success=False,
            tool=None,
            result=None,
            error=f"Invalid envelope: {e}",
        )

    # Route the validated envelope
    return route_envelope(envelope, mapping_config)
