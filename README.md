# MCP STDIO Webhook Server

A lightweight Python MCP (Model Context Protocol) server that accepts event envelopes and maps them to MCP tools. This server uses the STDIO transport and can be deployed with Docker Compose in a one-click style using a stdio-proxy (TCP bridge).

## Overview

This project provides a robust MCP server that:
- Communicates over STDIO internally with MCP clients
- Exposes an easy-to-use TCP endpoint via a proxy/bridge for Docker deployments
- Supports optional bearer-token authentication
- Maps received event envelopes to registered MCP tools using configurable mappings
- Supports both synchronous and asynchronous processing modes

## Features

### Core Features (MVP)
- ✅ STDIO-based MCP server using `FastMCP` and the MCP Python SDK
- ✅ Envelope router with configurable event-to-tool mappings
- ✅ Optional bearer-token authentication (empty tokens = auth disabled)
- ✅ TCP bridge (stdio-proxy) for Docker deployment
- ✅ JSON structured logging
- ✅ Example tools: `ack_event`, `process_payload`, `list_recent_events`

### Planned Features
- 🔜 In-memory recent event log
- 🔜 In-process worker pool for async jobs
- 🔜 Optional Redis-backed queue
- 🔜 Example stdio client script
- 🔜 Prometheus metrics stub

## Quick Start

### Prerequisites
- Docker and Docker Compose
- (Optional) Python 3.11+ for local development

### Docker Compose Deployment

1. Clone the repository:
```bash
git clone <repository-url>
cd mcp_webhook_python_zed
```

2. Copy the example environment file:
```bash
cp .env.example .env
```

3. Configure your environment (optional):
```bash
# Edit .env to customize PORT, WEBHOOK_BEARER_TOKENS, etc.
```

4. Create a mapping configuration:
```bash
cp config/mapping.yml.example config/mapping.yml
```

5. Start the server:
```bash
docker-compose up --build
```

The server will be available at `tcp://localhost:9000` (default port).

### Testing the Connection

Send a test envelope using netcat (for basic TCP testing):
```bash
printf '%s\n' '{"type":"event","event_type":"file.save","payload":{"path":"/repo/file.py"},"meta":{"auth":"token1"}}' | nc localhost 9000
```

Note: This is a simple TCP test. Full MCP stdio framing is required for production usage.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 9000 | Port for stdio-proxy TCP listener |
| `MCP_NAME` | MCP-STDIO-Server | Human-friendly server name |
| `WEBHOOK_BEARER_TOKENS` | (empty) | Comma-separated bearer tokens (empty = auth disabled) |
| `ASYNC_PROCESSING` | false | Enable async processing mode |
| `MAPPING_FILE` | /app/config/mapping.yml | Path to event mapping configuration |
| `LOG_LEVEL` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |

### Event Mapping Configuration

Create a `mapping.yml` file to define how events map to tools:

```yaml
mappings:
  - event: "file.save"
    tool: "process_payload"
    args:
      path: payload.path
      user_id: payload.user.id
  
  - event: "file.open"
    tool: "ack_event"
    args:
      file: payload.path
```

## Envelope Format

Events are sent as JSON envelopes:

```json
{
  "type": "event",
  "event_type": "file.save",
  "payload": {
    "path": "/repo/file.py",
    "user": {
      "id": "alice"
    }
  },
  "meta": {
    "auth": "token1",
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-01-06T12:00:00Z"
  }
}
```

### Envelope Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Must be "event" |
| `event_type` | string | Yes | Event identifier for mapping |
| `payload` | object | Yes | Event data (any structure) |
| `meta.auth` | string | Conditional | Bearer token (required if auth enabled) |
| `meta.id` | string | No | Unique event identifier |
| `meta.timestamp` | string | No | ISO 8601 timestamp |

## Architecture

```
┌─────────────┐     TCP      ┌──────────────┐     STDIO      ┌─────────────┐
│   Client    │ ◄──────────► │ stdio-proxy  │ ◄────────────► │ MCP Server  │
│             │  Port: 9000   │ (TCP Bridge) │  Framing       │  (FastMCP)  │
└─────────────┘               └──────────────┘                └─────────────┘
                                     │
                                     ▼
                              ┌──────────────┐
                              │ Envelope     │
                              │ Router       │
                              └──────────────┘
                                     │
                                     ▼
                              ┌──────────────┐
                              │ MCP Tools    │
                              │ (ack_event,  │
                              │  process_    │
                              │  payload,    │
                              │  list_recent)│
                              └──────────────┘
```

### Components

