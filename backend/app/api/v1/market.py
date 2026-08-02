"""
Market Scanner routes — live pair quotes and opportunity scanning.
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.schemas import MarketPairOut, MarketOpportunityOut

router = APIRouter()


@router.get("/pairs", response_model=List[MarketPairOut])
async def get_pairs(db: AsyncSession = Depends(get_db)) -> List[MarketPairOut]:
    """
    Return current bid/ask, spread, 24h change, volatility, and trend direction
    for every pair in the bot's allowed-pairs list.
    Data sourced from the configured market data provider (MT5 or yfinance).
    """
    raise NotImplementedError("market.pairs — implement in market scanner service")


@router.get("/scan", response_model=List[MarketOpportunityOut])
async def scan(db: AsyncSession = Depends(get_db)) -> List[MarketOpportunityOut]:
    """
    Trigger the Market Scanner module on demand and return the current opportunity list.
    In production, scanning runs on a scheduled interval; this endpoint exposes
    the last computed results synchronously.
    """
    raise NotImplementedError("market.scan — implement in market scanner service")
