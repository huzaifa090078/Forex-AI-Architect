"""
Backtesting routes — queue runs and retrieve results (Section 15).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user_id
from app.core.database import get_db
from app.db.models import Backtest, User
from app.db.schemas import BacktestInput, BacktestOut
from app.modules.backtesting.engine import ConcreteBacktestEngine
from app.modules.backtesting.interfaces import BacktestConfig

logger = logging.getLogger(__name__)
router = APIRouter()

_engine = ConcreteBacktestEngine()


def _parse_date(d_str: str) -> date:
    try:
        return date.fromisoformat(d_str.split("T")[0])
    except Exception:
        return date.today()


@router.get("", response_model=List[BacktestOut])
async def list_backtests(
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
) -> List[BacktestOut]:
    """Return all historical backtest runs."""
    try:
        stmt = select(Backtest).order_by(Backtest.created_at.desc())
        result = await db.execute(stmt)
        records = result.scalars().all()
        return [BacktestOut.model_validate(r) for r in records]
    except Exception as exc:
        logger.error("list_backtests failed: %s", exc)
        return []


@router.post("", response_model=BacktestOut, status_code=status.HTTP_201_CREATED)
async def create_backtest(
    payload: BacktestInput,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> BacktestOut:
    """
    Execute a backtest run on historical data.
    """
    from_d = _parse_date(payload.from_date)
    to_d = _parse_date(payload.to_date)

    if from_d >= to_d:
        raise HTTPException(
            status_code=400,
            detail="from_date must be before to_date",
        )

    # Ensure a valid user_id
    effective_user_id = user_id
    if not effective_user_id:
        user_res = await db.execute(select(User).limit(1))
        u = user_res.scalars().first()
        effective_user_id = u.id if u else str(uuid.uuid4())

    backtest_id = str(uuid.uuid4())
    record = Backtest(
        id=backtest_id,
        user_id=effective_user_id,
        strategy_id=payload.strategy_id,
        pair=payload.pair.upper(),
        from_date=payload.from_date,
        to_date=payload.to_date,
        status="running",
        initial_balance=payload.initial_balance,
    )
    db.add(record)
    await db.commit()

    config = BacktestConfig(
        strategy_id=payload.strategy_id,
        pair=payload.pair.upper(),
        from_date=from_d,
        to_date=to_d,
        initial_balance=float(payload.initial_balance),
        lot_size=float(payload.lot_size),
        risk_per_trade_pct=float(payload.risk_per_trade or 1.0),
    )

    try:
        res = await _engine.run(config)
        record.status = "completed"
        record.initial_balance = res.initial_balance
        record.final_balance = res.final_balance
        record.total_trades = res.total_trades
        record.winning_trades = res.winning_trades
        record.losing_trades = res.losing_trades
        record.win_rate = res.win_rate
        record.profit_factor = res.profit_factor
        record.max_drawdown = res.max_drawdown
        record.net_pnl = res.net_pnl
        record.sharpe_ratio = res.sharpe_ratio
        record.completed_at = datetime.now(timezone.utc)
        record.result_detail = {
            "trades": [
                {
                    "open_time": t.open_time,
                    "close_time": t.close_time,
                    "pair": t.pair,
                    "direction": t.direction,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "stop_loss": t.stop_loss,
                    "take_profit": t.take_profit,
                    "lot_size": t.lot_size,
                    "pnl": t.pnl,
                    "exit_reason": t.exit_reason,
                }
                for t in res.trades
            ],
            "equity_curve": res.equity_curve,
            "metadata": res.metadata,
        }
        await db.commit()
        await db.refresh(record)
        return BacktestOut.model_validate(record)
    except Exception as exc:
        logger.error("Backtest simulation failed: %s", exc, exc_info=True)
        record.status = "failed"
        record.completed_at = datetime.now(timezone.utc)
        record.result_detail = {"error": str(exc)}
        await db.commit()
        await db.refresh(record)
        return BacktestOut.model_validate(record)


@router.get("/{id}", response_model=BacktestOut)
async def get_backtest(
    id: str = Path(...),
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
) -> BacktestOut:
    """Return a backtest run by ID."""
    stmt = select(Backtest).where(Backtest.id == id)
    res = await db.execute(stmt)
    record = res.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return BacktestOut.model_validate(record)
