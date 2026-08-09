"""
Backtesting routes — queue runs and retrieve results.

Backtesting engine is not yet implemented.
All endpoints return HTTP 501 Not Implemented so callers receive a clear,
structured error instead of an unhandled HTTP 500 from NotImplementedError.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.schemas import BacktestOut, BacktestInput

router = APIRouter()

_NOT_IMPLEMENTED = "Backtesting engine is not yet implemented"


@router.get("", response_model=List[BacktestOut])
async def list_backtests(db: AsyncSession = Depends(get_db)) -> List[BacktestOut]:
    """Return all historical backtest runs for the authenticated user."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=_NOT_IMPLEMENTED,
    )


@router.post("", response_model=BacktestOut, status_code=status.HTTP_202_ACCEPTED)
async def create_backtest(
    payload: BacktestInput,
    db: AsyncSession = Depends(get_db),
) -> BacktestOut:
    """
    Queue a new backtest run.
    The run will be executed asynchronously by the Backtesting module worker pool.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=_NOT_IMPLEMENTED,
    )


@router.get("/{id}", response_model=BacktestOut)
async def get_backtest(
    id: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> BacktestOut:
    """Return a backtest run by ID including its result metrics once completed."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=_NOT_IMPLEMENTED,
    )
