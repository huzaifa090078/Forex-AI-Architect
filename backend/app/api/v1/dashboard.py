"""
Dashboard routes — summary KPIs and performance time-series.
Requires authentication.
"""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.schemas import DashboardSummaryOut, PerformancePointOut
from app.services.dashboard_service import get_summary, get_performance
from app.api.v1.auth import get_current_user_id

router = APIRouter()


@router.get("/summary", response_model=DashboardSummaryOut)
async def get_summary_route(
    db:      AsyncSession = Depends(get_db),
    _user_id: str         = Depends(get_current_user_id),
) -> DashboardSummaryOut:
    return await get_summary(db)


@router.get("/performance", response_model=List[PerformancePointOut])
async def get_performance_route(
    period:   str          = Query(default="30d", pattern="^(1d|7d|30d|90d|1y|all)$"),
    db:       AsyncSession = Depends(get_db),
    _user_id: str          = Depends(get_current_user_id),
) -> List[PerformancePointOut]:
    return await get_performance(db, period)
