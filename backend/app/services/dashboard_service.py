"""
Dashboard Service — aggregates KPIs and performance series from the DB.

No MT5 calls here; data comes purely from the trades/signals tables
and the BotSettings singleton.  MT5 account data (balance/equity) is
filled in separately by the health endpoint.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotSettings, SystemLog, Trade
from app.db.schemas import DashboardSummaryOut, PerformancePointOut
from app.modules.news_filter.monitor import news_monitor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bot status detection
# ---------------------------------------------------------------------------

def _bot_status() -> str:
    """
    Best-effort bot status based on news_monitor task state.
    Returns: running | paused | stopped | error
    """
    task = getattr(news_monitor, "_task", None)
    if task is None:
        return "stopped"
    if task.done():
        exc = task.exception() if not task.cancelled() else None
        return "error" if exc else "stopped"
    return "running"


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

async def _get_open_count(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).select_from(Trade).where(Trade.status == "open")
    )
    return result.scalar_one() or 0


async def _get_trade_stats(db: AsyncSession):
    """Returns (total, winning, total_pnl, today_pnl, all_time_equity_proxy)."""
    # All closed trades
    result = await db.execute(
        select(Trade.pnl, Trade.closed_at)
        .where(Trade.status == "closed")
    )
    rows = result.all()

    today_utc = datetime.now(timezone.utc).date()
    total_pnl  = 0.0
    today_pnl  = 0.0
    winning    = 0
    total      = len(rows)

    for pnl, closed_at in rows:
        if pnl is None:
            continue
        total_pnl += pnl
        if pnl > 0:
            winning += 1
        if closed_at and closed_at.date() == today_utc:
            today_pnl += pnl

    win_rate = (winning / total) if total > 0 else 0.0
    return total, total_pnl, today_pnl, win_rate


async def get_summary(db: AsyncSession) -> DashboardSummaryOut:
    """
    Assemble dashboard KPIs.
    Balance/equity are placeholders (MT5 not available on Linux);
    real values come when the bot runs on Windows with a live MT5 terminal.
    """
    open_count = await _get_open_count(db)
    total, total_pnl, today_pnl, win_rate = await _get_trade_stats(db)

    # Balance/equity/margin: fetch from MT5 if connector is live
    balance = 0.0
    equity = 0.0
    margin = None
    free_margin = None
    leverage = None
    mt5_connected = False
    broker_server = None

    try:
        from app.modules.trade_manager.manager import trade_manager
        connector = getattr(trade_manager, "_connector", None)
        if connector is not None:
            info = await connector.get_account_info()
            if info:
                balance = float(info.balance)
                equity = float(info.equity)
                margin = float(info.margin)
                free_margin = float(info.free_margin)
                leverage = int(info.leverage)
                mt5_connected = bool(info.connected)
                broker_server = str(info.server)
    except Exception:
        pass

    return DashboardSummaryOut(
        balance        = round(balance, 2),
        equity         = round(equity, 2),
        total_pnl      = round(total_pnl, 2),
        today_pnl      = round(today_pnl, 2),
        open_trades    = open_count,
        total_trades   = total,
        win_rate       = round(win_rate, 4),
        bot_status     = _bot_status(),
        mt5_connected  = mt5_connected,
        broker_server  = broker_server,
        margin         = round(margin, 2) if margin is not None else None,
        free_margin    = round(free_margin, 2) if free_margin is not None else None,
        leverage       = leverage,
    )


async def get_performance(db: AsyncSession, period: str) -> List[PerformancePointOut]:
    """
    Return daily equity-curve data points for the given period.
    Computed from closed trades aggregated by date.
    """
    now = datetime.now(timezone.utc)

    period_map = {
        "1d":  1, "7d": 7, "30d": 30,
        "90d": 90, "1y": 365, "all": 3650,
    }
    days = period_map.get(period, 30)
    since = now - timedelta(days=days)

    result = await db.execute(
        select(Trade.closed_at, Trade.pnl)
        .where(Trade.status == "closed")
        .where(Trade.closed_at >= since)
        .order_by(Trade.closed_at)
    )
    rows = result.all()

    # Group by date
    daily: dict[date, list[float]] = {}
    for closed_at, pnl in rows:
        if closed_at is None or pnl is None:
            continue
        d = closed_at.date()
        daily.setdefault(d, []).append(pnl)

    if not daily:
        return []

    # Build cumulative equity series
    points: List[PerformancePointOut] = []
    running = 0.0
    for d in sorted(daily.keys()):
        pnls = daily[d]
        day_pnl = sum(pnls)
        running += day_pnl
        points.append(PerformancePointOut(
            date   = d.isoformat(),
            equity = round(running, 2),
            pnl    = round(day_pnl, 2),
            trades = len(pnls),
        ))

    return points
