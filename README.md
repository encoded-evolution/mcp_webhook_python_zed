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

### Additional Features (Implemented)
- ✅ In-memory recent event log (via `list_recent_events` tool)
- ✅ In-process worker pool for async jobs (configurable via `ASYNC_PROCESSING`)
- ✅ Comprehensive testing (unit + integration)
- ✅ CI/CD pipeline with GitHub Actions

### Optional/Future Features
- ✅ Redis-backed queue for high-throughput scenarios (use with `--profile async`)
- 🔜 Example stdio client script (see Task 150)
- 🔜 Prometheus metrics integration

## Quick Start

### Prerequisites
- Docker and Docker Compose
- (Optional) Python 3.11+ for local development

### Docker Compose Deployment

1. Clone the repository:
```bash
git clone https://github.com/encoded-evolution/mcp_webhook_python_zed.git
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

**Quick TCP Test (netcat)**
Send a test envelope using netcat (for basic connectivity testing):
```bash
printf '%s\n' '{"type":"event","event_type":"file.save","payload":{"path":"/repo/file.py"},"meta":{"auth":"token1"}}' | nc localhost 9000
```

**Using the Example Client**
For proper MCP stdio framing, use the example client:
```bash
python examples/stdio_client.py --event file.save --path /repo/file.py --auth token1
```

**Note**: The netcat test is for basic TCP connectivity only. Full MCP stdio framing is required for production usage. See `examples/stdio_client.py` for a complete client implementation.

## MCP Client Configuration

This server can be used with any MCP-compatible client (Claude Desktop, VS Code MCP extension, etc.) by configuring the client to connect via Docker.

### Prerequisites

1. Pull the Docker image:
```bash
docker pull encoded-evolution/mcp-webhook-stdio:0.1.0
```

2. Create a local configuration directory:
```bash
mkdir -p ~/.config/mcp-webhook
cp config/mapping.yml.example ~/.config/mcp-webhook/mapping.yml
```

### Claude Desktop Configuration

Add the following to your Claude Desktop configuration file (`claude_desktop_config.json`):

**Minimal configuration (no auth, default settings):**
```json
{
  "mcpServers": {
    "mcp-webhook": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-p", "9000:9000",
        "encoded-evolution/mcp-webhook-stdio:latest"
      ]
    }
  }
}
```

**Full configuration with all settings:**
```json
{
  "mcpServers": {
    "mcp-webhook": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "PORT=9000",
        "-e", "MCP_NAME=My-Webhook-Server",
        "-e", "WEBHOOK_BEARER_TOKENS=your-secret-token-1,another-token-2",
        "-e", "ASYNC_PROCESSING=false",
        "-e", "LOG_LEVEL=INFO",
        "-e", "REDIS_URL=",
        "-e", "MAPPING_FILE=/app/config/mapping.yml",
        "-v", "${HOME}/.config/mcp-webhook:/app/config:ro",
        "-p", "9000:9000",
        "encoded-evolution/mcp-webhook-stdio:latest"
      ]
    }
  }
}
```

### VS Code MCP Extension Configuration
### Claude Desktop Configuration

Add to your Claude Desktop config file (`claude_desktop_config.json` on macOS/Linux or `claude_desktop_config.json` in `%APPDATA%\Claude\` on Windows):

**Option 1: Using docker compose (recommended for multiple clients)**

```json
{
  "mcpServers": {
    "mcp-webhook": {
      "transport": {
        "type": "tcp",
        "host": "localhost",
        "port": 9000
      }
    }
  }
}
```
### VS Code MCP Extension Configuration

Add to your VS Code settings (`settings.json`):

**Option 1: Using docker compose (recommended for multiple clients)**

```json
{
  "mcp.servers": {
    "mcp-webhook": {
      "transport": {
        "type": "tcp",
        "host": "localhost",
        "port": 9000
      }
    }
  }
}
```

**Option 2: Using individual container (one client per container)**

```json
{
  "mcp.servers": {
    "mcp-webhook": {
      "transport": {
        "type": "stdio",
        "command": "docker",
        "args": [
          "run", "--rm", "-i",
          "-e", "PORT=9000",
          "-e", "MCP_NAME=My-Webhook-Server",
          "-e", "WEBHOOK_BEARER_TOKENS=your-secret-token-1,another-token-2",
          "-e", "ASYNC_PROCESSING=false",
          "-e", "LOG_LEVEL=INFO",
          "-e", "REDIS_URL=",
          "-e", "MAPPING_FILE=/app/config/mapping.yml",
          "-v", "${env:HOME}/.config/mcp-webhook:/app/config:ro",
          "-p", "9000:9000",
          "encoded-evolution/mcp-webhook-stdio:latest"
        ]
      }
    }
  }
}
```

### Zed Configuration

**Option 1: Using docker compose (recommended - server already running)**

First, start the server:
```bash
cd mcp_webhook_python_zed
docker compose up
```

Then configure Zed (open settings.json):

```json
{
  "lsp": {
    "mcp": {
      "mcp-webhook": {
        "transport": {
          "type": "tcp",
          "host": "localhost",
          "port": 9000
        }
      }
    }
  }
}
```

**Option 2: Using individual container (server starts with Zed)**

Configure Zed (open settings.json):

```json
{
  "lsp": {
    "mcp": {
      "mcp-webhook": {
        "command": "docker",
        "args": [
          "run", "--rm", "-i",
          "-p", "9000:9000",
          "encoded-evolution/mcp-webhook-stdio:latest"
        ]
      }
    }
  }
}
```

**Important:** Do not use Option 2 if you already have `docker compose up` running, as it will cause a port conflict on 9000.

### TCP Transport (For Other Clients)

If your MCP client supports direct TCP connections, you can connect directly to the TCP proxy:

```json
{
  "mcpServers": {
    "mcp-webhook-tcp": {
      "transport": {
        "type": "tcp",
        "host": "localhost",
        "port": 9000
      }
    }
  }
}
```

### Environment Variables for Client Configuration

| Variable | Purpose | Default | Example |
|----------|---------|---------|---------|
| `PORT` | Port for stdio-proxy listener | `9000` | `9000` |
| `MCP_NAME` | Human-readable server name | `MCP-STDIO-Server` | `My-Webhook-Server` |
| `WEBHOOK_BEARER_TOKENS` | Comma-separated auth tokens (empty = no auth) | `` (disabled) | `token1,token2,token3` |
| `ASYNC_PROCESSING` | Enable async worker pool | `false` | `true` |
| `LOG_LEVEL` | Logging verbosity | `INFO` | `DEBUG`, `WARNING`, `ERROR` |
| `REDIS_URL` | Redis connection URL for async queue (optional) | `` (disabled) | `redis://localhost:6379/0` |
| `MAPPING_FILE` | Path to event mapping config | `/app/config/mapping.yml` | `/app/config/custom-mapping.yml` |

