---
name: E2E pipeline design
description: Auto-trading pipeline module design decisions — TP selection, lock strategy, singleton reuse.
---

# E2E Automated Trading Pipeline — Design Decisions

**Location:** `backend/app/modules/trading_pipeline/pipeline.py`

## Key Decisions

**take_profit_2 not take_profit_1:**
The AI engine returns `take_profit_1` (1:1 R:R) and `take_profit_2` (1:2 R:R). The pipeline passes `take_profit_2` to the Risk Manager because the default `RISK_MIN_RR=2.0` requires a 2:1 R:R. Passing `take_profit_1` would always fail the Risk Manager R:R check. Fall back to `take_profit_1` only when `take_profit_2` is None.

**Why:** `_compute_tp` in `RuleBasedAIEngine` returns `(entry + risk*1.0, entry + risk*2.0)` for BUY. `take_profit_2` is the 2:1 R:R target.

**Per-pair asyncio lock:**
`_pair_locks` dict + `_locks_registry` Lock prevents concurrent executions for the same pair. If the lock is already held, the new candle event is skipped (not queued).

**Why:** Without this, rapid candle events could queue many pipeline runs, each fetching data and calling the AI independently, creating a storm of identical trade requests.

**Singleton reuse:**
- Risk Manager uses `trade_manager._connector` for account/tick/position data — same connection as the Trade Manager, no second connection.
- `_news_filter` singleton from `app.modules.news_filter` wired into `_risk_manager` at module load.
- `_run_evaluation` imported from `app.api.v1.ai` to reuse the identical AI pipeline logic (not duplicated).

**asyncio.create_task in _on_candle:**
The candle callback spawns the pipeline as a background task so `_on_candle` returns immediately. The pipeline runs asynchronously; the next candle event is not blocked by the previous pipeline run.
