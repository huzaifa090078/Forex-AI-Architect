"""
Test configuration — session-scoped event loop to prevent asyncpg
"Future attached to a different loop" errors across test functions.

All async fixtures and tests share a single event loop for the entire
test session. This is required because the DB engine (asyncpg pool) is
a module-level singleton tied to the loop it was first used in.
"""
import asyncio
import pytest


@pytest.fixture(scope="session")
def event_loop():
    """
    Override the default pytest-asyncio event loop to be session-scoped.
    Without this, each test function gets its own loop, which breaks
    asyncpg connections that were created in the first loop.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