### Testing the Connection

After configuring your MCP client:

**If using docker compose:**

1. Verify the container is running:
```bash
docker ps | grep mcp-webhook
```

2. Check logs for startup:
```bash
docker logs mcp-webhook-server
```

3. Test TCP connection (optional):
```bash
nc -zv localhost 9000
```

4. Look for successful client connection in logs:
```bash
docker logs -f mcp-webhook-server
```

**If using individual container:**

1. Start your MCP client (Zed, Claude Desktop, etc.)
2. Client will automatically start the Docker container
3. Check logs from container:
```bash
docker ps | grep mcp-webhook-stdio
docker logs <container-id>
```

4. Restart your MCP client if you make configuration changes

### Common Issues

#### Port Already in Use

If using docker compose and seeing port conflicts, ensure you're not running multiple MCP clients configured for STDIO transport. Use TCP transport instead.

#### Connection Refused

Ensure the container is running before trying to connect with TCP transport. Check with `docker ps`.

#### Authentication Failures

**Container not starting:** Check Docker is running and the image is pulled correctly.

**Port already in use:** Change the port in your client configuration:
```json
"-e", "PORT=9001",
"-p", "9001:9001",
```

**Authentication errors:** Ensure the token in your envelope matches one of the configured `WEBHOOK_BEARER_TOKENS`.

**Configuration file not found:** Verify the volume mount path matches where your mapping file is located on the host.

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
| `REDIS_URL` | (empty) | Redis connection URL (e.g., redis://redis:6379/0); empty uses in-memory queue |

### Using Redis-Backed Async Queue

For higher throughput scenarios, you can enable a Redis-backed queue instead of the in-memory queue:

1. Start the services with the async profile:
```bash
docker-compose --profile async up --build
```

2. Set the `REDIS_URL` environment variable in your `.env` file:
```bash
REDIS_URL=redis://redis:6379/0
ASYNC_PROCESSING=true
```

3. The server will automatically use Redis for task queuing when:
   - `REDIS_URL` is configured and non-empty
   - The `aioredis` package is installed (included in `[redis]` optional dependency)

**Benefits of Redis Queue:**
- Persistent queue that survives container restarts
- Multiple worker processes can share the same queue
- Better for high-throughput scenarios
- Tasks are stored in a Redis list and processed by worker coroutines

**Note:** When Redis is unavailable, the server will fall back to the in-memory queue automatically and log a warning.

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
                              │ Async Worker │
                              │ (in-memory   │
                              │  or Redis)   │
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

### 2. Install dependencies:
```bash
# For basic development
pip install -e ".[dev]"

# For Redis queue support (optional)
pip install -e ".[dev,redis]"
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

## Upcoming Features
- [ ] Enhanced admin tooling
- [ ] Per-client token management
- [ ] Multi-tenant support
- [ ] Kubernetes manifests / Helm chart
- [ ] OAuth or HMAC signing flows
- [ ] Prometheus metrics integration
- [ ] Example stdio client script

## Support

For issues, questions, or contributions, please open an issue on the project repository.
