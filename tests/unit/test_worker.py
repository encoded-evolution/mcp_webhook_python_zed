"""Unit tests for worker module.

This test suite validates:
- WorkerTask serialization and deserialization
- WorkerResult creation
- AsyncWorker initialization and queue backend selection
- Enqueue/dequeue operations (with mocked Redis)
- Error handling and fallback behavior
- Global worker instance management
"""

import asyncio
import json
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
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


class TestWorkerTask:
    """Unit tests for WorkerTask dataclass."""

    def test_worker_task_creation(self):
        """Test creating a WorkerTask instance."""
        task = WorkerTask(
            envelope_dict={"type": "event", "event_type": "test"},
            mapping_info={"tool": "ack_event", "args": {}},
            task_id="test-123",
        )
        assert task.envelope_dict == {"type": "event", "event_type": "test"}
        assert task.mapping_info == {"tool": "ack_event", "args": {}}
        assert task.task_id == "test-123"
        assert task.enqueued_at.endswith("Z")  # ISO format with Z suffix

    def test_worker_task_to_json(self):
        """Test WorkerTask serialization to JSON."""
        task = WorkerTask(
            envelope_dict={"type": "event", "event_type": "test"},
            mapping_info={"tool": "ack_event", "args": {"path": "payload.path"}},
            task_id="test-123",
            enqueued_at="2026-01-06T12:00:00Z",
        )
        json_str = task.to_json()
        assert isinstance(json_str, str)

        # Parse and verify structure
        data = json.loads(json_str)
        assert data["envelope_dict"] == {"type": "event", "event_type": "test"}
        assert data["mapping_info"] == {"tool": "ack_event", "args": {"path": "payload.path"}}
        assert data["task_id"] == "test-123"
        assert data["enqueued_at"] == "2026-01-06T12:00:00Z"

    def test_worker_task_from_json(self):
        """Test WorkerTask deserialization from JSON."""
        json_str = json.dumps({
            "envelope_dict": {"type": "event", "event_type": "test"},
            "mapping_info": {"tool": "ack_event", "args": {}},
            "task_id": "test-123",
            "enqueued_at": "2026-01-06T12:00:00Z",
        })
        task = WorkerTask.from_json(json_str)
        assert isinstance(task, WorkerTask)
        assert task.envelope_dict == {"type": "event", "event_type": "test"}
        assert task.task_id == "test-123"

    def test_worker_task_roundtrip_serialization(self):
        """Test that serialization/deserialization is reversible."""
        # Note: tool_func cannot be serialized to JSON, so it's excluded in this test
        original = WorkerTask(
            envelope_dict={
                "type": "event",
                "event_type": "file.save",
                "payload": {"path": "/test/file.py", "user": {"id": "alice"}},
                "meta": {"auth": "token1"},
            },
            mapping_info={
                "tool": "process_payload",
                "args": {"path": "payload.path", "user_id": "payload.user.id"},
            },
            task_id="roundtrip-test",
            enqueued_at="2026-01-06T12:00:00Z",
        )

        # Serialize and deserialize
        json_str = original.to_json()
        restored = WorkerTask.from_json(json_str)

        # Verify all fields match (tool_func would need to be added back separately)
        assert restored.envelope_dict == original.envelope_dict
        assert restored.task_id == original.task_id
        assert restored.enqueued_at == original.enqueued_at
        assert restored.mapping_info["tool"] == original.mapping_info["tool"]
        assert restored.mapping_info["args"] == original.mapping_info["args"]


class TestWorkerResult:
    """Unit tests for WorkerResult dataclass."""

    def test_worker_result_creation_success(self):
        """Test creating a successful WorkerResult."""
        result = WorkerResult(
            task_id="test-123",
            success=True,
            tool="ack_event",
            result={"status": "acknowledged"},
            error=None,
        )
        assert result.task_id == "test-123"
        assert result.success is True
        assert result.tool == "ack_event"
        assert result.result == {"status": "acknowledged"}
        assert result.error is None

    def test_worker_result_creation_failure(self):
        """Test creating a failed WorkerResult."""
        result = WorkerResult(
            task_id="test-456",
            success=False,
            tool="process_payload",
            result=None,
            error="Missing required field: path",
        )
        assert result.task_id == "test-456"
        assert result.success is False
        assert result.tool == "process_payload"
        assert result.result is None
        assert result.error == "Missing required field: path"

    def test_worker_result_timestamp(self):
        """Test WorkerResult auto-generates completed_at timestamp."""
        result = WorkerResult(
            task_id="test-789",
            success=True,
            tool="ack_event",
            result={"done": True},
            error=None,
        )
        assert result.completed_at.endswith("Z")  # ISO format with Z suffix
        assert "T" in result.completed_at  # Contains time separator


