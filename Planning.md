# MCP STDIO Webhook Server — Planning

Last updated: 2026-01-06

This document captures the high-level plan for a lightweight Python MCP server that:
- Uses the MCP Python SDK (`mcp[cli]`) with the STDIO transport.
- Accepts event envelopes from clients and maps them to MCP tools.
- Is deployable with Docker Compose in a one-click style using a stdio-proxy (TCP bridge).
- Uses optional bearer-token authentication (empty tokens = auth disabled).

Contents
- Core Functionality
- Features
- Out of Scope
- Tech Stack
- Architecture
- Envelope format
- Deployment (docker-compose + stdio-proxy)
- Testing
- Next steps

---

## Core Functionality

Goal
- Provide a small, robust MCP server that communicates over STDIO internally and exposes an easy-to-use TCP endpoint (via a proxy/bridge) for clients when deployed with Docker Compose.
- Provide optional bearer-token auth for incoming event envelopes.

MVP requirements
- STDIO-based MCP server using `FastMCP` and the SDK's stdio transport.
- `POST`-like event handling over STDIO:
  - Accept structured JSON envelopes sent by clients over the STDIO channel (or via the TCP bridge).
  - Optionally validate a bearer token included in the envelope metadata.
  - Map received events to registered MCP `@mcp.tool()` calls using a configurable mapping.
  - Support synchronous processing (return tool result) or asynchronous processing (ack + background worker).
- Docker Compose deployment:
  - Container runs STDIO server + stdio-proxy (TCP bridge) so host clients can connect to a port (e.g., 9000).
  - Configuration via environment variables (token list, port, async toggle, mapping file path).
- Observability:
  - JSON structured logs to stdout/stderr.
  - Example admin tooling exposed as MCP tools (e.g., `list_recent_events`), not an HTTP admin endpoint.

Acceptance criteria
- Developer can run `docker-compose up --build`.
- Client can connect to `tcp://localhost:9000` and perform MCP stdio connect/requests.
- Optional bearer-token validation can be enabled/disabled via environment variables.

---

## Features

MVP (must-have)
- STDIO MCP server implemented with `FastMCP`:
  - Example tools: `ack_event`, `process_payload`.
  - Tools return structured outputs (Pydantic models where appropriate).
- Envelope router:
  - Mapping config (YAML/JSON) mapping `event_type` -> `tool` + argument extraction rules.
  - Bearer-token support:
    - `WEBHOOK_BEARER_TOKENS` env var (comma-separated); empty disables auth.
- stdio-proxy (TCP bridge):
  - Listens on configurable port (default 9000).
  - Forwards bytes to/from server stdin/stdout so host clients can connect over TCP.
- Docker Compose:
  - `docker-compose.yml` that builds and exposes port(s).
  - `.env.example` for configuration.
- README with quickstart, sample envelopes, and example client usage.

Near-term (nice-to-have)
- In-memory recent event log exposing last N events via MCP tool.
- In-process worker pool for async jobs (configurable).
- Optional Redis-backed queue (enabled via compose profile).
- Example stdio client script that opens a socket to the proxy and implements MCP stdio framing.
- Prometheus metrics stub for request counts and processing durations.

Long-term / optional
- Per-client token management UI.
- Multi-tenant support.
- Kubernetes manifests / Helm chart (separate deliverable).
- Full OAuth or HMAC signing flows.

---

## Out of Scope (for initial MVP)

- HTTP webhook endpoints — we intentionally use STDIO for local/IDE integrations.
- IDE plugins — we will provide example client scripts instead.
- Hosted SaaS / secret management.
- Complex database persistence (only light in-memory or optional Redis).
- Kubernetes / Helm (deferred).

---

## Tech Stack

- Python 3.11+
- Primary SDK: `mcp[cli]` (Model Context Protocol Python SDK)
- Pydantic for schemas and structured tool output
- Minimal ASGI tooling (not required for STDIO MVP)
- For TCP bridging: `socat` or a tiny Python-based bridge (we will prefer a Python bridge so Docker image stays consistent and portable)
- Docker + docker-compose for the 1-click deployment
- Testing:
  - `pytest`, `pytest-asyncio`
  - `asyncio` subprocess helpers for STDIO testing
  - `httpx` optional (only if we add HTTP bits)
- Linting/formatting:
  - `black`, `ruff`, `isort`

Configuration (env vars)
- PORT — port for stdio-proxy listener (default: 9000)
- MCP_NAME — human-friendly server name
- WEBHOOK_BEARER_TOKENS — comma-separated tokens; empty disables auth
- ASYNC_PROCESSING — "true"/"false"
- MAPPING_FILE — mapping config path inside container (default: `/app/config/mapping.yml`)
- LOG_LEVEL — default INFO

---

## Architecture

Overview
- Single container runs:
  - MCP STDIO server (child process spawned by the entrypoint).
  - stdio-proxy (TCP listener) that forwards data to server stdin/stdout.
- Envelope Router (module):
  - Receives parsed envelopes passed into the server (tools may call into it or server routes envelopes to it).
  - Validates token (if enabled) and maps events to tools.
- Worker (optional):
  - In-process worker pool for asynchronous/long-running tool calls.
- Storage:
  - In-memory ring buffer for recent events (for quick inspection via MCP tool).
  - Optional Redis queue if `async` profile enabled.

Data flow
1. Client connects to `localhost:PORT` (TCP) and speaks MCP STDIO framing.
2. stdio-proxy forwards incoming bytes to the STDIO server's stdin.
3. Server decodes MCP messages and routes event envelopes to Envelope Router.
4. Envelope Router extracts event_type, verifies auth (if enabled), renders arguments per mapping rules, invokes appropriate `@mcp.tool()`.
5. Tool returns structured output; server returns response back over STDIO -> proxy -> client.

