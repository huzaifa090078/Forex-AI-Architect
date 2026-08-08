---
name: Asyncpg event loop tests
description: How to avoid asyncpg "Future attached to different loop" errors in pytest tests.
---

The asyncpg connection pool is a module-level singleton (SQLAlchemy async engine). If each test function creates a new event loop, connections from the pool (created in the first loop) become incompatible.

**Fix applied:**
1. `backend/pytest.ini` — `asyncio_mode = auto`, `asyncio_default_fixture_loop_scope = session`
2. `backend/tests/conftest.py` — session-scoped `event_loop` fixture that creates one loop for the entire test session
3. `backend/tests/test_section11_api.py` — `client` and `auth_headers` fixtures use `scope="session"` so they share the same loop as the DB pool

**Why:** Without session-scoped loop, each test class/function gets its own loop, and asyncpg protocol futures from the old loop can't be awaited in the new one → RuntimeError.

**How to apply:** Any future test file that hits the DB via ASGI transport must use the session-scoped `client` and `auth_headers` fixtures, not function-scoped ones.