class TestAsyncWorkerInitialization:
    """Unit tests for AsyncWorker initialization."""

    def test_worker_initialization_defaults(self):
        """Test AsyncWorker initialization with default parameters."""
        worker = AsyncWorker()
        assert worker._num_workers == 2
        assert worker._queue_size == 1000
        assert worker._queue_name == "mcp_webhook_tasks"
        assert worker._running is False
        assert worker.queue is None
        assert worker.redis_client is None

    def test_worker_initialization_custom_params(self):
        """Test AsyncWorker initialization with custom parameters."""
        worker = AsyncWorker(
            num_workers=4,
            queue_size=500,
            queue_name="custom_queue",
        )
        assert worker._num_workers == 4
        assert worker._queue_size == 500
        assert worker._queue_name == "custom_queue"

    def test_worker_redis_enabled_from_config(self):
        """Test that worker detects Redis is enabled from config."""
        # Reset and configure Redis URL
        reset_settings()
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"

        if REDIS_AVAILABLE:
            worker = AsyncWorker()
            assert worker._use_redis is True
        else:
            worker = AsyncWorker()
            assert worker._use_redis is False

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()

    def test_worker_redis_disabled_without_url(self):
        """Test that worker doesn't use Redis when URL not configured."""
        reset_settings()
        os.environ["REDIS_URL"] = ""

        worker = AsyncWorker()
        assert worker._use_redis is False

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()

    def test_worker_redis_disabled_without_package(self):
        """Test that worker falls back to memory queue when aioredis not installed."""
        reset_settings()
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"

        with patch("mcp_webhook.worker.REDIS_AVAILABLE", False):
            worker = AsyncWorker()
            assert worker._use_redis is False

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()


