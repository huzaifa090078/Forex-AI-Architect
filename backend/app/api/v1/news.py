"""
News Filter routes — Section 10 full implementation.

Endpoints:
  GET  /v1/news              — all relevant events (upcoming + live), filterable
  GET  /v1/news/upcoming     — high-impact events in next 24 h
  GET  /v1/news/status       — system health + config snapshot
  GET  /v1/news/pair/{pair}  — trading safety status for a specific pair
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.db.models import NewsEventRecord
from app.db.schemas import (
    NewsEventOut,
    NewsSystemStatusOut,
    PairNewsStatusOut,
)
from app.modules.news_filter.monitor import news_filter
from app.modules.news_filter.service import NewsService

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SUPPORTED_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD",
    "USDCAD", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP",
]


def _minutes_to(event_time: datetime, now: datetime) -> Optional[float]:
    delta = (event_time - now).total_seconds() / 60.0
    return round(delta, 2) if delta >= 0 else None


def _record_to_out(record: NewsEventRecord, now: datetime) -> NewsEventOut:
    """Convert ORM record → API response schema, adding computed fields."""
    # Affected pairs derived deterministically from currency
    currency = record.currency.upper()
    affected = [
        p for p in _SUPPORTED_PAIRS
        if currency in (p[:3].upper(), p[3:6].upper())
    ]
    return NewsEventOut(
        id               = record.id,
        provider         = record.provider,
        event_name       = record.event_name,
        currency         = record.currency,
        impact           = record.impact,
        event_time       = record.event_time,
        source           = record.source,
        actual           = record.actual,
        forecast         = record.forecast,
        previous         = record.previous,
        status           = record.status,
        affected_pairs   = affected,
        minutes_to_event = _minutes_to(record.event_time, now),
    )


# ---------------------------------------------------------------------------
# GET /v1/news
# ---------------------------------------------------------------------------

@router.get("", response_model=List[NewsEventOut])
async def list_news(
    impact:   str           = Query(default="all", pattern="^(low|medium|high|all)$"),
    currency: Optional[str] = Query(default=None, description="ISO currency code, e.g. USD"),
    db:       AsyncSession  = Depends(get_db),
) -> List[NewsEventOut]:
    """
    Return upcoming and live economic events.

    Optionally filter by impact level (low / medium / high / all) and/or currency.
    Does NOT return finished events — use Trade History for those.
    Does NOT expose provider API keys or credentials.
    """
    records = await NewsService.get_all_relevant(
        db, impact=impact if impact != "all" else None, currency=currency
    )
    now = datetime.now(timezone.utc)
    return [_record_to_out(r, now) for r in records]


# ---------------------------------------------------------------------------
# GET /v1/news/upcoming
# ---------------------------------------------------------------------------

@router.get("/upcoming", response_model=List[NewsEventOut])
async def upcoming_news(
    hours: int = Query(default=24, ge=1, le=168),
    db:    AsyncSession = Depends(get_db),
) -> List[NewsEventOut]:
    """
    Return HIGH-impact events scheduled in the next ``hours`` hours (default 24).
    Used by the dashboard to show the upcoming news panel.
    """
    records = await NewsService.get_upcoming(db, impact="high", hours=hours)
    now = datetime.now(timezone.utc)
    return [_record_to_out(r, now) for r in records]


# ---------------------------------------------------------------------------
# GET /v1/news/status
# ---------------------------------------------------------------------------

@router.get("/status", response_model=NewsSystemStatusOut)
async def news_status() -> NewsSystemStatusOut:
    """
    Return the current News Filter system health and configuration snapshot.

    Exposes: provider availability, last refresh timestamp, config values,
    cached event count.  Never exposes API keys or secrets.
    """
    cached = news_filter.get_cached_events()
    high_count = sum(1 for e in cached if e.impact.value == "high")

    return NewsSystemStatusOut(
        provider_available    = news_filter.provider_available,
        last_refresh          = news_filter.last_refresh,
        filter_enabled        = settings.NEWS_FILTER_ENABLED,
        high_impact_enabled   = settings.NEWS_HIGH_IMPACT_ENABLED,
        medium_impact_enabled = settings.NEWS_MEDIUM_IMPACT_ENABLED,
        low_impact_enabled    = settings.NEWS_LOW_IMPACT_ENABLED,
        pause_before_minutes  = settings.NEWS_PAUSE_BEFORE_MINUTES,
        resume_after_minutes  = settings.NEWS_RESUME_AFTER_MINUTES,
        cached_event_count    = len(cached),
        high_impact_count     = high_count,
    )


# ---------------------------------------------------------------------------
# GET /v1/news/pair/{pair}
# ---------------------------------------------------------------------------

@router.get("/pair/{pair}", response_model=PairNewsStatusOut)
async def pair_news_status(
    pair: str = Path(..., description="Forex pair symbol e.g. EURUSD"),
) -> PairNewsStatusOut:
    """
    Return the trading safety status for a specific forex pair right now.

    Evaluates the in-memory cache synchronously — no provider call.
    Distinguishes:
      • NO_RELEVANT_NEWS           — no event for this pair's currencies
      • *_IMPACT_NEWS_WINDOW       — trading suppressed
      • NEWS_PROVIDER_UNAVAILABLE  — provider is down

    Never exposes API keys or provider secrets.
    """
    pair_upper = pair.upper().replace("/", "").replace("_", "")
    if len(pair_upper) < 6:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid pair symbol: '{pair}'. Expected 6-char symbol like EURUSD.",
        )

    now = datetime.now(timezone.utc)
    result = news_filter.evaluate_pair(pair_upper, now)

    return PairNewsStatusOut(
        pair             = result.pair,
        affected         = result.affected,
        blocked          = result.blocked,
        reason           = result.reason.value,
        impact           = result.impact.value if result.impact else None,
        event_name       = result.event_name,
        event_time       = result.event_time,
        minutes_to_event = result.minutes_to_event,
        status           = result.status.value if result.status else None,
        provider_ok      = result.provider_ok,
    )
