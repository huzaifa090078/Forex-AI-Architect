"""
News Filter — database service (Section 10).

NewsService provides all CRUD operations for the news_events table.
Duplicate events are prevented via the unique constraint on
(provider, event_name, currency, event_time).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NewsEventRecord
from app.modules.news_filter.interfaces import ImpactLevel, NewsEvent, NewsEventStatus

logger = logging.getLogger(__name__)

# Map domain ImpactLevel → DB string
_IMPACT_TO_STR = {
    ImpactLevel.HIGH:   "high",
    ImpactLevel.MEDIUM: "medium",
    ImpactLevel.LOW:    "low",
}

# Map domain NewsEventStatus → DB string
_STATUS_TO_STR = {
    NewsEventStatus.UPCOMING: "upcoming",
    NewsEventStatus.LIVE:     "live",
    NewsEventStatus.FINISHED: "finished",
}


class NewsService:
    """Static-method CRUD for news_events table — mirrors TradeService pattern."""

    # ── upsert ────────────────────────────────────────────────────────────────

    @staticmethod
    async def upsert_event(db: AsyncSession, event: NewsEvent) -> None:
        """
        Insert or update a news event using the unique identity constraint.
        Never creates duplicates for the same (provider, event_name, currency, event_time).
        """
        now = datetime.now(timezone.utc)
        stmt = (
            pg_insert(NewsEventRecord)
            .values(
                id          = event.id,
                provider    = event.provider,
                event_name  = event.event_name,
                currency    = event.currency.upper(),
                impact      = _IMPACT_TO_STR[event.impact],
                event_time  = event.event_time,
                source      = event.source or "",
                actual      = event.actual,
                forecast    = event.forecast,
                previous    = event.previous,
                status      = "upcoming",
                created_at  = now,
                updated_at  = now,
            )
            .on_conflict_do_update(
                constraint  = "uq_news_event_identity",
                set_={
                    "actual":     event.actual,
                    "forecast":   event.forecast,
                    "previous":   event.previous,
                    "updated_at": now,
                },
            )
        )
        await db.execute(stmt)
        await db.commit()

    # ── status refresh ────────────────────────────────────────────────────────

    @staticmethod
    async def refresh_statuses(
        db: AsyncSession,
        now: datetime,
        pause_before_minutes: int,
        resume_after_minutes: int,
    ) -> None:
        """
        Update the status column for all events relative to ``now``.

        UPCOMING  — event_time is in the future (> now)
        LIVE      — within the [−resume_after, +pause_before] window
        FINISHED  — event_time + resume_after is in the past
        """
        from datetime import timedelta
        from sqlalchemy import text

        before_delta = timedelta(minutes=pause_before_minutes)
        after_delta  = timedelta(minutes=resume_after_minutes)

        window_start = now - after_delta
        window_end   = now + before_delta

        # Mark LIVE (inside the active window)
        await db.execute(
            update(NewsEventRecord)
            .where(
                NewsEventRecord.event_time >= window_start,
                NewsEventRecord.event_time <= window_end,
            )
            .values(status="live", updated_at=now)
        )

        # Mark FINISHED (past the post-event resume window)
        await db.execute(
            update(NewsEventRecord)
            .where(NewsEventRecord.event_time < window_start)
            .values(status="finished", updated_at=now)
        )

        # Mark UPCOMING (before the pre-event pause window)
        await db.execute(
            update(NewsEventRecord)
            .where(NewsEventRecord.event_time > window_end)
            .values(status="upcoming", updated_at=now)
        )

        await db.commit()

    # ── queries ───────────────────────────────────────────────────────────────

    @staticmethod
    async def get_upcoming(
        db: AsyncSession,
        *,
        impact: Optional[str] = None,
        currency: Optional[str] = None,
        hours: int = 24,
    ) -> List[NewsEventRecord]:
        """Return events with status='upcoming', optionally filtered."""
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) + timedelta(hours=hours)
        q = (
            select(NewsEventRecord)
            .where(
                NewsEventRecord.event_time <= cutoff,
                NewsEventRecord.status == "upcoming",
            )
            .order_by(NewsEventRecord.event_time)
        )
        if impact and impact != "all":
            q = q.where(NewsEventRecord.impact == impact.lower())
        if currency:
            q = q.where(NewsEventRecord.currency == currency.upper())

        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def get_all_relevant(
        db: AsyncSession,
        *,
        impact: Optional[str] = None,
        currency: Optional[str] = None,
    ) -> List[NewsEventRecord]:
        """Return upcoming + live events (not finished), ordered by event_time."""
        q = (
            select(NewsEventRecord)
            .where(NewsEventRecord.status.in_(["upcoming", "live"]))
            .order_by(NewsEventRecord.event_time)
        )
        if impact and impact != "all":
            q = q.where(NewsEventRecord.impact == impact.lower())
        if currency:
            q = q.where(NewsEventRecord.currency == currency.upper())

        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def record_to_domain(record: NewsEventRecord) -> NewsEvent:
        """Convert ORM record → domain NewsEvent."""
        impact_map = {"high": ImpactLevel.HIGH, "medium": ImpactLevel.MEDIUM, "low": ImpactLevel.LOW}
        return NewsEvent(
            id         = record.id,
            event_name = record.event_name,
            currency   = record.currency,
            impact     = impact_map.get(record.impact, ImpactLevel.LOW),
            event_time = record.event_time,
            source     = record.source or "",
            actual     = record.actual,
            forecast   = record.forecast,
            previous   = record.previous,
            provider   = record.provider,
        )
