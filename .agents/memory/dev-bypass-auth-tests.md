---
name: Dev bypass auth tests
description: 7 section11 tests that always fail in APP_ENV=development — known, expected, not regressions.
---

# Dev Bypass Auth Test Failures

**The rule:** 7 tests in `tests/test_section11_api.py` always fail when `APP_ENV=development`.

**Why:** `get_current_user_id` in `app/api/v1/auth.py` immediately returns `"dev-operator"` when `APP_ENV=development`, ignoring the JWT header. This causes:
- `test_me_authenticated` → GET /auth/me looks up "dev-operator" in DB → None → HTTP 404 (not 200)
- `test_me_unauthenticated` → also returns 200 or 404 rather than 401 (no auth enforcement)
- 5 `_unauthenticated` tests (dashboard/settings/logs/signals) → return 200 instead of 401

**These 7 failures are intentional and documented.** The dev bypass exists so the bot can run locally without a real JWT flow. The bypass must be reverted before production deployment.

**How to apply:** When running the test suite, expect 155 passed / 7 failed / 2 skipped in dev mode. Do NOT treat these 7 as regressions from code changes. The full suite with APP_ENV=production/staging would pass all 162 tests.
