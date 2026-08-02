"""
News Filter — abstract interface contracts.

The News Filter prevents the bot from opening trades in the minutes
surrounding high-impact economic releases (NFP, CPI, FOMC, etc.).
It also enriches signals with news sentiment scores.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class ImpactLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class NewsEvent:
    """A single economic calendar entry."""
    id: str
    headline: str
    source: str
    impact: ImpactLevel
    currency: str
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    published_at: datetime = field(default_factory=datetime.utcnow)


class INewsProvider(ABC):
    """Abstract source for economic calendar data."""

    @abstractmethod
    async def fetch_upcoming(self, hours: int = 24) -> List[NewsEvent]:
        """Return scheduled events in the next `hours` hours."""
        ...

    @abstractmethod
    async def fetch_recent(self, hours: int = 48) -> List[NewsEvent]:
        """Return events published in the last `hours` hours."""
        ...


class INewsFilter(ABC):
    """
    Evaluate whether trading should be suppressed based on scheduled news.
    Injected into the Trade Manager as a pre-flight guard.
    """

    @abstractmethod
    async def is_trading_allowed(self, pair: str) -> bool:
        """
        Return False if a high-impact event affecting `pair`'s currencies
        is scheduled within the configured suppression window.
        """
        ...

    @abstractmethod
    async def get_upcoming_high_impact(self) -> List[NewsEvent]:
        """Return all high-impact events in the next 24 hours."""
        ...
