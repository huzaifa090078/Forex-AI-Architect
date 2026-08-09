---
name: Test env setup
description: How and why conftest.py sets APP_ENV=test and NullPool for the test suite.
---

# Test Environment Setup (conftest.py)

## Two problems solved simultaneously

### 1. Dev bypass (APP_ENV)
`get_current_user_id` in `app/api/v1/auth.py` returns `"dev-operator"` immediately when
`APP_ENV == "development"`. This caused 7 section11 tests to fail:
- `test_me_authenticated`: dev-operator → DB lookup → None → 404 (not 200)
- 6 `_unauthenticated` tests: dev bypass → 200 (not 401)

Fix: `os.environ["APP_ENV"] = "test"` at the very top of `conftest.py`, before any import.
This must execute before `app.core.config` is first imported so the pydantic Settings
singleton reads APP_ENV=test.

### 2. asyncpg cross-loop "Future attached to different loop"
pytest-asyncio 0.24.0 with `asyncio_default_fixture_loop_scope = session` + custom `event_loop`
fixture creates TWO session loops:
  - L_plugin: pytest-asyncio internal session loop (used by session-scoped async fixtures)
  - L_custom: custom event_loop fixture loop (used by tests)

asyncpg pool connections created in L_plugin (from session fixtures) can't be used in L_custom
(from tests). Causes RuntimeError in any test that makes DB calls through the pool.

Fix: **NullPool** — replace `app.core.database.AsyncSessionLocal` with a NullPool-based
sessionmaker in conftest.py at module load time. NullPool creates a fresh connection per
request; no pooling means no cross-loop issues.

```python
_db.engine = create_async_engine(url, poolclass=NullPool, ...)
_db.AsyncSessionLocal = async_sessionmaker(bind=_db.engine, ...)
```

Key: `get_db()` in app.core.database looks up `AsyncSessionLocal` from its own module
global scope at call time, so replacing the module attribute redirects all FastAPI
dependency-injected sessions to the NullPool engine.

## Result
- 162 passed / 0 failed / 2 skipped (full suite)
- The dev bypass remains active for local development (APP_ENV defaults to "development")
- Production/staging require real JWT (APP_ENV != "development")

**Why:** Tests need real auth enforcement + stable DB behavior across different event loops.
**How to apply:** Both changes must coexist in conftest.py. Removing either one causes failures.
