"""
Trade management routes — full Section 9 implementation.

Endpoints:
  GET    /v1/trades            — paginated trade history
  GET    /v1/trades/stats      — aggregate performance statistics
  GET    /v1/trades/open       — live open trades enriched with broker data
  GET    /v1/trades/{id}       — single trade record
  POST   /v1/trades            — record a manual trade (no broker execution)
  PATCH  /v1/trades/{id}       — modify SL/TP or status
  DELETE /v1/trades/{id}       — cancel/delete a non-executed trade
  POST   /v1/trades/{id}/close — manual broker close of an open position
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.db.schemas import (
    TradeOut,
    TradeInput,
    TradeUpdate,
    TradeStatsOut,
    PaginatedTradesOut,
    OpenTradeOut,
    ManualCloseIn,
    TradeExecutionResultOut,
)
from app.api.v1.auth import get_current_user_id
from app.modules.trade_manager.service import TradeService
from app.modules.trade_manager.manager import trade_manager

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Helper: compute pip distances ──────────────────────────────────────────

def _pip_distance(price_a: float, price_b: float, pair: str) -> float:
    """Approximate pip distance between two prices for a given pair."""
    divisor = 100.0 if "JPY" in pair.upper() else 10_000.0
    return round(abs(price_a - price_b) * divisor, 1)


# ─── GET /v1/trades ──────────────────────────────────────────────────────────

@router.get("", response_model=PaginatedTradesOut)
async def list_trades(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    status_filter: str = Query(default="all", alias="status"),
    pair: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> PaginatedTradesOut:
    """Return paginated trade records with optional filters."""
    trades, total = await TradeService.get_trades(
        db, status_filter=status_filter, pair=pair, page=page, limit=limit
    )
    return PaginatedTradesOut(
        items=[TradeOut.model_validate(t) for t in trades],
        total=total,
        page=page,
        limit=limit,
    )


# ─── GET /v1/trades/stats ────────────────────────────────────────────────────

@router.get("/stats", response_model=TradeStatsOut)
async def get_stats(db: AsyncSession = Depends(get_db)) -> TradeStatsOut:
    """Aggregate performance statistics across all closed trades."""
    stats = await TradeService.get_stats(db)
    return TradeStatsOut(**stats)


# ─── GET /v1/trades/open ─────────────────────────────────────────────────────

@router.get("/open", response_model=List[OpenTradeOut])
async def get_open_trades(db: AsyncSession = Depends(get_db)) -> List[OpenTradeOut]:
    """
    Return all open trades enriched with live broker prices and PnL where available.
    Falls back to database values when MT5 is unavailable (non-Windows environment).
    """
    db_trades = await TradeService.get_open_trades(db)

    # Attempt to fetch live broker positions (fails gracefully on Linux/no MT5)
    broker_map: dict = {}
    try:
        positions = await trade_manager._connector.get_positions()
        broker_map = {str(p.ticket): p for p in positions}
    except Exception:
        pass  # Not an error — live data is optional enrichment

    now = datetime.now(timezone.utc)
    result = []
    for trade in db_trades:
        bp = broker_map.get(trade.broker_order_id or "")
        current_price = bp.current_price if bp else None
        live_pnl      = float(bp.profit) if bp else trade.pnl
        duration      = int((now - trade.opened_at).total_seconds()) if trade.opened_at else None

        sl_dist = (
            _pip_distance(current_price, trade.stop_loss, trade.pair)
            if current_price else None
        )
        tp_dist = (
            _pip_distance(current_price, trade.take_profit, trade.pair)
            if current_price else None
        )

        result.append(OpenTradeOut(
            id=trade.id,
            pair=trade.pair,
            direction=trade.direction,
            entry_price=trade.entry_price,
            current_price=current_price,
            stop_loss=trade.stop_loss,
            take_profit=trade.take_profit,
            lot_size=trade.lot_size,
            pnl=live_pnl,
            status=trade.status,
            opened_at=trade.opened_at,
            duration_seconds=duration,
            broker_ticket=trade.broker_order_id,
            sl_distance_pips=sl_dist,
            tp_distance_pips=tp_dist,
            risk_reward_ratio=trade.risk_reward_ratio,
        ))
    return result


# ─── GET /v1/trades/{id} ─────────────────────────────────────────────────────

@router.get("/{id}", response_model=TradeOut)
async def get_trade(
    id: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> TradeOut:
    """Return a single trade record by its UUID."""
    trade = await TradeService.get_trade(db, id)
    if trade is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    return TradeOut.model_validate(trade)


# ─── POST /v1/trades ─────────────────────────────────────────────────────────

@router.post("", response_model=TradeOut, status_code=status.HTTP_201_CREATED)
async def create_trade(
    payload: TradeInput,
    db: AsyncSession = Depends(get_db),
) -> TradeOut:
    """
    Record a manual trade directly into the database.
    This route does NOT send an order to the broker — it is for
    manually recorded trades or administrative imports.
    For live bot execution use the internal AI → Risk → TradeManager pipeline.
    """
    if payload.direction not in ("buy", "sell"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="direction must be 'buy' or 'sell'",
        )
    trade = await TradeService.create_trade(db, {
        "user_id":    settings.TRADE_BOT_USER_ID,
        "pair":       payload.pair.upper(),
        "direction":  payload.direction,
        "entry_price": payload.entry_price,
        "stop_loss":  payload.stop_loss,
        "take_profit": payload.take_profit,
        "lot_size":   payload.lot_size,
        "status":     "open",
        "notes":      payload.notes,
        "signal_id":  payload.signal_id,
    })
    return TradeOut.model_validate(trade)


# ─── PATCH /v1/trades/{id} ───────────────────────────────────────────────────

@router.patch("/{id}", response_model=TradeOut)
async def update_trade(
    payload: TradeUpdate,
    id: str = Path(...),
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),   # Task 2: auth guard
) -> TradeOut:
    """
    Update SL, TP, notes, or close/cancel a trade record.

    If stop_loss or take_profit are changed AND the trade has a broker ticket,
    the modification is forwarded to the broker via the Trade Manager.
    """
    trade = await TradeService.get_trade(db, id)
    if trade is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")

    # Broker modification for live SL/TP changes
    if trade.status == "open" and trade.broker_order_id:
        if payload.stop_loss is not None or payload.take_profit is not None:
            success = await trade_manager.modify_trade(
                id,
                stop_loss=payload.stop_loss,
                take_profit=payload.take_profit,
            )
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Broker rejected the SL/TP modification",
                )

    # DB update
    updates = payload.model_dump(exclude_none=True)
    updated = await TradeService.update_trade(db, id, **updates)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    return TradeOut.model_validate(updated)


# ─── DELETE /v1/trades/{id} ──────────────────────────────────────────────────

@router.delete("/{id}")
async def delete_trade(
    id: str = Path(...),
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),   # Task 2: auth guard
) -> Response:
    """
    Delete a trade record.
    Only allowed when the trade has no broker_order_id (never sent to broker).
    Trades with a live or executed broker ticket cannot be deleted.
    Returns HTTP 204 No Content on success.
    """
    trade = await TradeService.get_trade(db, id)
    if trade is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    if trade.broker_order_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot delete a trade that has been sent to the broker "
                f"(ticket={trade.broker_order_id}). Close it first."
            ),
        )
    deleted = await TradeService.delete_trade(db, id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── POST /v1/trades/{id}/close ──────────────────────────────────────────────

@router.post("/{id}/close", response_model=TradeExecutionResultOut)
async def close_trade(
    id: str = Path(...),
    payload: ManualCloseIn = ManualCloseIn(),
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),   # Task 2: auth guard
) -> TradeExecutionResultOut:
    """
    Manually close an open position via the broker.
    Sends a market close order through the MT5 connector, then updates the DB.
    """
    trade = await TradeService.get_trade(db, id)
    if trade is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    if trade.status != "open":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Trade is not open (status={trade.status!r})",
        )

    result = await trade_manager.close_trade(id, reason=payload.reason)
    return TradeExecutionResultOut(
        success=result.success,
        broker_order_id=result.broker_order_id,
        fill_price=result.fill_price,
        fill_time=result.fill_time,
        error_message=result.error_message,
    )
