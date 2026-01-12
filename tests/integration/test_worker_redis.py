"""Integration tests for Redis-backed async worker.

This test suite validates the Redis queue functionality, including:
- Redis connection and queue operations
- Task enqueuing and dequeuing
- Worker processing with Redis backend
- Error handling and fallback behavior
- Graceful shutdown with Redis

Requires a running Redis server. Tests can be skipped if Redis is unavailable.
"""

import asyncio
import json
import os
import pytest

from mcp_webhook.worker import (
    WorkerTask,
    WorkerResult,
    AsyncWorker,
    get_worker,
    reset_worker,
    REDIS_AVAILABLE,
)
from mcp_webhook.config import get_settings, reset_settings

# Test Redis configuration - can be overridden via environment
REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL", "redis://localhost:6379/1")
REDIS_TEST_QUEUE = "test_mcp_webhook_tasks"


@pytest.mark.integration
@pytest.mark.skipif(not REDIS_AVAILABLE, reason="aioredis not installed")
@pytest.mark.skipif(
    os.environ.get("SKIP_REDIS_TESTS"),
    reason="SKIP_REDIS_TESTS environment variable is set"
)
class TestRedisWorkerIntegration:
    """Integration tests for Redis-backed async worker."""

    @pytest.fixture(autouse=True)
    async def setup_teardown(self):
        """Setup and teardown for each test."""
        # Reset global instances
        reset_worker()
        reset_settings()

        # Clear test queue before each test
        if REDIS_AVAILABLE:
            import aioredis
            redis = await aioredis.from_url(REDIS_TEST_URL)
            await redis.delete(REDIS_TEST_QUEUE)
            await redis.close()

        # Configure settings to use Redis
        os.environ["REDIS_URL"] = REDIS_TEST_URL

        yield

        # Cleanup: clear queue and reset
        if REDIS_AVAILABLE:
            import aioredis
            redis = await aioredis.from_url(REDIS_TEST_URL)
            await redis.delete(REDIS_TEST_QUEUE)
            await redis.close()
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_worker()
        reset_settings()

    @pytest.mark.asyncio
    async def test_redis_connection_and_queue_size(self):
        """Test that worker can connect to Redis and report queue size."""
        import aioredis

        worker = AsyncWorker(num_workers=1, queue_name=REDIS_TEST_QUEUE)
        await worker.start()

        # Verify Redis connection
        assert worker.redis_client is not None
        assert worker._use_redis is True

        # Initial queue size should be 0
        size = await worker.queue_size
        assert size == 0

        # Enqueue a task
        task = WorkerTask(
            envelope_dict={"type": "event", "event_type": "test"},
            mapping_info={"tool": "ack_event", "args": {}},
            task_id="test-task-1",
        )
        worker.enqueue(task)

        # Verify queue size increased
        size = await worker.queue_size
        assert size == 1

        await worker.stop()

    @pytest.mark.asyncio
    async def test_enqueue_and_process_task_with_redis(self):
        """Test enqueuing a task and having worker process it from Redis."""
        worker = AsyncWorker(num_workers=1, queue_name=REDIS_TEST_QUEUE)
        await worker.start()

        # Enqueue a simple task
        task = WorkerTask(
            envelope_dict={
                "type": "event",
                "event_type": "file.save",
                "payload": {"path": "/test/file.py"},
                "meta": {},
            },
            mapping_info={
                "tool": "ack_event",
                "tool_func": lambda **kwargs: {"status": "acknowledged", **kwargs},
                "args": {"event_type": "envelope.event_type"},
            },
            task_id="test-task-2",
        )
        success = worker.enqueue(task)
        assert success is True

        # Wait for worker to process the task
        await asyncio.sleep(0.5)

        # Verify queue is now empty
        size = await worker.queue_size
        assert size == 0

        await worker.stop()

    @pytest.mark.asyncio
    async def test_multiple_tasks_with_redis(self):
        """Test processing multiple tasks from Redis queue."""
        worker = AsyncWorker(num_workers=2, queue_name=REDIS_TEST_QUEUE)
        await worker.start()

        # Enqueue multiple tasks
        num_tasks = 5
        for i in range(num_tasks):
            task = WorkerTask(
                envelope_dict={
                    "type": "event",
                    "event_type": "test",
                    "payload": {"index": i},
                    "meta": {},
                },
                mapping_info={
                    "tool": "ack_event",
                    "tool_func": lambda **kwargs: {"processed": True, **kwargs},
                    "args": {},
                },
                task_id=f"test-task-{i}",
            )
            worker.enqueue(task)

        # Verify all tasks are in queue
        size = await worker.queue_size
        assert size == num_tasks

        # Wait for workers to process all tasks
        await asyncio.sleep(2.0)

        # Verify queue is empty
        size = await worker.queue_size
        assert size == 0

        await worker.stop()

    @pytest.mark.asyncio
    async def test_task_serialization(self):
        """Test WorkerTask serialization/deserialization for Redis."""
        original_task = WorkerTask(
            envelope_dict={"type": "event", "event_type": "test", "payload": {"key": "value"}},
            mapping_info={"tool": "process_payload", "args": {"path": "payload.key"}},
            task_id="serialization-test",
            enqueued_at="2026-01-06T12:00:00Z",
        )

        # Serialize
        json_str = original_task.to_json()
        assert isinstance(json_str, str)

        # Deserialize
        restored_task = WorkerTask.from_json(json_str)

        # Verify all fields match
        assert restored_task.task_id == original_task.task_id
        assert restored_task.envelope_dict == original_task.envelope_dict
        assert restored_task.mapping_info == original_task.mapping_info
        assert restored_task.enqueued_at == original_task.enqueued_at

    @pytest.mark.asyncio
    async def test_worker_fallback_to_memory_queue_on_redis_error(self):
        """Test that worker falls back to in-memory queue when Redis is unavailable."""
        # Configure with invalid Redis URL
        os.environ["REDIS_URL"] = "redis://invalid-host:9999/0"
        reset_settings()

        worker = AsyncWorker(num_workers=1, queue_name=REDIS_TEST_QUEUE)
        await worker.start()

        # Should fall back to in-memory queue
        assert worker._use_redis is False
        assert worker.queue is not None
        assert worker.redis_client is None

        # Enqueue should still work
        task = WorkerTask(
            envelope_dict={"type": "event"},
            mapping_info={"tool": "ack_event", "args": {}},
            task_id="fallback-test",
        )
        success = worker.enqueue(task)
        assert success is True

        # Should use in-memory queue
        assert worker.queue.qsize() == 1

        await worker.stop()

    @pytest.mark.asyncio
    async def test_graceful_shutdown_with_redis(self):
        """Test graceful shutdown while tasks are in Redis queue."""
        worker = AsyncWorker(num_workers=1, queue_name=REDIS_TEST_QUEUE)
        await worker.start()

        # Enqueue a task
        task = WorkerTask(
            envelope_dict={"type": "event", "event_type": "test"},
            mapping_info={
                "tool": "ack_event",
                "tool_func": lambda **kwargs: asyncio.sleep(0.5) or {"done": True},
                "args": {},
            },
            task_id="shutdown-test",
        )
        worker.enqueue(task)

        # Give worker time to pick up task
        await asyncio.sleep(0.1)

        # Stop worker (should wait for task to complete)
        await worker.stop()

        # Verify worker stopped cleanly
        assert worker._running is False
        assert worker.redis_client is None

    @pytest.mark.asyncio
    async def test_redis_queue_persistence(self):
        """Test that tasks persist in Redis queue across worker restarts."""
        import aioredis

        # First worker instance
        worker1 = AsyncWorker(num_workers=0, queue_name=REDIS_TEST_QUEUE)
        await worker1.start()

        # Enqueue tasks without workers
        task1 = WorkerTask(
            envelope_dict={"type": "event", "event_type": "test1"},
            mapping_info={"tool": "ack_event", "args": {}},
            task_id="persist-1",
        )
        task2 = WorkerTask(
            envelope_dict={"type": "event", "event_type": "test2"},
            mapping_info={"tool": "ack_event", "args": {}},
            task_id="persist-2",
        )
        worker1.enqueue(task1)
        worker1.enqueue(task2)

        # Verify tasks are in Redis
        size = await worker1.queue_size
        assert size == 2

        # Stop first worker
        await worker1.stop()

        # Start second worker instance (tasks should still be in Redis)
        worker2 = AsyncWorker(num_workers=1, queue_name=REDIS_TEST_QUEUE)
        await worker2.start()

        # Tasks should still be there
        size = await worker2.queue_size
        assert size == 2

        # Process tasks
        await asyncio.sleep(1.0)
        size = await worker2.queue_size
        assert size == 0

        await worker2.stop()

    @pytest.mark.asyncio
    async def test_concurrent_workers_with_redis(self):
        """Test multiple workers sharing a Redis queue."""
        num_workers = 3
        num_tasks = 10

        worker = AsyncWorker(num_workers=num_workers, queue_name=REDIS_TEST_QUEUE)
        await worker.start()

        # Enqueue tasks
        for i in range(num_tasks):
            task = WorkerTask(
                envelope_dict={
                    "type": "event",
                    "event_type": "concurrent",
                    "payload": {"task": i},
                    "meta": {},
                },
                mapping_info={
                    "tool": "ack_event",
                    "tool_func": lambda **kwargs: asyncio.sleep(0.1) or {"processed": True},
                    "args": {},
                },
                task_id=f"concurrent-{i}",
            )
            worker.enqueue(task)

        # Verify all tasks enqueued
        size = await worker.queue_size
        assert size == num_tasks

        # Wait for processing
        await asyncio.sleep(2.0)

        # Verify all tasks processed
        size = await worker.queue_size
        assert size == 0

        await worker.stop()


@pytest.mark.integration
class TestRedisWorkerWithoutRedis:
    """Tests for worker behavior when Redis is not available."""

    @pytest.fixture(autouse=True)
    async def setup_teardown(self):
        """Setup and teardown."""
        reset_worker()
        reset_settings()
        yield
        reset_worker()
        reset_settings()

    @pytest.mark.asyncio
    async def test_worker_defaults_to_memory_queue_without_redis_url(self):
        """Test worker uses in-memory queue when REDIS_URL is not configured."""
        os.environ["REDIS_URL"] = ""
        reset_settings()

        worker = AsyncWorker(num_workers=1, queue_name=REDIS_TEST_QUEUE)
        await worker.start()

        # Should use in-memory queue
        assert worker._use_redis is False
        assert worker.queue is not None
        assert worker.redis_client is None

        # Enqueue should work
        task = WorkerTask(
            envelope_dict={"type": "event"},
            mapping_info={"tool": "ack_event", "args": {}},
            task_id="no-redis-test",
        )
        success = worker.enqueue(task)
        assert success is True

        await worker.stop()
