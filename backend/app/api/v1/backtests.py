"""
Backtesting routes — queue runs and retrieve results.
"""

from typing import List

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.schemas import BacktestOut, BacktestInput

router = APIRouter()


@router.get("", response_model=List[BacktestOut])
async def list_backtests(db: AsyncSession = Depends(get_db)) -> List[BacktestOut]:
    """Return all historical backtest runs for the authenticated user."""
    raise NotImplementedError("backtests.list — implement in backtest service")


@router.post("", response_model=BacktestOut, status_code=status.HTTP_202_ACCEPTED)
async def create_backtest(
    payload: BacktestInput,
    db: AsyncSession = Depends(get_db),
) -> BacktestOut:
    """
    Queue a new backtest run.
    The run is executed asynchronously by the Backtesting module worker pool.
    Returns immediately with status=queued.
    """
    raise NotImplementedError("backtests.create — implement in backtest service")


@router.get("/{id}", response_model=BacktestOut)
async def get_backtest(
    id: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> BacktestOut:
    """Return a backtest run by ID including its result metrics once completed."""
    raise NotImplementedError("backtests.get — implement in backtest service")
