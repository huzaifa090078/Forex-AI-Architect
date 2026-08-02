"""
News Filter — base implementation scaffold.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List

from app.modules.news_filter.interfaces import INewsFilter, INewsProvider, NewsEvent, ImpactLevel
from app.core.config import settings

logger = logging.getLogger(__name__)


class BaseNewsFilter(INewsFilter):
    """
    Suppresses trading within NEWS_HIGH_IMPACT_BLOCK_MINUTES of high-impact events
    for any currency in the pair being traded.
    """

    def __init__(self, provider: INewsProvider) -> None:
        self._provider = provider

    async def is_trading_allowed(self, pair: str) -> bool:
        if not settings.NEWS_FILTER_ENABLED:
            return True
        currencies = self._extract_currencies(pair)
        upcoming = await self._provider.fetch_upcoming(hours=24)
        now = datetime.now(timezone.utc)
        window = timedelta(minutes=settings.NEWS_HIGH_IMPACT_BLOCK_MINUTES)
        for event in upcoming:
            if event.impact != ImpactLevel.HIGH:
                continue
            if event.currency not in currencies:
                continue
            if abs((event.published_at - now).total_seconds()) <= window.total_seconds():
                logger.info(
                    "NewsFilter: trading suppressed for %s — event '%s' in window",
                    pair, event.headline,
                )
                return False
        return True

    async def get_upcoming_high_impact(self) -> List[NewsEvent]:
        events = await self._provider.fetch_upcoming(hours=24)
        return [e for e in events if e.impact == ImpactLevel.HIGH]

    @staticmethod
    def _extract_currencies(pair: str) -> List[str]:
        """Extract base and quote currencies from a pair symbol (e.g. 'EURUSD' → ['EUR', 'USD'])."""
        pair = pair.replace("/", "").replace("_", "").upper()
        if len(pair) >= 6:
            return [pair[:3], pair[3:6]]
        return [pair]
