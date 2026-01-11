# Task List — MCP STDIO Webhook Server

This file lists compact, self-contained tasks to complete the plan in Planning.md. Each task includes: scope reminder, build steps, and the test that marks it complete. Use the checkboxes to track progress. Perform tasks independently; each task contains required context.

---

- [x] Task 001 — Repository scaffold
  - Scope reminder: Create repository layout and basic files so later implementation has a consistent structure.
  - Build steps:
    1. Create directories: `src/`, `config/`, `docker/`, `examples/`, `tests/`.
    2. Add `pyproject.toml`, `.gitignore`, `README.md` (placeholder), `.env.example`.
    3. Add `src/mcp_webhook/` package with `__init__.py`.
    4. Add `docker-compose.yml` stub and `Dockerfile` stub.
  - Test to mark complete:
    - All files and directories exist at project root.
    - `python -m pip check` (or simple `python -c "import importlib.util; print('ok')"` in a clean env) runs without referencing project code; CI step verifies files present.

---

- [x] Task 002 — Planning.md and Task.md committed
  - Scope reminder: Ensure planning artifacts are in repo root for traceability.
  - Build steps:
    1. Add `Planning.md` (already present) and this `Task.md` to repo root.
    2. Commit files with descriptive message.
  - Test to mark complete:
    - Files `Planning.md` and `Task.md` are present under project root and readable.

---

- [x] Task 010 — Implement config module
  - Scope reminder: Centralize configuration (env-driven) for PORT, tokens, mapping path, async toggle, log level.
  - Build steps:
    1. Add `src/mcp_webhook/config.py` using `pydantic.BaseSettings`.
    2. Define fields: `port`, `mcp_name`, `webhook_bearer_tokens`, `async_processing`, `mapping_file`, `log_level`.
    3. Provide `.env.example` with default values.
  - Test to mark complete:
    - Import `mcp_webhook.config` and instantiate settings in a shell; ensure values reflect `.env.example` when loaded.
    - Unit test asserts `WEBHOOK_BEARER_TOKENS` empty yields empty list.

---

- [x] Task 020 — Add mapping config parser
  - Scope reminder: Parse mapping YAML/JSON to resolve event -> tool and arg templates.
  - Build steps:
    1. Implement `src/mcp_webhook/mapping.py` that reads `MAPPING_FILE`.
    2. Support YAML format with entries `{event, tool, args}` and dot-path extraction.
    3. Provide `config/mapping.yml.example`.
  - Test to mark complete:
    - Unit tests: load example mapping and assert returned mapping objects and dot-path extraction function return expected values for sample payload.

---

- [x] Task 030 — Envelope Pydantic models and extraction utilities
  - Scope reminder: Validate incoming envelopes and extract args using dot-path syntax.
  - Build steps:
    1. Implement `src/mcp_webhook/envelope.py` with Pydantic models for `Envelope`, `Meta`.
    2. Provide `extract_value(payload, "payload.user.id")` utility and simple default/error handling.
  - Test to mark complete:
    - Unit tests: several valid/invalid envelopes validate/fail appropriately.
    - Extraction tests: dot-path resolves nested values and raises clear errors for missing required fields.

---

- [x] Task 040 — Implement MCP tools (ack_event, process_payload, admin list)
  - Scope reminder: Provide the core tool functions that mapping will call; structured outputs via Pydantic.
  - Build steps:
    1. Create `src/mcp_webhook/tools.py`.
    2. Implement `ack_event(event_type: str, payload: dict) -> dict`, `process_payload(path: str, user_id: str) -> dict`, and `list_recent_events()`.
    3. Register tools with FastMCP in server bootstrap (placeholder).
  - Test to mark complete:
    - Unit tests: call each tool directly and assert expected structured dict/Pydantic shape.
    - Tools importable without requiring running the server.

---

- [x] Task 050 — Implement Envelope Router (sync path)
  - Scope reminder: Route validated envelopes to an MCP tool invocation synchronously (no queue).
  - Build steps:
    1. Add `src/mcp_webhook/router.py`.
    2. Router resolves mapping, extracts args, validates auth token if configured, invokes tool function and returns result.
    3. Ensure clear error handling and structured error responses.
  - Test to mark complete:
    - Unit tests: given sample envelope and mapping, router calls correct tool and returns expected output.
    - Auth tests: token present -> success; invalid -> raises/returns auth error.

---

- [x] Task 060 — Implement in-process async worker (optional toggle)
  - Scope reminder: Support asynchronous processing when `ASYNC_PROCESSING=true`; in-process queue small worker pool.
  - Build steps:
    1. Add `src/mcp_webhook/worker.py` implementing a simple asyncio queue and worker coroutine(s).
    2. Router enqueues when async enabled; worker consumes and calls tools, logs results.
  - Test to mark complete:
    - Integration test: start worker loop, enqueue task, assert worker processed item and result stored in recent-events buffer.

---

- [x] Task 070 — Implement FastMCP STDIO server bootstrap
  - Scope reminder: Launch FastMCP server and register tools so server speaks MCP on STDIO.
  - Build steps:
    1. Create `src/mcp_webhook/server.py` which constructs `FastMCP` with name, registers `@mcp.tool()` wrappers around `tools.py` functions, and exposes an entrypoint `run_stdio_server()` that calls `mcp.run(transport="stdio")`.
    2. Ensure the server exposes an admin tool to query recent events.
  - Test to mark complete:
    - Unit/integration: start the server in-process in a test harness and verify that `ClientSession` can list prompts/tools (use SDK test client pattern or mock).

---

