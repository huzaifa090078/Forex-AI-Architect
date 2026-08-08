# News Filter — Section 10: economic calendar event detection and trading suppression

from app.modules.news_filter.interfaces import (
    ImpactLevel,
    NewsBlockReason,
    NewsEvent,
    NewsEventStatus,
    INewsFilter,
    INewsProvider,
    PairNewsStatus,
)
from app.modules.news_filter.provider import UnavailableNewsProvider
from app.modules.news_filter.filter import ConcreteNewsFilter
from app.modules.news_filter.monitor import news_filter, news_monitor
from app.modules.news_filter.service import NewsService

__all__ = [
    # Enums
    "ImpactLevel",
    "NewsBlockReason",
    "NewsEventStatus",
    # Domain objects
    "NewsEvent",
    "PairNewsStatus",
    # Interfaces
    "INewsFilter",
    "INewsProvider",
    # Implementations
    "UnavailableNewsProvider",
    "ConcreteNewsFilter",
    "NewsService",
    # Module-level singletons
    "news_filter",
    "news_monitor",
]
