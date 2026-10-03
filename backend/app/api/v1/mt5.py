"""
MT5 Read-Only Integration Router.

Provides real-time read-only account, open positions, closed trade history,
and performance statistics fetched directly from the local MetaTrader 5 terminal.

Strictly READ-ONLY for demo account testing. Does not execute trades.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, Query, HTTPException

from app.modules.mt5_integration.base import RealMT5Connector, _MT5_AVAILABLE
from app.modules.mt5_integration.interfaces import AccountInfo, BrokerPosition, BrokerDeal

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared connector singleton for the MT5 API router
_connector = RealMT5Connector()
_is_connected: bool = False


async def _get_connected_connector() -> RealMT5Connector:
    """Ensure MT5 connection is established before servicing requests."""
    global _is_connected
    if not _MT5_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="MetaTrader5 Python package is not available on this platform.",
        )

    try:
        ok = await _connector.connect()
        if not ok:
            _is_connected = False
            raise HTTPException(
                status_code=502,
                detail="Failed to connect to local MetaTrader 5 terminal. Check terminal status and credentials.",
            )
        _is_connected = True
        return _connector
    except HTTPException:
        raise
    except Exception as exc:
        _is_connected = False
        logger.error("MT5 connector error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"MT5 connector error: {exc}",
        )


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class MT5AccountOut(BaseModel):
    login: int
    server: str
    company: str = ""
    currency: str = "USD"
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float = 0.0
    leverage: int = 1
    floating_pnl: float = 0.0          # Floating P/L on currently open positions
    trade_allowed: bool = False
    trade_expert: bool = False
    connected: bool = True
    checked_at: str


class MT5PositionOut(BaseModel):
    ticket: int
    symbol: str
    direction: str                     # "buy" | "sell"
    volume: float
    open_price: float
    current_price: float
    sl: float = 0.0
    tp: float = 0.0
    floating_pnl: float                # Floating profit/loss
    swap: float = 0.0
    magic: int = 0
    open_time: str
    comment: str = ""


class MT5DealOut(BaseModel):
    ticket: int
    order: int
    symbol: str
    direction: str                     # "buy" | "sell" | "balance"
    entry: str                         # "in" | "out" | "inout" | "out_by"
    volume: float
    price: float
    profit: float                      # Realized profit/loss
    commission: float = 0.0
    swap: float = 0.0
    net_profit: float = 0.0            # Realized profit + commission + swap
    close_time: str
    magic: int = 0
    comment: str = ""


class MT5StatsOut(BaseModel):
    total_trades: int = 0              # Closed trading deals count
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0              # 0 - 100%
    total_realized_profit: float = 0.0 # Gross closed profit
    total_realized_loss: float = 0.0   # Gross closed loss
    net_realized_pnl: float = 0.0      # Total realized trading profit + comm + swap
    today_realized_pnl: float = 0.0    # Deals closed today
    today_trades_count: int = 0
    open_positions_count: int = 0
    total_floating_pnl: float = 0.0    # Floating P/L on open positions
    account_balance: float = 0.0
    account_equity: float = 0.0
    free_margin: float = 0.0
    margin_level: float = 0.0
    connected: bool = True


class MT5SummaryOut(BaseModel):
    connected: bool
    account: Optional[MT5AccountOut] = None
    positions: List[MT5PositionOut] = Field(default_factory=list)
    history: List[MT5DealOut] = Field(default_factory=list)
    stats: MT5StatsOut
    timestamp: str


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/account", response_model=MT5AccountOut)
async def get_mt5_account() -> MT5AccountOut:
    """Return live connected MT5 account snapshot."""
    conn = await _get_connected_connector()
    info = await conn.get_account_info()
    return MT5AccountOut(
        login=info.login,
        server=info.server,
        company=info.company,
        currency=info.currency,
        balance=round(info.balance, 2),
        equity=round(info.equity, 2),
        margin=round(info.margin, 2),
        free_margin=round(info.free_margin, 2),
        margin_level=round(info.margin_level, 2),
        leverage=info.leverage,
        floating_pnl=round(info.profit, 2),
        trade_allowed=info.trade_allowed,
        trade_expert=info.trade_expert,
        connected=info.connected,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/positions", response_model=List[MT5PositionOut])
async def get_mt5_positions() -> List[MT5PositionOut]:
    """Return all currently open positions from MT5."""
    conn = await _get_connected_connector()
    raw_positions = await conn.get_positions()
    result: List[MT5PositionOut] = []
    for p in raw_positions:
        result.append(
            MT5PositionOut(
                ticket=p.ticket,
                symbol=p.symbol,
                direction=p.type,
                volume=round(p.volume, 2),
                open_price=round(p.open_price, 5),
                current_price=round(p.current_price, 5),
                sl=round(p.sl, 5),
                tp=round(p.tp, 5),
                floating_pnl=round(p.profit, 2),
                swap=round(p.swap, 2),
                magic=p.magic,
                open_time=p.open_time.isoformat(),
                comment=p.comment,
            )
        )
    return result


@router.get("/history", response_model=List[MT5DealOut])
async def get_mt5_history(
    days: int = Query(default=30, ge=1, le=365),
    include_balance: bool = Query(default=False),
) -> List[MT5DealOut]:
    """Return closed trade deals from MT5 history within the specified period."""
    conn = await _get_connected_connector()
    raw_deals = await conn.get_history_deals(days=days)
    result: List[MT5DealOut] = []
    for d in raw_deals:
        # If not include_balance, filter out non-trade balance actions (e.g. deposits)
        if not include_balance and d.type not in ("buy", "sell"):
            continue
        net = d.profit + d.commission + d.swap
        result.append(
            MT5DealOut(
                ticket=d.ticket,
                order=d.order,
                symbol=d.symbol,
                direction=d.type,
                entry=d.entry,
                volume=round(d.volume, 2),
                price=round(d.price, 5),
                profit=round(d.profit, 2),
                commission=round(d.commission, 2),
                swap=round(d.swap, 2),
                net_profit=round(net, 2),
                close_time=d.time.isoformat(),
                magic=d.magic,
                comment=d.comment,
            )
        )
    return result


@router.get("/stats", response_model=MT5StatsOut)
async def get_mt5_stats(days: int = Query(default=30, ge=1, le=365)) -> MT5StatsOut:
    """Calculate aggregate performance metrics separating Realized P/L from Floating P/L."""
    conn = await _get_connected_connector()
    info = await conn.get_account_info()
    positions = await conn.get_positions()
    deals = await conn.get_history_deals(days=days)

    now_utc = datetime.now(timezone.utc)
    today_date = now_utc.date()

    # Closed trades: entry is out/inout and type is buy/sell
    closed_trades = [
        d for d in deals
        if d.type in ("buy", "sell") and d.entry in ("out", "inout", "out_by")
    ]

    total_trades = len(closed_trades)
    winning = [d for d in closed_trades if (d.profit + d.commission + d.swap) > 0]
    losing = [d for d in closed_trades if (d.profit + d.commission + d.swap) < 0]
    win_rate = round((len(winning) / total_trades * 100), 1) if total_trades > 0 else 0.0

    total_realized_profit = sum(d.profit for d in winning)
    total_realized_loss = sum(d.profit for d in losing)
    net_realized_pnl = sum((d.profit + d.commission + d.swap) for d in closed_trades)

    today_trades = [d for d in closed_trades if d.time.date() == today_date]
    today_realized_pnl = sum((d.profit + d.commission + d.swap) for d in today_trades)

    total_floating_pnl = sum(p.profit for p in positions)

    return MT5StatsOut(
        total_trades=total_trades,
        winning_trades=len(winning),
        losing_trades=len(losing),
        win_rate=win_rate,
        total_realized_profit=round(total_realized_profit, 2),
        total_realized_loss=round(total_realized_loss, 2),
        net_realized_pnl=round(net_realized_pnl, 2),
        today_realized_pnl=round(today_realized_pnl, 2),
        today_trades_count=len(today_trades),
        open_positions_count=len(positions),
        total_floating_pnl=round(total_floating_pnl, 2),
        account_balance=round(info.balance, 2),
        account_equity=round(info.equity, 2),
        free_margin=round(info.free_margin, 2),
        margin_level=round(info.margin_level, 2),
        connected=info.connected,
    )


@router.get("/summary", response_model=MT5SummaryOut)
async def get_mt5_summary(days: int = Query(default=30, ge=1, le=365)) -> MT5SummaryOut:
    """
    Combined polling endpoint for dashboard.
    Retrieves account, positions, trade history, and metrics in a single round-trip.
    """
    try:
        conn = await _get_connected_connector()
        info = await conn.get_account_info()
        positions = await conn.get_positions()
        deals = await conn.get_history_deals(days=days)
    except Exception as exc:
        logger.warning("MT5 summary retrieval failed: %s", exc)
        return MT5SummaryOut(
            connected=False,
            account=None,
            positions=[],
            history=[],
            stats=MT5StatsOut(connected=False),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    now_utc = datetime.now(timezone.utc)
    today_date = now_utc.date()

    # Build account out
    account_out = MT5AccountOut(
        login=info.login,
        server=info.server,
        company=info.company,
        currency=info.currency,
        balance=round(info.balance, 2),
        equity=round(info.equity, 2),
        margin=round(info.margin, 2),
        free_margin=round(info.free_margin, 2),
        margin_level=round(info.margin_level, 2),
        leverage=info.leverage,
        floating_pnl=round(info.profit, 2),
        trade_allowed=info.trade_allowed,
        trade_expert=info.trade_expert,
        connected=info.connected,
        checked_at=now_utc.isoformat(),
    )

    # Build positions out
    positions_out = [
        MT5PositionOut(
            ticket=p.ticket,
            symbol=p.symbol,
            direction=p.type,
            volume=round(p.volume, 2),
            open_price=round(p.open_price, 5),
            current_price=round(p.current_price, 5),
            sl=round(p.sl, 5),
            tp=round(p.tp, 5),
            floating_pnl=round(p.profit, 2),
            swap=round(p.swap, 2),
            magic=p.magic,
            open_time=p.open_time.isoformat(),
            comment=p.comment,
        )
        for p in positions
    ]

    # Build history out (trade deals only)
    trade_deals = [d for d in deals if d.type in ("buy", "sell")]
    history_out = [
        MT5DealOut(
            ticket=d.ticket,
            order=d.order,
            symbol=d.symbol,
            direction=d.type,
            entry=d.entry,
            volume=round(d.volume, 2),
            price=round(d.price, 5),
            profit=round(d.profit, 2),
            commission=round(d.commission, 2),
            swap=round(d.swap, 2),
            net_profit=round(d.profit + d.commission + d.swap, 2),
            close_time=d.time.isoformat(),
            magic=d.magic,
            comment=d.comment,
        )
        for d in trade_deals
    ]

    # Calculate stats
    closed_trades = [d for d in trade_deals if d.entry in ("out", "inout", "out_by")]
    total_trades = len(closed_trades)
    winning = [d for d in closed_trades if (d.profit + d.commission + d.swap) > 0]
    losing = [d for d in closed_trades if (d.profit + d.commission + d.swap) < 0]
    win_rate = round((len(winning) / total_trades * 100), 1) if total_trades > 0 else 0.0

    total_realized_profit = sum(d.profit for d in winning)
    total_realized_loss = sum(d.profit for d in losing)
    net_realized_pnl = sum((d.profit + d.commission + d.swap) for d in closed_trades)

    today_trades = [d for d in closed_trades if d.time.date() == today_date]
    today_realized_pnl = sum((d.profit + d.commission + d.swap) for d in today_trades)
    total_floating_pnl = sum(p.profit for p in positions)

    stats_out = MT5StatsOut(
        total_trades=total_trades,
        winning_trades=len(winning),
        losing_trades=len(losing),
        win_rate=win_rate,
        total_realized_profit=round(total_realized_profit, 2),
        total_realized_loss=round(total_realized_loss, 2),
        net_realized_pnl=round(net_realized_pnl, 2),
        today_realized_pnl=round(today_realized_pnl, 2),
        today_trades_count=len(today_trades),
        open_positions_count=len(positions),
        total_floating_pnl=round(total_floating_pnl, 2),
        account_balance=round(info.balance, 2),
        account_equity=round(info.equity, 2),
        free_margin=round(info.free_margin, 2),
        margin_level=round(info.margin_level, 2),
        connected=True,
    )

    return MT5SummaryOut(
        connected=True,
        account=account_out,
        positions=positions_out,
        history=history_out,
        stats=stats_out,
        timestamp=now_utc.isoformat(),
    )