- [x] Task 080 — Implement stdio-proxy (TCP <-> STDIO bridge)
  - Scope reminder: Provide TCP endpoint for host clients; proxy forwards bytes to server stdin/stdout.
  - Build steps:
    1. Add `src/mcp_webhook/proxy.py` implementing an asyncio TCP server.
    2. The proxy spawns the server process as a subprocess with pipes (or connects to an in-process server) and forwards bytes bidirectionally.
    3. Provide graceful shutdown and logging.
  - Test to mark complete:
    - Integration test: spawn proxy+server and use a test TCP client to perform a minimal MCP stdio handshake (or send framed message) and receive a response.
    - Smoke test: connect via `nc` in CI-compatible test to ensure port open.

---

- [x] Task 090 — Entry point and Docker entrypoint script
  - Scope reminder: Tie startup: config load, start server subprocess and proxy; support env-driven behavior.
  - Build steps:
    1. Add `entrypoint.sh` (or `entrypoint.py`) to start proxy and spawn server subprocess; handle signals.
    2. Update Dockerfile to use entrypoint and expose configured port.
    3. Ensure logs are sent to stdout/stderr.
  - Test to mark complete:
    - Build Docker image locally; run container and assert the proxy port is listening and process is running.
    - Container exits cleanly on SIGTERM.

---

- [x] Task 100 — Dockerfile and docker-compose
  - Scope reminder: Produce a small image and a `docker-compose.yml` enabling 1-click run with example volume mounts.
  - Build steps:
    1. Implement `Dockerfile` using `python:3.11-slim`, install required dependencies via `pyproject.toml` or `requirements.txt`.
    2. Implement `docker-compose.yml` (compose v3.9) mapping `PORT` and mounting `config/`.
    3. Add `config/mapping.yml.example` and `.env.example`.
  - Test to mark complete:
    - `docker-compose up --build` runs without error and binds the proxy port on the host.
    - A smoke client connects and receives expected MCP response for a simple call (can be emulated test).

---

- [x] Task 110 — Logging, metrics stub, and recent events buffer
  - Scope reminder: Basic observability for debugging and tests.
  - Build steps:
    1. Implement structured JSON logging via `logging` config in `config.py`.
    2. Add an in-memory ring buffer to store the last N processed envelopes and results.
    3. Expose `list_recent_events` as an MCP tool.
  - Test to mark complete:
    - Unit test: push events and assert buffer stores N items and MCP tool returns them.
    - Logging configuration test: ensure log messages are JSON formatted.

---

- [x] Task 120 — Unit tests for all modules
  - Scope reminder: Provide tests for config, mapping, envelope parsing, extraction, tools, and router.
  - Build steps:
    1. Create `tests/unit/test_config.py`, `test_mapping.py`, `test_envelope.py`, `test_extraction.py`, `test_tools.py`, `test_router.py`.
    2. Configure `pytest.ini` and GitHub Actions stub for test run.
  - Test to mark complete:
    - `pytest` completes with all unit tests passing locally and in CI.

---

- [x] Task 130 — Integration tests (local TCP + stdio)
  - Scope reminder: Validate end-to-end behavior via proxy: client -> TCP -> proxy -> server -> tool -> response.
  - Build steps:
    1. Add `tests/integration/test_stdio_proxy.py` that starts container or in-process proxy+server and connects an asyncio TCP client.
    2. Use example mapping and envelope to assert correct tool invocation and response.
  - Test to mark complete:
    - Integration test passes in CI using `docker-compose` or in-process start.

---

- [x] Task 140 — CI workflow
  - Scope reminder: Automate lint, unit tests, build image, and integration smoke test.
  - Build steps:
    1. Add `.github/workflows/ci.yml` with jobs: setup, lint, test, build (optional), integration smoke.
    2. Ensure environment variables and secrets handled for CI.
  - Test to mark complete:
    - CI pipeline runs and passes for lint + unit tests on a PR.

---

- [x] Task 150 — Documentation & examples
  - Scope reminder: Provide README quickstart, example client, and mapping examples so users can run the system.
  - Build steps:
    1. Enhance `README.md` with quickstart steps: `docker-compose up --build`, sample envelope, and sample client command.
    2. Add `examples/stdio_client.py` demonstrating connection to `localhost:PORT` and MCP stdio framing.
  - Test to mark complete:
    - Follow README steps on a fresh machine/CI runner and verify smoke client can perform a sample call.

---

- [ ] Task 160 — Optional: Redis-backed queue profile
  - Scope reminder: Provide optional async queue for higher throughput; enabled via compose profile `async`.
  - Build steps:
    1. Add `docker-compose.yml` profile that includes `redis`.
    2. Implement queue integration in `worker.py` if enabled (use `aioredis` or simple `asyncio`-Redis pattern).
  - Test to mark complete:
    - Bring up compose with profile; enqueue tasks from client; worker consumes and processes jobs; assert results.
  - Follow-up actions:
    1. Mark task complete in Task.md.
    2. Create a summary of changes made during this task.
    3. Commit all changes to Git with descriptive commit message.
    4. Push to origin/main.
    5. Wait for user review before proceeding to next task.

---

- [ ] Task 170 — Final review and release notes
  - Scope reminder: Ensure project is consistent and ready for handoff.
  - Build steps:
    1. Run full test suite and fix issues.
    2. Add `RELEASE.md` describing how to build and publish image.
    3. Tag a repo release or create a release draft.
  - Test to mark complete:
    - All tests pass; release notes present and the image build steps documented.
  - Follow-up actions:
    1. Mark task complete in Task.md.
    2. Create a summary of changes made during this task.
    3. Commit all changes to Git with descriptive commit message.
    4. Push to origin/main.
    5. Wait for user review before proceeding to next task.

---

Notes
- Keep each task atomic and independent. Each task's tests must not require the full system unless explicitly stated (integration tasks are the exception).
- When writing code later, include docstrings and small usage examples to make review and testing quick.
