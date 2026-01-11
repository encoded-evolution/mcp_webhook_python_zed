"""Pytest configuration and shared fixtures.

This module provides common fixtures and configuration for running
async tests with pytest-asyncio and managing test dependencies.
"""

import asyncio
import pytest
from typing import AsyncGenerator, Generator

from mcp_webhook.config import reset_settings


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """Set up the event loop policy for async tests.

    This fixture runs once per test session and ensures all async tests
    use a consistent event loop configuration.

    Returns:
        The default event loop policy for the platform.
    """
    policy = asyncio.DefaultEventLoopPolicy()
    asyncio.set_event_loop_policy(policy)
    return policy


@pytest.fixture(autouse=True)
def reset_config() -> Generator[None, None, None]:
    """Reset configuration before and after each test.

    This fixture runs automatically for every test (autouse=True)
    to ensure clean configuration state between tests.
    """
    reset_settings()
    yield
    reset_settings()


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create a fresh event loop for each test.

    This overrides the default pytest-asyncio event loop fixture
    to ensure each test gets its own isolated loop.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