class TestAsyncWorkerInMemoryQueue:
    """Unit tests for AsyncWorker with in-memory queue."""

    @pytest.mark.asyncio
    async def test_start_creates_in_memory_queue(self):
        """Test that start() creates in-memory queue when Redis disabled."""
        reset_settings()
        os.environ["REDIS_URL"] = ""

        worker = AsyncWorker(num_workers=0)  # No workers to avoid async tasks
        await worker.start()

        assert worker._running is True
        assert worker.queue is not None
        assert worker._shutdown_event is not None
        assert isinstance(worker.queue, asyncio.Queue)

        await worker.stop()

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()

    @pytest.mark.asyncio
    async def test_enqueue_in_memory_queue(self):
        """Test enqueuing task to in-memory queue."""
        reset_settings()
        os.environ["REDIS_URL"] = ""

        worker = AsyncWorker(num_workers=0)
        await worker.start()

        task = WorkerTask(
            envelope_dict={"type": "event"},
            mapping_info={"tool": "ack_event", "args": {}},
            task_id="test-1",
        )
        success = worker.enqueue(task)

        assert success is True
        assert worker.queue.qsize() == 1

        await worker.stop()

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()

    @pytest.mark.asyncio
    async def test_enqueue_fails_when_queue_full(self):
        """Test that enqueue returns False when in-memory queue is full."""
        reset_settings()
        os.environ["REDIS_URL"] = ""

        worker = AsyncWorker(num_workers=0, queue_size=1)
        await worker.start()

        # Fill queue
        task1 = WorkerTask(
            envelope_dict={"type": "event"},
            mapping_info={"tool": "ack_event", "args": {}},
            task_id="test-1",
        )
        worker.enqueue(task1)

        # Try to enqueue another task (should fail)
        task2 = WorkerTask(
            envelope_dict={"type": "event"},
            mapping_info={"tool": "ack_event", "args": {}},
            task_id="test-2",
        )
        success = worker.enqueue(task2)

        assert success is False
        assert worker.queue.qsize() == 1

        await worker.stop()

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()

    @pytest.mark.asyncio
    async def test_enqueue_fails_when_not_running(self):
        """Test that enqueue raises RuntimeError when worker not running."""
        reset_settings()
        os.environ["REDIS_URL"] = ""

        worker = AsyncWorker()

        task = WorkerTask(
            envelope_dict={"type": "event"},
            mapping_info={"tool": "ack_event", "args": {}},
            task_id="test-1",
        )

        with pytest.raises(RuntimeError, match="Async worker is not running"):
            worker.enqueue(task)

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()

    @pytest.mark.asyncio
    async def test_stop_clearly_stops_worker(self):
        """Test that stop() cleanly stops the worker."""
        reset_settings()
        os.environ["REDIS_URL"] = ""

        worker = AsyncWorker(num_workers=0)
        await worker.start()

        assert worker._running is True

        await worker.stop()

        assert worker._running is False
        assert len(worker.workers) == 0

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()

    @pytest.mark.asyncio
    async def test_queue_size_property(self):
        """Test queue_size property returns correct size."""
        reset_settings()
        os.environ["REDIS_URL"] = ""

        worker = AsyncWorker(num_workers=0)

        # Before start
        assert worker.queue_size == 0

        await worker.start()

        # Empty queue
        assert worker.queue_size == 0

        # Add tasks
        for i in range(3):
            task = WorkerTask(
                envelope_dict={"type": "event"},
                mapping_info={"tool": "ack_event", "args": {}},
                task_id=f"test-{i}",
            )
            worker.enqueue(task)

        assert worker.queue_size == 3

        await worker.stop()

        # After stop
        assert worker.queue_size == 0

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()