Security
- Optional bearer tokens stored in env var; document proper production secret management.
- Recommend running behind local firewall / secure network for production deployments.
- No TLS termination inside the container; recommend external proxy (e.g., Traefik) if TLS is required.

StdIO-proxy design notes
- Implement proxy inside container as a small Python program:
  - Launch the server process as a subprocess with pipes.
  - Create a TCP server listening on port `PORT`.
  - For each accepted TCP connection, connect the socket data to the subprocess's stdin and send subprocess stdout back to the socket.
  - Ensure binary-safe forwarding; handle disconnects and process termination.
- Use `asyncio` for the proxy for robustness.

---

## Envelope format

Design goal: simple, extensible envelope that is easy to validate with Pydantic.

Suggested envelope (JSON) structure:
```mcp_webhook_python_zed/example_envelope.json#L1-6
{
  "type": "event",
  "event_type": "file.save",
  "payload": { "path": "/repo/file.py", "user": { "id": "alice" } },
  "meta": { "auth": "token1", "id": "uuid", "timestamp": "2026-01-06T12:00:00Z" }
}
```

Mapping example (YAML)
```mcp_webhook_python_zed/config/mapping.yml#L1-20
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

Argument extraction
- We will support a simple dot-path extraction syntax (e.g., `payload.user.id`) and basic defaulting.
- If extraction fails for required args, server returns an error to client.

Auth
- If `WEBHOOK_BEARER_TOKENS` is empty, auth is disabled.
- If set, router requires `envelope.meta.auth` to match one of the tokens (exact match).
- Provide clear error messages over the MCP channel for auth failures.

---

## Deployment (docker-compose + stdio-proxy)

Rationale
- STDIO transport is designed for local process integration.
- To make docker-compose 1‑click usable, we provide a TCP bridge inside the container so host clients can connect to a port.

Example `docker-compose.yml` (planning-level)
```mcp_webhook_python_zed/docker-compose.yml#L1-30
version: "3.9"
services:
  mcp-stdio:
    build: .
    image: mcp-webhook-stdio:latest
    environment:
      - PORT=9000
      - MCP_NAME=MCP-STDIO-Server
      - WEBHOOK_BEARER_TOKENS=${WEBHOOK_BEARER_TOKENS:-}
      - ASYNC_PROCESSING=false
      - MAPPING_FILE=/app/config/mapping.yml
    ports:
      - "9000:9000"
    volumes:
      - ./config:/app/config:ro
    restart: unless-stopped
```

Entrypoint behavior (high-level)
- Run `entrypoint.sh` which:
  - Reads env config.
  - Launches the MCP stdio server subprocess (e.g., `python -m mcp.server.fastmcp` or similar).
  - Starts the stdio-proxy listening on `$PORT`.
  - Supervises both processes and handles signals gracefully.

Client connection
- After `docker-compose up --build`, a client can connect to `localhost:9000` and perform MCP stdio handshake and calls.
- Provide a small example client script in `examples/` to demonstrate the framing.

Example client usage (planning-level)
```mcp_webhook_python_zed/example_curl.sh#L1-6
# Note: raw TCP test only; MCP framing details are required for production usage.
printf '%s\n' '{"type":"event","event_type":"file.save","payload":{"path":"/repo/file.py"},"meta":{"auth":"token1"}}' | nc localhost 9000
```

(Important: the real MCP STDIO transport uses a framed message format — the above JSON is illustrative for planning. The actual client will use framing per MCP stdio examples from the SDK.)

---

## Testing

Unit tests
- Envelope parsing & validation using Pydantic.
- Mapping logic: correct arg extraction given mapping rules and sample payloads.
- Auth behavior: tokens empty vs tokens present; valid and invalid token tests.
- Tool function unit tests (structured outputs validated).

Integration tests (local)
- Use `asyncio` subprocess helpers to spawn the server locally and connect via a fake client over TCP to the stdio-proxy.
- Run a sample sequence:
  - Perform MCP stdio initialization (handshake).
  - Send an event envelope and assert the returned structured result.
- Test both synchronous and async processing paths.

CI tests (docker-compose)
- Optional GH Actions job that:
  - Builds the Docker image.
  - Brings up `docker-compose` services.
  - Runs the example client that connects to `localhost:9000` and exercises key flows.
  - Tears down services.

Test tooling
- `pytest` + `pytest-asyncio`.
- Use `asyncio` tests to simulate TCP clients and server subprocesses.

Acceptance criteria for testing
- End-to-end envelope -> routing -> tool -> response path covered in tests.
- Auth verifying behavior tested in both enabled and disabled modes.
- CI includes at least unit + integration smoke test.

---

## Next steps

Pick one of the following and I will take it on next:
1. Scaffold the repository (file layout, `pyproject.toml`, `Dockerfile`, `entrypoint.sh` stub, `src/` modules, `docker-compose.yml`, `config/.env.example`, `config/mapping.yml.example`, and `README.md` draft).
2. Implement MVP: STDIO server, stdio-proxy, envelope router, mapping, tools, and tests.
3. Produce an implementation checklist split into epics and tasks (work items ready for issues).

I recommend starting with (1) scaffold so you can review structure before I implement the code.

---

## Notes and decisions

- STDIO transport chosen to support tight IDE integrations.
- Docker Compose + stdio-proxy chosen to provide one-click host connectivity while preserving STDIO-based server internals.
- Bearer tokens kept optional — empty env means auth disabled.
- Mapping config uses simple dot-path extraction; we will keep logic minimal and strict for MVP.
- The proxy will be Python-based (asyncio) to avoid additional OS dependencies, keep image portable, and make behavior easy to test.

---