1. **Client**: Connects via TCP to the stdio-proxy
2. **stdio-proxy**: TCP bridge that forwards data to/from server STDIO
3. **MCP Server**: FastMCP-based server handling MCP protocol
4. **Envelope Router**: Maps events to tools and validates auth
5. **MCP Tools**: Executable functions that process events

## Available MCP Tools

### `ack_event`
Acknowledges an event and returns a confirmation.
```python
# Parameters: event_type: str, payload: dict
# Returns: {"status": "acknowledged", "event_type": "..."}
```

### `process_payload`
Processes a payload with path and user information.
```python
# Parameters: path: str, user_id: str
# Returns: {"processed": true, "path": "...", "user_id": "..."}
```

### `list_recent_events`
Returns the list of recently processed events.
```python
# Parameters: None
# Returns: {"events": [...]}
```

## Development

### Local Development Setup

1. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -e ".[dev]"
```

3. Run tests:
```bash
pytest
```

4. Run linting:
```bash
ruff check src/
black src/
isort src/
```

### Project Structure

```
mcp_webhook_python_zed/
├── src/
│   └── mcp_webhook/
│       ├── __init__.py
│       ├── config.py          # Configuration management
│       ├── mapping.py         # Event-to-tool mapping parser
│       ├── envelope.py        # Envelope Pydantic models
│       ├── tools.py           # MCP tool implementations
│       ├── router.py          # Envelope routing logic
│       ├── worker.py          # Async worker (optional)
│       ├── server.py          # FastMCP server bootstrap
│       └── proxy.py           # stdio-proxy (TCP bridge)
├── config/
│   ├── mapping.yml.example    # Example mapping configuration
│   └── .env.example           # Example environment variables
├── tests/
│   ├── unit/                  # Unit tests
│   └── integration/           # Integration tests
├── examples/
│   └── stdio_client.py       # Example client implementation
├── docker/
│   └── entrypoint.sh         # Docker entrypoint script
├── docker-compose.yml        # Docker Compose configuration
├── Dockerfile                # Docker image definition
├── pyproject.toml           # Python project configuration
├── README.md                # This file
├── Planning.md              # Project planning document
└── Task.md                  # Task tracking
```

## Testing

### Unit Tests
```bash
# Run all unit tests
pytest tests/unit/

# Run specific test file
pytest tests/unit/test_config.py

# Run with coverage
pytest --cov=src --cov-report=html
```

### Integration Tests
```bash
# Run all integration tests
pytest tests/integration/

# Run specific integration test
pytest tests/integration/test_stdio_proxy.py
```

### End-to-End Test with Docker
```bash
# Build and start the service
docker-compose up --build

# Run the example client (from another terminal)
python examples/stdio_client.py

# Verify logs for processed events
docker-compose logs -f mcp-stdio
```

## Security

### Authentication
- Bearer tokens are stored in environment variables
- When `WEBHOOK_BEARER_TOKENS` is empty, authentication is disabled
- In production, use proper secret management (e.g., Docker secrets, Vault)

### Recommendations
- Run behind a firewall or in a secure network
- Use an external proxy (e.g., Traefik, Nginx) for TLS termination
- Rotate bearer tokens regularly
- Enable structured logging for audit trails

## Troubleshooting

### Port Already in Use
```bash
# Find process using port 9000
netstat -ano | findstr :9000  # Windows
lsof -i :9000                 # macOS/Linux

# Change port in .env
PORT=9001
```

### Connection Refused
- Verify the container is running: `docker-compose ps`
- Check logs: `docker-compose logs mcp-stdio`
- Ensure firewall allows connections to the configured port

### Authentication Failures
- Verify `WEBHOOK_BEARER_TOKENS` matches the token in envelope meta
- Check that `meta.auth` field is present in the envelope
- Review logs for detailed error messages

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes and write tests
4. Run tests: `pytest`
5. Run linting: `ruff check src/ && black src/ && isort src/`
6. Commit your changes: `git commit -m "Add my feature"`
7. Push to the branch: `git push origin feature/my-feature`
8. Open a Pull Request

## License

MIT License - see LICENSE file for details

## Roadmap

See [Planning.md](Planning.md) for detailed project planning and [Task.md](Task.md) for task tracking.

### Upcoming Features
- [ ] Enhanced admin tooling
- [ ] Per-client token management
- [ ] Multi-tenant support
- [ ] Kubernetes manifests / Helm chart
- [ ] OAuth or HMAC signing flows
- [ ] Prometheus metrics integration

## Support

For issues, questions, or contributions, please open an issue on the project repository.