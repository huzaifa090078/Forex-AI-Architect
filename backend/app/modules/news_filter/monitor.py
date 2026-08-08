"""
News Filter — NewsMonitor background refresh task (Section 10).

Pattern mirrors TradeMonitor (Section 9): single asyncio Task,
idempotent start/stop, configurable interval, clean shutdown.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.news_filter.filter import ConcreteNewsFilter
from app.modules.news_filter.provider import UnavailableNewsProvider
from app.modules.news_filter.service import NewsService

logger = logging.getLogger(__name__)


class NewsMonitor:
    """
    Background task that periodically:
      1. Calls ConcreteNewsFilter.refresh() to update the in-memory cache.
      2. Persists normalized events to the news_events DB table (upsert).
      3. Updates event statuses (UPCOMING / LIVE / FINISHED) in the DB.

    Single instance — created at module level, wired into main.py lifecycle.
    """

    def __init__(self, news_filter: ConcreteNewsFilter) -> None:
        self._filter:   ConcreteNewsFilter  = news_filter
        self._task:     Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the background refresh loop (idempotent)."""
        if self._task is not None and not self._task.done():
            logger.debug("NewsMonitor: already running — start() ignored")
            return

        # Run one refresh immediately so the cache is warm at startup
        await self._tick()

        self._task = asyncio.create_task(self._loop(), name="news-monitor")
        logger.info("NewsMonitor: started (interval=%ds)", settings.NEWS_REFRESH_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Cancel the background loop and wait for it to finish."""
        if self._task is None or self._task.done():
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        logger.info("NewsMonitor: stopped")

    # ── Internal ─────────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        """Refresh loop — runs until cancelled."""
        try:
            while True:
                await asyncio.sleep(settings.NEWS_REFRESH_INTERVAL_SECONDS)
                await self._tick()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("NewsMonitor: unexpected error — %s", exc)

    async def _tick(self) -> None:
        """One refresh cycle: provider fetch → cache update → DB persist."""
        try:
            # 1. Refresh in-memory cache from provider
            await self._filter.refresh()

            # 2. Persist events to DB and update statuses
            events = self._filter.get_cached_events()
            now    = datetime.now(timezone.utc)

            if events:
                async with AsyncSessionLocal() as db:
                    for event in events:
                        try:
                            await NewsService.upsert_event(db, event)
                        except Exception as ev_exc:
                            logger.warning(
                                "NewsMonitor: could not persist event '%s' — %s",
                                event.event_name, ev_exc,
                            )

                    await NewsService.refresh_statuses(
                        db,
                        now=now,
                        pause_before_minutes=settings.NEWS_PAUSE_BEFORE_MINUTES,
                        resume_after_minutes=settings.NEWS_RESUME_AFTER_MINUTES,
                    )

            logger.debug(
                "NewsMonitor._tick: %d events processed at %s",
                len(events), now.isoformat(),
            )

        except Exception as exc:
            logger.error("NewsMonitor._tick: error — %s", exc)


# ── Module-level singletons (wired in main.py) ────────────────────────────────

_provider      = UnavailableNewsProvider()
news_filter    = ConcreteNewsFilter(_provider)
news_monitor   = NewsMonitor(news_filter)
