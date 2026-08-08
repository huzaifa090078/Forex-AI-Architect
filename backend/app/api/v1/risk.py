"""
Risk Manager API routes (Section 8).

Exposes Risk Manager state and pre-flight trade approval through the existing
API architecture.  All endpoints follow the project's Pydantic / camelCase
serialization conventions.

Endpoints:
  GET  /v1/risk/state              — configuration + live protection state
  POST /v1/risk/approve            — run full approve_trade() pre-flight check
  POST /v1/risk/record-close       — record a closed trade P&L (updates daily stats)
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.db.schemas import (
    ProtectionStateOut,
    RiskApprovalIn,
    RiskApprovalOut,
    RiskStateOut,
    RecordTradeCloseIn,
)
from app.modules.market_scanner.market_data_service import MarketDataService
from app.modules.mt5_integration.base import RealMT5Connector
from app.modules.risk_manager.manager import RuleBasedRiskManager
from app.modules.risk_manager.types import ProtectionState

router   = APIRouter()
logger   = logging.getLogger(__name__)

# Module-level singletons (mirrors the pattern in ai.py)
_connector = RealMT5Connector()
_manager   = RuleBasedRiskManager()   # no news filter wired yet — Section 13


def _protection_state_to_out(ps: ProtectionState) -> ProtectionStateOut:
    return ProtectionStateOut(
        dailyLossActive       = ps.daily_loss_active,
        dailyProfitActive     = ps.daily_profit_active,
        drawdownActive        = ps.drawdown_active,
        consecutiveLossActive = ps.consecutive_loss_active,
        maxOpenTradesActive   = ps.max_open_trades_active,
        sessionBlocked        = ps.session_blocked,
        newsBlocked           = ps.news_blocked,
        spreadBlocked         = ps.spread_blocked,
        exposureBlocked       = ps.exposure_blocked,
        anyActive             = ps.any_active(),
        dailyPnl              = ps.daily_pnl,
        dailyPnlPct           = ps.daily_pnl_pct,
        drawdownPct           = ps.drawdown_pct,
        consecutiveLosses     = ps.consecutive_losses,
        openTrades            = ps.open_trades,
    )


@router.get(
    "/state",
    response_model=RiskStateOut,
    summary="Risk Manager configuration and live protection state",
)
async def get_risk_state() -> RiskStateOut:
    """
    Return the current Risk Manager configuration and all active protection states.

    Returns 503 when MT5 is unavailable (Replit / Linux environment).
    The protection state section will show all-false defaults when the connector
    cannot retrieve live account/position data.
    """
    try:
        protection = await _manager.get_protection_state(_connector)
    except Exception as exc:
        logger.warning("risk/state: could not retrieve protection state — %s", exc)
        protection = ProtectionState()

    return RiskStateOut(
        riskPerTradePct         = settings.RISK_PER_TRADE_PERCENT,
        minRr                   = settings.RISK_MIN_RR,
        maxOpenTrades           = settings.MAX_OPEN_TRADES,
        maxDailyLossPct         = settings.MAX_DAILY_LOSS_PERCENT,
        maxDailyProfitPct       = settings.RISK_MAX_DAILY_PROFIT_PERCENT,
        maxDrawdownPct          = settings.RISK_MAX_DRAWDOWN_PERCENT,
        maxConsecutiveLosses    = settings.RISK_MAX_CONSECUTIVE_LOSSES,
        maxSpreadPips           = settings.RISK_MAX_SPREAD_PIPS,
        allowedSessions         = settings.RISK_ALLOWED_SESSIONS,
        maxTotalOpenLots        = settings.RISK_MAX_TOTAL_OPEN_LOTS,
        maxCurrencyExposureLots = settings.RISK_MAX_CURRENCY_EXPOSURE_LOTS,
        protection              = _protection_state_to_out(protection),
    )


@router.post(
    "/approve",
    response_model=RiskApprovalOut,
    summary="Pre-flight risk approval for a proposed trade",
)
async def approve_trade(payload: RiskApprovalIn) -> RiskApprovalOut:
    """
    Run the full Section 8 risk pipeline for a proposed trade.

    Returns 503 when MT5 is unavailable (Linux / no terminal connected).

    All mandatory checks are applied:
      SL/TP validity, R:R, lot sizing, risk cap, max open trades, spread,
      daily loss/profit, drawdown, consecutive losses, session, news, exposure.

    The returned ``approved`` field and ``lotSize`` should be used when
    constructing an OrderRequest for the Trade Manager.  The Trade Manager
    validates the approval token before sending any broker order.
    """
    try:
        approval = await _manager.approve_trade(
            pair        = payload.pair,
            direction   = payload.direction,
            entry       = payload.entry,
            stop_loss   = payload.stop_loss,
            take_profit = payload.take_profit,
            connector   = _connector,
        )
    except RuntimeError as exc:
        # MT5 unavailable on Replit/Linux
        raise HTTPException(
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE,
            detail      = f"MT5 connector unavailable: {exc}",
        )
    except Exception as exc:
        logger.exception("risk/approve: unexpected error")
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail      = f"Risk Manager error: {exc}",
        )

    return RiskApprovalOut(
        approved          = approval.approved,
        pair              = approval.pair,
        direction         = approval.direction,
        entry             = approval.entry,
        stopLoss          = approval.stop_loss,
        takeProfit        = approval.take_profit,
        lotSize           = approval.lot_size,
        riskAmount        = approval.risk_amount,
        riskPct           = approval.risk_pct,
        rrRatio           = approval.rr_ratio,
        rejectionReasons  = list(approval.rejection_reasons),
        protectionFlags   = list(approval.protection_flags),
        approvedAt        = approval.approved_at,
    )


@router.post(
    "/record-close",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Record a closed trade P&L in the daily stats tracker",
)
async def record_trade_close(payload: RecordTradeCloseIn) -> None:
    """
    Notify the Risk Manager that a trade has been closed with the given P&L.

    Updates daily loss / profit / consecutive-loss counters.
    Idempotent — the same trade_id recorded twice has no additional effect.
    """
    await _manager.record_closed_trade(
        trade_id = payload.trade_id,
        pnl      = payload.pnl,
    )
