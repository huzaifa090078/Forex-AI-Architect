"""
Test configuration — shared event loop + test environment setup.

Two problems are solved here:

1. Dev-bypass auth (APP_ENV):
   APP_ENV is forced to "test" before any app module is imported so that
   get_current_user_id does NOT apply the development bypass.  Protected
   endpoints require a valid JWT — same as staging/production.  The intentional
   dev bypass in auth.py remains intact for local development.

2. asyncpg cross-loop "Future attached to different loop" (NullPool):
   The default connection pool (QueuePool) binds connections to the asyncio
   event loop in which they were first created.  Tests in auto mode run in
   function-scoped loops; session-scoped fixtures run in the session loop.
   When a test uses a pool connection created in the session loop, asyncpg
   raises RuntimeError.  Using NullPool removes pooling entirely — each DB
   request creates a fresh connection in the calling loop, then closes it.
   This is slower but avoids all cross-loop issues in the test suite.

os.environ["APP_ENV"] MUST be set before any import of app.core.config so
that pydantic_settings.BaseSettings reads "test" (not "development") when
it constructs the Settings singleton.

_configure_test_db() MUST be called before any test creates a FastAPI app
(i.e. before the session-scoped `client` fixture runs) so that get_db in
app.core.database uses the NullPool AsyncSessionLocal.  Because it runs at
conftest module load time, it executes before any pytest fixture setup.
"""
import os
os.environ["APP_ENV"] = "test"          # Must be first — before any app import

import asyncio
import pytest
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


def _configure_test_db() -> None:
    """
    Replace the module-level engine and AsyncSessionLocal in app.core.database
    with a NullPool version.

    app.core.database.get_db() references AsyncSessionLocal from the module's
    own global scope (looked up at call time, not captured at import time), so
    replacing the module attribute is sufficient to redirect all FastAPI
    dependency-injected DB sessions to the NullPool engine.
    """
    import app.core.database as _db
    from app.core.config import settings

    _connect_args: dict = {"ssl": True} if settings.database_use_ssl else {}

    _db.engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        echo=False,
        connect_args=_connect_args,
    )
    _db.AsyncSessionLocal = async_sessionmaker(
        bind=_db.engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


_configure_test_db()


@pytest.fixture(scope="session")
def event_loop():
    """
    Session-scoped event loop shared by all async fixtures and tests.

    Combined with asyncio_default_fixture_loop_scope=session in pytest.ini,
    this ensures that all session-scoped async fixtures (client, auth_headers)
    run in the same event loop.  NullPool removes the need for the loop to be
    shared with DB connections, but the session-scoped loop still prevents
    ASGI transport lifetime issues between fixtures.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
