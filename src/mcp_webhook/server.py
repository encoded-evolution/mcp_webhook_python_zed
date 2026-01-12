"""FastMCP STDIO server for MCP webhook server.

This module provides a FastMCP server bootstrap that:
- Constructs FastMCP instance with configurable server name
- Registers MCP tools from tools.py
- Exposes admin tools for monitoring recent events
- Runs server with STDIO transport for IDE integration
- Configures structured JSON logging and collects basic metrics
"""

from typing import Any, Dict
import logging
from collections import defaultdict

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from mcp_webhook.config import get_settings, configure_logging
from mcp_webhook.tools import (
    ack_event,
    process_payload,
    list_recent_events,
    AckEventResponse,
    ProcessPayloadResponse,
    ListRecentEventsResponse,
)
from mcp_webhook.router import envelope_router


# Configure structured JSON logging
logger = configure_logging(get_settings())

# Simple metrics stub - tracks request counts by tool and result
# In production, this could be extended to track duration, errors, etc.
_metrics: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))


def increment_metric(metric_name: str, status: str = "success") -> None:
    """Increment a metric counter.

    Args:
        metric_name: The metric name (e.g., "tool.invocations")
        status: The status (e.g., "success", "error", "timeout")
    """
    _metrics[metric_name][status] += 1


def get_metrics() -> Dict[str, Dict[str, int]]:
    """Get current metrics snapshot.

    Returns:
        Dictionary of metric_name -> status -> count
    """
    # Convert nested defaultdicts to regular dicts
    return {
        metric_name: dict(status_counts)
        for metric_name, status_counts in _metrics.items()
    }


def reset_metrics() -> None:
    """Reset all metrics counters.

    Useful for testing and for periodic export in production.
    """
    global _metrics
    _metrics.clear()


# Create FastMCP instance
# The name is loaded from configuration
_settings = get_settings()
mcp = FastMCP(name=_settings.mcp_name)


@mcp.tool()
async def ack_event_tool(
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Acknowledge receipt of an event.

    This tool simply acknowledges that an event was received.
    It's useful for testing and for events that don't require processing.

    Args:
        event_type: The type of event being acknowledged
        payload: The event payload (for logging purposes)

    Returns:
        A structured response indicating successful acknowledgement
    """
    logger.info(f"Acknowledging event: {event_type}", extra={"event_type": event_type})
    increment_metric("ack_event_tool", "success")

    result = ack_event(event_type=event_type, payload=payload)
    return result.model_dump()


@mcp.tool()
async def process_payload_tool(
    path: str,
    user_id: str,
) -> dict[str, Any]:
    """Process a file payload.

    This tool simulates processing of a file path for a given user.
    In a real implementation, this could trigger file analysis,
    linting, or other operations.

    Args:
        path: The file path to process
        user_id: The user who is requesting to processing

    Returns:
        A structured response with processing results
    """
    logger.info(
        f"Processing payload for user {user_id}: {path}",
        extra={"user_id": user_id, "path": path}
    )
    increment_metric("process_payload_tool", "success")

    result = process_payload(path=path, user_id=user_id)
    return result.model_dump()


@mcp.tool()
async def list_recent_events_tool(
    max_count: int = 10,
) -> dict[str, Any]:
    """List recently processed events.

    Returns a list of events that have been processed, stored in an
    in-memory buffer. Useful for debugging and monitoring.

    Args:
        max_count: Maximum number of events to return. Defaults to 10.

    Returns:
        A structured response containing recent events
    """
    logger.info(f"Listing recent events (max_count={max_count})")
    increment_metric("list_recent_events_tool", "success")

    result = list_recent_events(max_count=max_count)
    return result.model_dump()


@mcp.tool()
async def get_server_info() -> dict[str, Any]:
    """Get information about the MCP webhook server.

    Returns configuration and runtime information about the server,
    including metrics for observability.

    Returns:
        A structured response with server information
    """
    settings = get_settings()

    logger.info("Server info requested")

    info = {
        "name": settings.mcp_name,
        "port": settings.port,
        "auth_enabled": settings.auth_enabled,
        "async_processing": settings.async_processing,
        "log_level": settings.log_level,
        "mapping_file": settings.mapping_file,
        "metrics": get_metrics(),
    }

    return info


@mcp.tool()
async def get_metrics_tool() -> dict[str, Any]:
    """Get server metrics.

    Returns current metrics including request counts by tool and status.
    Useful for monitoring server health and performance.

    Returns:
        A structured response with current metrics
    """
    logger.info("Metrics requested")

    metrics = get_metrics()
    return metrics


@mcp.tool()
async def envelope_router_tool(
    envelope: dict[str, Any],
) -> dict[str, Any]:
    """Route an event envelope to the appropriate MCP tool.

    This tool accepts an event envelope, validates it, and routes it
    to the appropriate tool based on the event type mapping configuration.

    Args:
        envelope: Dictionary containing envelope data with structure:
            {
                "type": "event",
                "event_type": str,
                "payload": dict,
                "meta": {
                    "auth": str (optional),
                    "id": str (optional),
                    "timestamp": str (optional)
                }
            }

    Returns:
        Dictionary with routing result:
            {
                "success": bool,
                "tool": str | None,
                "result": dict | None,
                "error": str | None
            }
    """
    logger.info(f"Routing envelope: {envelope.get('event_type', 'unknown')}")
    increment_metric("envelope_router_tool", "success")

    result = envelope_router(envelope)
    return result


@mcp.tool()
async def reset_metrics_tool() -> dict[str, Any]:
    """Reset server metrics.

    Useful for testing and for clearing metrics after specific periods.
    In production, metrics might be reset periodically (e.g., daily).

    Returns:
        A structured response confirming metrics reset
    """
    logger.info("Resetting metrics")
    reset_metrics()

    return {
        "success": True,
        "message": "Metrics have been reset",
    }


def run_stdio_server() -> None:
    """Run the MCP server with STDIO transport.

    This is the main entry point for running the server.
    It blocks and communicates via stdin/stdout using MCP protocol.

    The server will:
    - Accept MCP protocol messages over STDIO
    - Route requests to registered tools
    - Return responses in MCP protocol format
    - Log using structured JSON format
    - Collect basic metrics
    """
    logger.info("=" * 60)
    logger.info("MCP STDIO Server initializing...")
    logger.info("=" * 60)

    settings = get_settings()

    logger.info(f"Starting MCP STDIO server: {settings.mcp_name}")
    logger.info(f"Auth enabled: {settings.auth_enabled}")
    logger.info(f"Async processing: {settings.async_processing}")
    logger.info(f"Port: {settings.port}")
    logger.info(f"Mapping file: {settings.mapping_file}")

    try:
        logger.info("Starting FastMCP server loop (blocking on STDIO)...")
        mcp.run()
        logger.info("FastMCP server loop exited normally")
    except KeyboardInterrupt:
        logger.info("Server shutdown requested via KeyboardInterrupt")
        increment_metric("server", "shutdown")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        increment_metric("server", "error")
        raise


def main() -> None:
    """Main entry point for the MCP webhook server.

    This function is used as a console script entry point and
    simply calls run_stdio_server().
    """
    run_stdio_server()


if __name__ == "__main__":
    logger.info("Server process starting (as subprocess)...")
    try:
        main()
        logger.info("Server process completed")
    except Exception as e:
        logger.error(f"Server process crashed: {e}", exc_info=True)
        raise
