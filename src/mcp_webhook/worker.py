"""Async worker for processing envelope events in background.

This module provides an in-process async worker that processes event
envelopes from a queue when async processing is enabled. The worker
maintains compatibility with synchronous routing by storing results
in the same recent events buffer.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field

from mcp_webhook.config import get_settings

logger = logging.getLogger(__name__)


@dataclass()
class WorkerTask:
    """Represents a task to be processed by the async worker.

    Attributes:
        envelope_dict: The envelope data as a dictionary
        mapping_info: Dictionary containing tool info and args
        task_id: Unique identifier for this task
        enqueued_at: Timestamp when task was enqueued
    """

    envelope_dict: Dict[str, Any]
    mapping_info: Dict[str, Any]
    task_id: str
    enqueued_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    __hash__ = object.__hash__


@dataclass()
class WorkerResult:
    """Represents the result of processing a worker task.

    Attributes:
        task_id: The task identifier
        success: Whether the task completed successfully
        tool: The name of the tool that was invoked
        result: The result returned by the tool
        error: Error message if processing failed
        completed_at: Timestamp when task completed
    """

    task_id: str
    success: bool
    tool: Optional[str]
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    completed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    __hash__ = object.__hash__


class AsyncWorker:
    """In-process async worker for background task processing.

    The worker manages an asyncio queue and one or more worker coroutines
    that process tasks asynchronously. Results are stored in the recent
    events buffer for observability.

    Attributes:
        settings: Application settings
        queue: asyncio.Queue for pending tasks
        workers: List of worker tasks
        _running: Flag indicating if worker is running
        _shutdown_event: Event for graceful shutdown
    """

    def __init__(
        self,
        num_workers: int = 2,
        queue_size: int = 1000,
    ):
        """Initialize the async worker.

        Args:
            num_workers: Number of worker coroutines to spawn (default: 2)
            queue_size: Maximum size of the task queue (default: 1000)
        """
        self.settings = get_settings()
        self._num_workers = num_workers
        self._queue_size = queue_size
        self.queue: Optional[asyncio.Queue[WorkerTask]] = None
        self.workers: List[asyncio.Task] = []
        self._running = False
        self._shutdown_event: Optional[asyncio.Event] = None

    async def start(self) -> None:
        """Start the async worker and worker coroutines.

        Creates the queue, shutdown event, and spawns worker tasks.
        This should be called before any enqueue operations.
        """
        if self._running:
            logger.warning("Async worker is already running")
            return

        self.queue = asyncio.Queue(maxsize=self._queue_size)
        self._shutdown_event = asyncio.Event()
        self._running = True

        # Spawn worker coroutines
        for i in range(self._num_workers):
            worker_task = asyncio.create_task(
                self._worker_loop(i),
                name=f"async-worker-{i}",
            )
            self.workers.append(worker_task)

        logger.info(
            f"Async worker started with {self._num_workers} workers "
            f"(queue size: {self._queue_size})"
        )

    async def stop(self, timeout: float = 30.0) -> None:
        """Stop the async worker gracefully.

        Signals workers to stop and waits for them to finish processing
        remaining tasks within the timeout period.

        Args:
            timeout: Maximum time to wait for workers to finish (seconds)
        """
        if not self._running:
            return

        logger.info("Stopping async worker...")

        # Signal workers to stop
        if self._shutdown_event:
            self._shutdown_event.set()

        # Wait for workers to finish with timeout
        if self.workers:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.workers, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Async worker shutdown timed out after {timeout}s, "
                    f"cancelling {len(self.workers)} workers"
                )
                for worker in self.workers:
                    if not worker.done():
                        worker.cancel()

        self._running = False
        self.workers.clear()
        logger.info("Async worker stopped")

    def enqueue(self, task: WorkerTask) -> bool:
        """Enqueue a task for processing.

        Args:
            task: The WorkerTask to enqueue

        Returns:
            True if task was enqueued, False if queue is full

        Raises:
            RuntimeError: If worker is not running
        """
        if not self._running or self.queue is None:
            raise RuntimeError("Async worker is not running")

        try:
            # Use put_nowait to avoid blocking if queue is full
            self.queue.put_nowait(task)
            logger.debug(
                f"Enqueued task {task.task_id} (queue size: {self.queue.qsize()})"
            )
            return True
        except asyncio.QueueFull:
            logger.warning(f"Task queue full, cannot enqueue task {task.task_id}")
            return False

    async def _worker_loop(self, worker_id: int) -> None:
        """Worker coroutine that processes tasks from the queue.

        Args:
            worker_id: Identifier for this worker
        """
        if self.queue is None or self._shutdown_event is None:
            logger.error(f"Worker {worker_id}: queue or shutdown_event not initialized")
            return

        logger.debug(f"Worker {worker_id} started")

        while not self._shutdown_event.is_set():
            try:
                # Wait for task with timeout to allow shutdown check
                try:
                    task = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                # Process the task
                logger.debug(f"Worker {worker_id} processing task {task.task_id}")
                result = await self._process_task(task)

                # Log result
                if result.success:
                    logger.info(
                        f"Worker {worker_id} completed task {task.task_id} "
                        f"with tool {result.tool}"
                    )
                else:
                    logger.warning(
                        f"Worker {worker_id} failed task {task.task_id}: {result.error}"
                    )

                # Mark task as done
                self.queue.task_done()

            except Exception as e:
                logger.error(
                    f"Worker {worker_id} error processing task: {e}",
                    exc_info=True,
                )

        logger.debug(f"Worker {worker_id} stopped")

    async def _process_task(self, task: WorkerTask) -> WorkerResult:
        """Process a single task.

        Args:
            task: The WorkerTask to process

        Returns:
            WorkerResult with processing outcome
        """
        try:
            # Import here to avoid circular dependency
            from mcp_webhook.envelope import Envelope
            from mcp_webhook.router import invoke_tool
            from mcp_webhook.tools import _store_recent_event

            # Validate envelope
            envelope = Envelope(**task.envelope_dict)

            # Extract tool and args from mapping info
            tool_func = task.mapping_info["tool_func"]
            args_mapping = task.mapping_info["args"]

            # Extract args from envelope
            from mcp_webhook.envelope import extract_value
            resolved_args = {}
            for arg_name, dot_path in args_mapping.items():
                value = extract_value(envelope.payload, dot_path)
                resolved_args[arg_name] = value

            # Invoke tool
            tool_result = invoke_tool(tool_func, resolved_args)

            # Store in recent events buffer
            _store_recent_event(envelope.event_type, tool_result)

            return WorkerResult(
                task_id=task.task_id,
                success=True,
                tool=task.mapping_info.get("tool"),
                result=tool_result,
                error=None,
            )

        except Exception as e:
            logger.error(f"Error processing task {task.task_id}: {e}", exc_info=True)
            return WorkerResult(
                task_id=task.task_id,
                success=False,
                tool=task.mapping_info.get("tool"),
                result=None,
                error=str(e),
            )

    @property
    def is_running(self) -> bool:
        """Check if the worker is currently running.

        Returns:
            True if worker is running, False otherwise
        """
        return self._running

    @property
    def queue_size(self) -> int:
        """Get the current size of the task queue.

        Returns:
            Number of tasks currently in the queue

        Raises:
            RuntimeError: If worker is not running
        """
        if not self._running or self.queue is None:
            return 0
        return self.queue.qsize()


# Global worker instance (created on demand)
_worker: Optional[AsyncWorker] = None


def get_worker() -> AsyncWorker:
    """Get or create the global async worker instance.

    Returns:
        The global AsyncWorker instance
    """
    global _worker
    if _worker is None:
        _worker = AsyncWorker()
    return _worker


def reset_worker() -> None:
    """Reset the global worker instance.

    Primarily used in tests to ensure clean state between test cases.
    Note: This does not stop the worker if it's running.
    """
    global _worker
    _worker = None
