"""
Trade management routes — CRUD operations and aggregate statistics.
"""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.schemas import (
    TradeOut,
    TradeInput,
    TradeUpdate,
    TradeStatsOut,
    PaginatedTradesOut,
)

router = APIRouter()


@router.get("", response_model=PaginatedTradesOut)
async def list_trades(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    status_filter: str = Query(default="all", alias="status"),
    pair: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> PaginatedTradesOut:
    """Return paginated trade records with optional filters."""
    raise NotImplementedError("trades.list — implement in trade service")


@router.get("/stats", response_model=TradeStatsOut)
async def get_stats(db: AsyncSession = Depends(get_db)) -> TradeStatsOut:
    """
    Return aggregate trade statistics: win rate, profit factor, max drawdown, etc.
    Calculated across all closed trades for the authenticated user.
    """
    raise NotImplementedError("trades.stats — implement in trade service")


@router.get("/{id}", response_model=TradeOut)
async def get_trade(
    id: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> TradeOut:
    """Return a single trade by its UUID."""
    raise NotImplementedError("trades.get — implement in trade service")


@router.post("", response_model=TradeOut, status_code=status.HTTP_201_CREATED)
async def create_trade(
    payload: TradeInput,
    db: AsyncSession = Depends(get_db),
) -> TradeOut:
    """
    Record a new manual trade.
    The Risk Manager validates the position before persisting.
    """
    raise NotImplementedError("trades.create — implement in trade service")


@router.patch("/{id}", response_model=TradeOut)
async def update_trade(
    payload: TradeUpdate,
    id: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> TradeOut:
    """Update SL, TP, notes, or close/cancel an existing trade."""
    raise NotImplementedError("trades.update — implement in trade service")


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trade(
    id: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Cancel and delete a trade record. Only allowed for non-executed trades."""
    raise NotImplementedError("trades.delete — implement in trade service")
