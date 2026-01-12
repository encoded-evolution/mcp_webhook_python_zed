"""
MCP STDIO Webhook Server

A lightweight Python MCP server that accepts event envelopes and maps them to MCP tools.
"""

from mcp_webhook.config import JSONFormatter

__version__ = "0.1.0"

__all__ = ["__version__", "JSONFormatter"]
