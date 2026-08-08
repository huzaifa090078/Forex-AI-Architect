"""
News Filter — provider implementations (Section 10).

UnavailableNewsProvider: safe no-op used when NEWS_API_KEY is not configured.
No events are fabricated; the filter knows the provider is unavailable.
"""

import logging
from typing import List

from app.modules.news_filter.interfaces import INewsProvider, NewsEvent

logger = logging.getLogger(__name__)


class UnavailableNewsProvider(INewsProvider):
    """
    Safe no-op provider used when no real economic-calendar source is configured.

    Returns empty lists — never fabricates events.
    The ConcreteNewsFilter detects ``is_available=False`` and sets
    PairNewsStatus.reason = NEWS_PROVIDER_UNAVAILABLE when NEWS_FILTER_ENABLED.
    """

    @property
    def is_available(self) -> bool:
        return False

    async def fetch_upcoming(self, hours: int = 24) -> List[NewsEvent]:
        logger.debug("UnavailableNewsProvider: no provider configured — returning empty event list")
        return []

    async def fetch_recent(self, hours: int = 48) -> List[NewsEvent]:
        logger.debug("UnavailableNewsProvider: no provider configured — returning empty event list")
        return []
