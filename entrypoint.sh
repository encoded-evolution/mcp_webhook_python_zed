#!/bin/bash
set -e

# Entrypoint script for MCP Webhook STDIO Server
# This script starts the stdio-proxy which manages both:
# - The TCP listener for client connections
# - The MCP server subprocess (STDIO-based)
#
# All configuration is done via environment variables

echo "=========================================="
echo "MCP Webhook STDIO Server"
echo "=========================================="

# Display configuration (without exposing sensitive tokens)
echo "Configuration:"
echo "  Server Name: ${MCP_NAME:-MCP-STDIO-Server}"
echo "  Port: ${PORT:-9000}"
echo "  Async Processing: ${ASYNC_PROCESSING:-false}"
echo "  Log Level: ${LOG_LEVEL:-INFO}"
echo "  Mapping File: ${MAPPING_FILE:-/app/config/mapping.yml}"
if [ -n "$WEBHOOK_BEARER_TOKENS" ]; then
  echo "  Authentication: ENABLED (tokens configured)"
else
  echo "  Authentication: DISABLED"
fi
echo "=========================================="

# Ensure config directory exists
mkdir -p /app/config

# Check if mapping file exists
if [ ! -f "$MAPPING_FILE" ]; then
  echo "Warning: Mapping file not found at $MAPPING_FILE"
  echo "The server will start but may not have any event mappings configured."
fi

# Run the stdio-proxy
# Using exec ensures that the proxy process replaces the shell,
# which allows proper signal handling (SIGTERM, SIGINT)
exec python -m mcp_webhook.proxy
