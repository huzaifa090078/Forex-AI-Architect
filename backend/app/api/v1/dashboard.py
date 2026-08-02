"""
Dashboard routes — summary KPIs and performance time-series.
"""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.schemas import DashboardSummaryOut, PerformancePointOut

router = APIRouter()


@router.get("/summary", response_model=DashboardSummaryOut)
async def get_summary(db: AsyncSession = Depends(get_db)) -> DashboardSummaryOut:
    """
    Return high-level KPIs: balance, equity, PnL, open trades, win rate, bot status.
    Data is aggregated from the Trade and BotSettings tables and optionally from MT5.
    """
    raise NotImplementedError("dashboard.summary — implement in dashboard service")


@router.get("/performance", response_model=List[PerformancePointOut])
async def get_performance(
    period: str = Query(default="30d", regex="^(1d|7d|30d|90d|1y|all)$"),
    db: AsyncSession = Depends(get_db),
) -> List[PerformancePointOut]:
    """
    Return daily equity curve and PnL series for the given time period.
    Used by the dashboard performance chart.
    """
    raise NotImplementedError("dashboard.performance — implement in dashboard service")
