---
name: Section 11 auth guards
description: Which backend endpoints require JWT auth guards and how they are wired.
---

All protected endpoints import `get_current_user_id` from `app.api.v1.auth` and add it as `_user_id: str = Depends(get_current_user_id)`.

Protected:
- `/v1/dashboard/summary` and `/v1/dashboard/performance`
- `/v1/signals`, `/v1/signals/active`, `/v1/signals/{id}`
- `/v1/logs`, `/v1/logs/errors`
- `/v1/settings` GET and PATCH

Not protected (public data):
- `/v1/market/*`, `/v1/news/*`, `/v1/candles`, `/v1/backtests/*`
- `/api/healthz`, `/api/ws` (WebSocket)

**Why:** Section 11 prompt requires operator authentication for all sensitive data endpoints. Without the guard, tests for unauthenticated access fail (expect 401/403 but get 200).

**How to apply:** Whenever a new endpoint is added that returns user/trade/signal/log data, add `_user_id: str = Depends(get_current_user_id)` to the route signature.
