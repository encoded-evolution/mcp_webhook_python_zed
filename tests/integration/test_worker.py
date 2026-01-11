"""Integration tests for async worker module."""

import asyncio
import pytest
from typing import Dict, Any

from mcp_webhook.worker import AsyncWorker, WorkerTask, get_worker, reset_worker
from mcp_webhook.config import get_settings, reset_settings
from mcp_webhook.tools import clear_recent_events, list_recent_events


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before and after each test."""
    # Reset before test
    reset_settings()
    reset_worker()
    clear_recent_events()

    yield

    # Reset after test
    reset_settings()
    reset_worker()
    clear_recent_events()


@pytest.mark.asyncio
async def test_worker_starts_and_stops():
    """Test that worker can start and stop cleanly."""
    worker = AsyncWorker(num_workers=1, queue_size=10)

    # Initially not running
    assert not worker.is_running

    # Start worker
    await worker.start()
    assert worker.is_running
    assert len(worker.workers) == 1

    # Stop worker
    await worker.stop()
    assert not worker.is_running


@pytest.mark.asyncio
async def test_worker_processes_single_task():
    """Test that worker processes a single task correctly."""
    worker = AsyncWorker(num_workers=1, queue_size=10)

    # Start worker
    await worker.start()

    try:
        # Create a simple task
        task = WorkerTask(
            envelope_dict={
                "event_type": "test.event",
                "payload": {"key": "value"},
                "type": "event",
            },
            mapping_info={
                "tool": "ack_event",
                "tool_func": lambda event_type, payload: {
                    "success": True,
                    "event_type": event_type,
                    "message": f"Processed: {event_type}"
                },
                "args": {
                    "event_type": "event_type",
                    "payload": "payload",
                }
            },
            task_id="test-001",
        )

        # Enqueue task
        enqueued = worker.enqueue(task)
        assert enqueued is True

        # Wait for task to be processed
        await asyncio.sleep(0.5)

        # Verify queue is empty
        assert worker.queue_size == 0

    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_worker_multiple_tasks_sequential():
    """Test that worker processes multiple tasks sequentially."""
    worker = AsyncWorker(num_workers=1, queue_size=10)

    # Start worker
    await worker.start()

    try:
        # Enqueue multiple tasks
        for i in range(5):
            task = WorkerTask(
                envelope_dict={
                    "event_type": f"test.event.{i}",
                    "payload": {"index": i},
                    "type": "event",
                },
                mapping_info={
                    "tool": "ack_event",
                    "tool_func": lambda event_type, payload: {
                        "success": True,
                        "event_type": event_type,
                        "payload": payload
                    },
                    "args": {
                        "event_type": "event_type",
                        "payload": "payload",
                    }
                },
                task_id=f"test-{i:03d}",
            )

            enqueued = worker.enqueue(task)
            assert enqueued is True

        # Wait for all tasks to be processed
        await asyncio.sleep(1.0)

        # Verify queue is empty
        assert worker.queue_size == 0

    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_worker_multiple_workers_parallel():
    """Test that multiple workers can process tasks in parallel."""
    worker = AsyncWorker(num_workers=3, queue_size=10)

    # Start worker
    await worker.start()

    try:
        # Enqueue more tasks than workers
        tasks_enqueued = []
        for i in range(6):
            task = WorkerTask(
                envelope_dict={
                    "event_type": f"test.parallel.{i}",
                    "payload": {"index": i},
                    "type": "event",
                },
                mapping_info={
                    "tool": "ack_event",
                    "tool_func": lambda event_type, payload: {
                        "success": True,
                        "event_type": event_type,
                    },
                    "args": {
                        "event_type": "event_type",
                        "payload": "payload",
                    }
                },
                task_id=f"parallel-{i:03d}",
            )

            enqueued = worker.enqueue(task)
            assert enqueued is True
            tasks_enqueued.append(task.task_id)

        # Wait for all tasks to be processed
        await asyncio.sleep(1.0)

        # Verify queue is empty
        assert worker.queue_size == 0

    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_worker_queue_full():
    """Test that enqueue returns False when queue is full."""
    worker = AsyncWorker(num_workers=1, queue_size=2)

    # Start worker
    await worker.start()

    try:
        # Fill the queue
        for i in range(2):
            task = WorkerTask(
                envelope_dict={
                    "event_type": f"test.full.{i}",
                    "payload": {},
                    "type": "event",
                },
                mapping_info={
                    "tool": "ack_event",
                    "tool_func": lambda event_type, payload: {},
                    "args": {},
                },
                task_id=f"full-{i:03d}",
            )

            enqueued = worker.enqueue(task)
            assert enqueued is True

        # Try to enqueue one more task (should fail)
        task = WorkerTask(
            envelope_dict={
                "event_type": "test.full.overflow",
                "payload": {},
                "type": "event",
            },
            mapping_info={
                "tool": "ack_event",
                "tool_func": lambda event_type, payload: {},
                "args": {},
            },
            task_id="overflow",
        )

        enqueued = worker.enqueue(task)
        assert enqueued is False

    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_worker_graceful_shutdown():
    """Test that worker gracefully shuts down with tasks in queue."""
    worker = AsyncWorker(num_workers=1, queue_size=10)

    # Start worker
    await worker.start()

    # Enqueue tasks
    for i in range(3):
        task = WorkerTask(
            envelope_dict={
                "event_type": f"test.shutdown.{i}",
                "payload": {},
                "type": "event",
            },
            mapping_info={
                "tool": "ack_event",
                "tool_func": lambda event_type, payload: {},
                "args": {},
            },
            task_id=f"shutdown-{i:03d}",
        )

        worker.enqueue(task)

    # Stop worker with timeout
    await worker.stop(timeout=5.0)

    # Verify worker is stopped
    assert not worker.is_running


@pytest.mark.asyncio
async def test_worker_with_real_tools():
    """Test worker with actual tool functions and buffer storage."""
    from mcp_webhook.envelope import Envelope
    from mcp_webhook.tools import process_payload

    # Clear buffer
    clear_recent_events()

    # Start worker
    worker = AsyncWorker(num_workers=1, queue_size=10)
    await worker.start()

    try:
        # Create mock mapping info for process_payload tool
        mapping_info = {
            "tool": "process_payload",
            "tool_func": process_payload,
            "args": {
                "path": "path",
                "user_id": "user.id",
            }
        }

        # Create envelope
        envelope = Envelope(
            event_type="file.save",
            payload={
                "path": "/test/file.py",
                "user": {"id": "test_user"},
            },
            type="event",
        )

        # Create task
        task = WorkerTask(
            envelope_dict=envelope.model_dump(),
            mapping_info=mapping_info,
            task_id="real-tool-001",
        )

        # Enqueue task
        worker.enqueue(task)

        # Wait for processing
        await asyncio.sleep(0.5)

        # Check recent events buffer
        response = list_recent_events()
        assert response.count > 0

        # Find our event
        found = False
        for event in response.events:
            if event.event_type == "file.save":
                found = True
                # Verify result structure
                assert "success" in event.result
                assert event.result["success"] is True
                assert "path" in event.result
                break

        assert found, "Event not found in recent events buffer"

    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_global_worker_instance():
    """Test that global worker instance works correctly."""
    worker = get_worker()

    assert not worker.is_running

    await worker.start()
    assert worker.is_running

    await worker.stop()
    assert not worker.is_running


@pytest.mark.asyncio
async def test_worker_error_handling():
    """Test that worker handles errors gracefully without crashing."""
    worker = AsyncWorker(num_workers=1, queue_size=10)

    # Start worker
    await worker.start()

    try:
        # Create a task that will fail
        task = WorkerTask(
            envelope_dict={
                "event_type": "test.error",
                "payload": {},  # Missing required fields
                "type": "event",
            },
            mapping_info={
                "tool": "process_payload",
                "tool_func": lambda path, user_id: {},
                "args": {
                    "path": "payload.missing_field",  # Will fail extraction
                    "user_id": "payload.another_missing",
                }
            },
            task_id="error-task",
        )

        # Enqueue task (should succeed)
        enqueued = worker.enqueue(task)
        assert enqueued is True

        # Wait for processing
        await asyncio.sleep(0.5)

        # Verify queue is empty (error was handled)
        assert worker.queue_size == 0

        # Worker should still be running
        assert worker.is_running

    finally:
        await worker.stop()