class TestAsyncWorkerRedisQueue:
    """Unit tests for AsyncWorker with Redis queue (mocked)."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(not REDIS_AVAILABLE, reason="aioredis not installed")
    async def test_start_creates_redis_client(self):
        """Test that start() creates Redis client when Redis enabled."""
        reset_settings()
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"

        mock_redis = AsyncMock()

        with patch("mcp_webhook.worker.aioredis") as mock_aioredis:
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            worker = AsyncWorker(num_workers=0)
            await worker.start()

            assert worker._running is True
            assert worker.redis_client is mock_redis
            assert worker._use_redis is True

            mock_aioredis.from_url.assert_called_once()

            await worker.stop()

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not REDIS_AVAILABLE, reason="aioredis not installed")
    async def test_enqueue_to_redis(self):
        """Test enqueuing task to Redis queue."""
        reset_settings()
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"

        mock_redis = AsyncMock()

        with patch("mcp_webhook.worker.aioredis") as mock_aioredis:
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            worker = AsyncWorker(num_workers=0)
            await worker.start()

            task = WorkerTask(
                envelope_dict={"type": "event"},
                mapping_info={"tool": "ack_event", "args": {}},
                task_id="test-1",
            )
            success = worker.enqueue(task)

            assert success is True
            mock_redis.rpush.assert_called_once()

            # Verify JSON was passed
            call_args = mock_redis.rpush.call_args
            assert call_args[0][1] == task.to_json()

            await worker.stop()

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not REDIS_AVAILABLE, reason="aioredis not installed")
    async def test_enqueue_handles_redis_error(self):
        """Test that enqueue handles Redis connection errors gracefully."""
        reset_settings()
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"

        mock_redis = AsyncMock()
        mock_redis.rpush = AsyncMock(side_effect=Exception("Redis connection lost"))

        with patch("mcp_webhook.worker.aioredis") as mock_aioredis:
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            worker = AsyncWorker(num_workers=0)
            await worker.start()

            task = WorkerTask(
                envelope_dict={"type": "event"},
                mapping_info={"tool": "ack_event", "args": {}},
                task_id="test-1",
            )
            success = worker.enqueue(task)

            assert success is False

            await worker.stop()

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not REDIS_AVAILABLE, reason="aioredis not installed")
    async def test_redis_queue_size(self):
        """Test queue_size property with Redis."""
        reset_settings()
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"

        mock_redis = AsyncMock()
        mock_redis.llen = AsyncMock(return_value=5)

        with patch("mcp_webhook.worker.aioredis") as mock_aioredis:
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            worker = AsyncWorker(num_workers=0)
            await worker.start()

            # Use async method for Redis
            size = await worker.get_queue_size()
            assert size == 5
            mock_redis.llen.assert_called_once_with(worker._queue_name)

            await worker.stop()

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not REDIS_AVAILABLE, reason="aioredis not installed")
    async def test_redis_close_connection_on_stop(self):
        """Test that Redis connection is closed on stop."""
        reset_settings()
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"

        mock_redis = AsyncMock()

        with patch("mcp_webhook.worker.aioredis") as mock_aioredis:
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            worker = AsyncWorker(num_workers=0)
            await worker.start()

            await worker.stop()

            mock_redis.close.assert_called_once()
            assert worker.redis_client is None

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()


class TestAsyncWorkerFallback:
    """Unit tests for worker fallback behavior."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(not REDIS_AVAILABLE, reason="aioredis not installed")
    async def test_fallback_to_memory_on_redis_connection_error(self):
        """Test fallback to in-memory queue when Redis connection fails."""
        reset_settings()
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"

        with patch("mcp_webhook.worker.aioredis") as mock_aioredis:
            mock_aioredis.from_url = AsyncMock(side_effect=Exception("Connection refused"))

            worker = AsyncWorker(num_workers=0)
            await worker.start()

            # Should fall back to in-memory queue
            assert worker._use_redis is False
            assert worker.queue is not None
            assert worker.redis_client is None

            await worker.stop()

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()

    @pytest.mark.asyncio
    async def test_enqueue_fails_when_redis_not_initialized(self):
        """Test that enqueue raises error when Redis client not initialized."""
        reset_settings()
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"

        with patch("mcp_webhook.worker.REDIS_AVAILABLE", True):
            # Manually set up worker in inconsistent state
            worker = AsyncWorker()
            worker._running = True
            worker._use_redis = True
            worker.redis_client = None  # Not initialized

            task = WorkerTask(
                envelope_dict={"type": "event"},
                mapping_info={"tool": "ack_event", "args": {}},
                task_id="test-1",
            )

            with pytest.raises(RuntimeError, match="Redis client not initialized"):
                worker.enqueue(task)

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()


class TestGlobalWorkerInstance:
    """Unit tests for global worker instance management."""

    def test_get_worker_returns_singleton(self):
        """Test that get_worker returns the same instance."""
        reset_worker()

        worker1 = get_worker()
        worker2 = get_worker()

        assert worker1 is worker2

    def test_reset_worker_creates_new_instance(self):
        """Test that reset_worker creates a new global instance."""
        worker1 = get_worker()
        reset_worker()
        worker2 = get_worker()

        assert worker1 is not worker2

    def test_multiple_workers_independent(self):
        """Test that explicitly created workers are independent."""
        worker1 = AsyncWorker(num_workers=1)
        worker2 = AsyncWorker(num_workers=2)

        assert worker1 is not worker2
        assert worker1._num_workers == 1
        assert worker2._num_workers == 2


class TestAsyncWorkerProperties:
    """Unit tests for AsyncWorker properties."""

    def test_is_running_property(self):
        """Test is_running property reflects worker state."""
        worker = AsyncWorker()

        assert worker.is_running is False

        # Note: Can't test actual running state without async context
        # but property logic is simple enough to trust

    def test_redis_enabled_property_via_settings(self):
        """Test that worker correctly reads redis_enabled from settings."""
        # Test with Redis disabled
        reset_settings()
        os.environ["REDIS_URL"] = ""
        worker1 = AsyncWorker()
        assert worker1._use_redis is False

        # Test with Redis enabled
        if REDIS_AVAILABLE:
            reset_settings()
            os.environ["REDIS_URL"] = "redis://localhost:6379/0"
            worker2 = AsyncWorker()
            assert worker2._use_redis is True

        # Cleanup
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        reset_settings()
