"""
News Filter — abstract interface contracts (Section 10).

The News Filter prevents the bot from opening trades during high-impact
economic releases (NFP, CPI, FOMC, etc.) and provides structured news
information to the Risk Manager and Dashboard.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


# ─── Enums ────────────────────────────────────────────────────────────────────

class ImpactLevel(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


class NewsEventStatus(str, Enum):
    UPCOMING = "upcoming"   # event has not yet occurred
    LIVE     = "live"       # inside the event window (pre OR post buffer)
    FINISHED = "finished"   # event + post-news resume window have elapsed


class NewsBlockReason(str, Enum):
    NO_RELEVANT_NEWS          = "NO_RELEVANT_NEWS"
    HIGH_IMPACT_NEWS_WINDOW   = "HIGH_IMPACT_NEWS_WINDOW"
    MEDIUM_IMPACT_NEWS_WINDOW = "MEDIUM_IMPACT_NEWS_WINDOW"
    LOW_IMPACT_NEWS_WINDOW    = "LOW_IMPACT_NEWS_WINDOW"
    NEWS_PROVIDER_UNAVAILABLE = "NEWS_PROVIDER_UNAVAILABLE"


# ─── Domain objects ───────────────────────────────────────────────────────────

@dataclass
class NewsEvent:
    """
    Normalised economic calendar event.

    ``event_name`` is the canonical name used for duplicate detection.
    ``event_time`` is always timezone-aware UTC.
    ``published_at`` kept for backward compat with the old interface.
    """
    id:           str
    event_name:   str                    # e.g. "Non-Farm Payrolls"
    currency:     str                    # ISO 4217, e.g. "USD"
    impact:       ImpactLevel
    event_time:   datetime               # timezone-aware UTC
    source:       str    = ""
    actual:       Optional[str] = None
    forecast:     Optional[str] = None
    previous:     Optional[str] = None
    provider:     str    = "unavailable"

    # Legacy alias so old code using .headline / .published_at still works
    @property
    def headline(self) -> str:
        return self.event_name

    @property
    def published_at(self) -> datetime:
        return self.event_time


@dataclass
class PairNewsStatus:
    """
    Result of evaluate_pair() — deterministic, based on the current cache.

    ``blocked``           — True  → Risk Manager should reject trade for this pair.
    ``provider_ok``       — False → provider unavailable; reason = NEWS_PROVIDER_UNAVAILABLE.
    ``minutes_to_event``  — None for FINISHED events.
    """
    pair:             str
    affected:         bool                           # pair's currencies matched ≥1 event
    blocked:          bool                           # trading suppressed right now
    reason:           NewsBlockReason
    impact:           Optional[ImpactLevel]  = None
    event_name:       Optional[str]          = None
    event_time:       Optional[datetime]     = None
    minutes_to_event: Optional[float]        = None  # positive = upcoming, None = finished
    status:           Optional[NewsEventStatus] = None
    provider_ok:      bool                   = True  # False when data is unavailable


# ─── Abstractions ─────────────────────────────────────────────────────────────

class INewsProvider(ABC):
    """Abstract source for economic-calendar data."""

    @property
    def is_available(self) -> bool:
        """Override to False for the UnavailableNewsProvider."""
        return True

    @abstractmethod
    async def fetch_upcoming(self, hours: int = 24) -> List[NewsEvent]:
        """Return events scheduled in the next ``hours`` hours."""
        ...

    @abstractmethod
    async def fetch_recent(self, hours: int = 48) -> List[NewsEvent]:
        """Return events that occurred in the last ``hours`` hours."""
        ...


class INewsFilter(ABC):
    """
    Evaluate whether trading should be suppressed based on scheduled news.
    Injected into the Risk Manager as a pre-flight guard.

    Concrete implementations must distinguish
      ``NO NEWS``  from  ``NEWS DATA UNAVAILABLE``.
    """

    @abstractmethod
    async def is_trading_allowed(self, pair: str) -> bool:
        """
        Return False if a configured-impact event affecting ``pair``'s currencies
        is within the configured suppression window.
        """
        ...

    @abstractmethod
    async def get_upcoming_high_impact(self) -> List[NewsEvent]:
        """Return all HIGH-impact events in the next 24 hours."""
        ...

    @abstractmethod
    def evaluate_pair(self, pair: str, now: datetime) -> PairNewsStatus:
        """
        Synchronous deterministic evaluation against the cached event list.

        Designed for fast Risk Manager integration — no DB or HTTP call.
        Always returns a PairNewsStatus; never raises.
        """
        ...

    @abstractmethod
    def get_affected_pairs(self, event: NewsEvent, all_pairs: List[str]) -> List[str]:
        """
        Return the subset of ``all_pairs`` whose base or quote currency
        matches the event's currency.  No duplicates.
        """
        ...

    @property
    @abstractmethod
    def provider_available(self) -> bool:
        """True when the backing provider reported no error on last refresh."""
        ...

    @property
    @abstractmethod
    def last_refresh(self) -> Optional[datetime]:
        """UTC timestamp of the last successful provider refresh, or None."""
        ...
