"""
Automated E2E Trading Pipeline (Section 1–9 demo readiness).

Runtime execution chain:
  ScanResult (from MarketScanner)
      ↓  [direction must be "buy" or "sell"]
  AI Engine  (_run_evaluation — same logic as /v1/ai/signal)
      ↓  [action must be BUY or SELL; NO_TRADE stops here]
  Risk Manager  (approve_trade — full Section 8 checks)
      ↓  [approved=True only; rejection stops here]
  RiskApproval  (immutable token)
      ↓
  Trade Manager  (open_trade — validates RiskApproval before broker call)
      ↓
  MT5 Connector → Exness Demo Account

Architectural guarantees (enforced by design):
  ■ Scanner does NOT decide to trade — it only provides candidates.
  ■ AI makes the trading decision (BUY / SELL / NO_TRADE).
  ■ Risk Manager is the ONLY source of RiskApproval — no bypass exists.
  ■ Trade Manager validates the approval token before every broker call.
  ■ Per-pair asyncio lock prevents duplicate concurrent executions.
  ■ All exceptions are caught — candle callback is never interrupted.
  ■ No new abstractions created — reuses existing singletons/interfaces.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.modules.ai_engine.types import TradeAction
from app.modules.market_scanner.interfaces import ScanResult
from app.modules.news_filter import news_filter as _news_filter
from app.modules.risk_manager.manager import RuleBasedRiskManager
from app.modules.trade_manager.interfaces import OrderRequest
from app.modules.trade_manager.manager import trade_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level Risk Manager — news filter wired in at construction time.
# Uses the same MT5 connector as the Trade Manager singleton for all
# account / symbol / tick data calls.
# ---------------------------------------------------------------------------
_risk_manager = RuleBasedRiskManager(news_filter=_news_filter)

# ---------------------------------------------------------------------------
# Per-pair execution lock — prevents double-execution when multiple candle
# events for the same pair arrive in quick succession before the previous
# pipeline run has completed.
# ---------------------------------------------------------------------------
_pair_locks: dict[str, asyncio.Lock] = {}
_locks_registry = asyncio.Lock()


async def _get_pair_lock(pair: str) -> asyncio.Lock:
    """Return (and lazily create) the asyncio.Lock for *pair*."""
    async with _locks_registry:
        if pair not in _pair_locks:
            _pair_locks[pair] = asyncio.Lock()
        return _pair_locks[pair]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_pipeline_for_scan(scan_result: ScanResult) -> None:
    """
    Execute the full AI → Risk → Trade pipeline for a scanner candidate.

    Designed to be called as an ``asyncio.create_task`` from the candle
    callback in main.py so the callback returns immediately.

    All exceptions are caught and logged — this coroutine never propagates
    an exception to the event loop.

    Args:
        scan_result: A ScanResult produced by MarketScanner.scan_pair().
                     Non-directional results (direction="ranging") are
                     silently skipped.
    """
    pair      = scan_result.pair
    timeframe = scan_result.timeframe
    direction = scan_result.direction

    # ── Guard 1: only directional opportunities proceed ───────────────────────
    if direction not in ("buy", "sell"):
        logger.debug(
            "Pipeline [%s/%s]: direction=%r — non-directional, skipping",
            pair, timeframe, direction,
        )
        return

    # ── Guard 2: per-pair concurrency lock ────────────────────────────────────
    try:
        pair_lock = await _get_pair_lock(pair)
    except Exception as exc:
        logger.error("Pipeline [%s/%s]: failed to acquire pair lock: %s", pair, timeframe, exc)
        return

    if pair_lock.locked():
        logger.debug(
            "Pipeline [%s/%s]: pipeline already running for this pair — skipping duplicate",
            pair, timeframe,
        )
        return

    async with pair_lock:
        try:
            await _execute_pipeline(pair, timeframe)
        except Exception as exc:
            # Belt-and-suspenders: individual steps also catch exceptions,
            # but this outer catch ensures the lock is always released cleanly.
            logger.error(
                "Pipeline [%s/%s]: unhandled error in pipeline execution: %s",
                pair, timeframe, exc, exc_info=True,
            )


async def _execute_pipeline(pair: str, timeframe: str) -> None:
    """
    Inner pipeline — called under the per-pair lock.

    Steps:
      1. AI evaluation (fetches fresh data, runs indicators + SMC + engine).
      2. AI gate: stop on NO_TRADE.
      3. Validate AI output completeness.
      4. Risk Manager approval.
      5. Risk gate: stop on rejection.
      6. Build OrderRequest with the immutable RiskApproval token.
      7. Trade Manager execution.
    """
    # ── Step 1: AI evaluation ─────────────────────────────────────────────────
    # Import deferred to avoid circular import at module load time.
    # _run_evaluation is the canonical AI pipeline used by /v1/ai/signal.
    from app.api.v1.ai import _run_evaluation

    try:
        from fastapi import HTTPException
        decision = await _run_evaluation(pair, timeframe)
    except Exception as exc:
        # HTTPException from _run_evaluation means MT5/data unavailable (503)
        # or bad timeframe (400).  Log and abort — not a code bug.
        logger.warning(
            "Pipeline [%s/%s]: AI evaluation failed: %s", pair, timeframe, exc,
        )
        return

    # ── Step 2: AI gate ───────────────────────────────────────────────────────
    if decision.action == TradeAction.NO_TRADE:
        logger.debug(
            "Pipeline [%s/%s]: AI → NO_TRADE (conf=%.3f) | reasons: %s",
            pair, timeframe, decision.confidence,
            "; ".join(decision.rejection_reasons) if decision.rejection_reasons else "none",
        )
        return

    # ── Step 3: Validate AI output completeness ───────────────────────────────
    entry      : Optional[float] = decision.entry_price
    stop_loss  : Optional[float] = decision.stop_loss
    # Prefer TP2 (1:2 R:R) → satisfies RISK_MIN_RR=2.0 default.
    # Fall back to TP1 when TP2 is None (unusual edge case).
    take_profit: Optional[float] = decision.take_profit_2 or decision.take_profit_1

    if entry is None or stop_loss is None or take_profit is None:
        logger.warning(
            "Pipeline [%s/%s]: AI returned %s but entry/SL/TP incomplete "
            "(entry=%s sl=%s tp2=%s tp1=%s) — cannot proceed",
            pair, timeframe, decision.action.value,
            entry, stop_loss, decision.take_profit_2, decision.take_profit_1,
        )
        return

    trade_direction = decision.action.value.lower()  # "buy" or "sell"

    logger.info(
        "Pipeline [%s/%s]: AI → %s | conf=%.3f | entry=%.5f sl=%.5f tp=%.5f",
        pair, timeframe, decision.action.value,
        decision.confidence, entry, stop_loss, take_profit,
    )

    # ── Step 4: Risk Manager approval ─────────────────────────────────────────
    # Uses the Trade Manager's connector so all MT5 calls share the same
    # connection context.
    connector = trade_manager._connector
    try:
        approval = await _risk_manager.approve_trade(
            pair        = pair,
            direction   = trade_direction,
            entry       = entry,
            stop_loss   = stop_loss,
            take_profit = take_profit,
            connector   = connector,
        )
    except Exception as exc:
        # approve_trade() is documented as never-raising, but guard anyway.
        logger.error(
            "Pipeline [%s/%s]: Risk Manager raised unexpectedly: %s",
            pair, timeframe, exc, exc_info=True,
        )
        return

    # ── Step 5: Risk gate ─────────────────────────────────────────────────────
    if not approval.approved:
        logger.info(
            "Pipeline [%s/%s]: Risk Manager REJECTED | reasons: %s",
            pair, timeframe,
            "; ".join(approval.rejection_reasons),
        )
        return

    logger.info(
        "Pipeline [%s/%s]: Risk Manager APPROVED | lot=%.2f rr=%.2f",
        pair, timeframe, approval.lot_size, approval.rr_ratio,
    )

    # ── Step 6: Build OrderRequest with immutable RiskApproval token ──────────
    request = OrderRequest(
        pair          = pair,
        direction     = trade_direction,
        entry_price   = entry,
        stop_loss     = approval.stop_loss,    # Risk Manager may have adjusted SL
        take_profit   = approval.take_profit,  # Risk Manager may have adjusted TP
        lot_size      = approval.lot_size,
        risk_approval = approval,              # REQUIRED — Trade Manager validates this
        signal_id     = f"auto:{pair}:{timeframe}",
        notes         = (
            f"Auto | {decision.action.value} | "
            f"conf={decision.confidence:.2f} | tf={timeframe}"
        ),
        metadata      = {
            "timeframe":       timeframe,
            "confidence":      decision.confidence,
            "trade_quality":   decision.trade_quality.value,
            "smc_summary":     decision.smc_summary.bias if decision.smc_summary else None,
            "pipeline":        "auto",
        },
    )

    # ── Step 7: Trade Manager execution ───────────────────────────────────────
    # Trade Manager calls _validate_risk_approval() before any broker call.
    # If the RiskApproval does not match the OrderRequest exactly, execution
    # is blocked — no bypass path exists.
    try:
        result = await trade_manager.open_trade(request)
    except Exception as exc:
        logger.error(
            "Pipeline [%s/%s]: Trade Manager raised unexpectedly: %s",
            pair, timeframe, exc, exc_info=True,
        )
        return

    if result.success:
        logger.info(
            "Pipeline [%s/%s]: TRADE EXECUTED | ticket=%s fill=%.5f lot=%.2f",
            pair, timeframe,
            result.broker_order_id, result.fill_price or 0.0, approval.lot_size,
        )
    else:
        logger.warning(
            "Pipeline [%s/%s]: Trade Manager REJECTED | reason: %s",
            pair, timeframe, result.error_message,
        )
