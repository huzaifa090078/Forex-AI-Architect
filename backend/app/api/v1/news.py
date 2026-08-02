"""
News Filter routes — economic calendar and high-impact event feed.
"""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.schemas import NewsItemOut

router = APIRouter()


@router.get("", response_model=List[NewsItemOut])
async def list_news(
    impact: str = Query(default="all", regex="^(low|medium|high|all)$"),
    currency: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> List[NewsItemOut]:
    """
    Return economic calendar events from the News Filter module.
    Optionally filtered by impact level and/or currency.
    """
    raise NotImplementedError("news.list — implement in news filter service")


@router.get("/upcoming", response_model=List[NewsItemOut])
async def upcoming(db: AsyncSession = Depends(get_db)) -> List[NewsItemOut]:
    """
    Return high-impact events scheduled in the next 24 hours.
    Used by the bot to suppress trading before major releases.
    """
    raise NotImplementedError("news.upcoming — implement in news filter service")
