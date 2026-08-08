"""
News Filter — ConcreteNewsFilter (Section 10 full implementation).

Responsibilities:
  • Cache economic events from the provider (refreshed by NewsMonitor).
  • evaluate_pair() — fast synchronous Risk Manager integration.
  • get_affected_pairs() — deterministic pair-impact mapping.
  • is_trading_allowed() — backward-compat method for Risk Manager hook.
  • Alert state tracking: emit TRADING_PAUSED / TRADING_RESUMED on transitions.
  • Distinguish NO_NEWS from NEWS_PROVIDER_UNAVAILABLE.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.core.config import settings
from app.modules.news_filter.interfaces import (
    ImpactLevel,
    INewsFilter,
    INewsProvider,
    NewsBlockReason,
    NewsEvent,
    NewsEventStatus,
    PairNewsStatus,
)

logger = logging.getLogger(__name__)

# Supported forex pairs — used for affected-pair calculation.
# Derived from the project's canonical pair list (Section 3/4).
_SUPPORTED_PAIRS: List[str] = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD",
    "USDCAD", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP",
]


def _extract_currencies(pair: str) -> List[str]:
    """Return [base, quote] from a forex pair symbol."""
    clean = pair.replace("/", "").replace("_", "").replace(" ", "").upper()
    if len(clean) >= 6:
        return [clean[:3], clean[3:6]]
    return [clean]


def _impact_enabled(impact: ImpactLevel) -> bool:
    """Check if this impact level is enabled in config."""
    if impact == ImpactLevel.HIGH:
        return settings.NEWS_HIGH_IMPACT_ENABLED
    if impact == ImpactLevel.MEDIUM:
        return settings.NEWS_MEDIUM_IMPACT_ENABLED
    if impact == ImpactLevel.LOW:
        return settings.NEWS_LOW_IMPACT_ENABLED
    return False


def _impact_reason(impact: ImpactLevel) -> NewsBlockReason:
    if impact == ImpactLevel.HIGH:
        return NewsBlockReason.HIGH_IMPACT_NEWS_WINDOW
    if impact == ImpactLevel.MEDIUM:
        return NewsBlockReason.MEDIUM_IMPACT_NEWS_WINDOW
    return NewsBlockReason.LOW_IMPACT_NEWS_WINDOW


class ConcreteNewsFilter(INewsFilter):
    """
    Production News Filter Engine.

    Thread-safe for read access to _cached_events (replaced atomically).
    Write access (cache refresh) is performed by NewsMonitor in a single
    background asyncio Task.
    """

    def __init__(self, provider: INewsProvider) -> None:
        self._provider:        INewsProvider       = provider
        self._cached_events:   List[NewsEvent]     = []
        self._provider_ok:     bool                = provider.is_available
        self._last_refresh:    Optional[datetime]  = None

        # Alert state: pair → was_blocked last evaluation.
        # Used to detect TRADING_PAUSED / TRADING_RESUMED transitions.
        self._last_blocked:    Dict[str, bool]     = {}

    # ── INewsFilter.provider_available ───────────────────────────────────────

    @property
    def provider_available(self) -> bool:
        return self._provider_ok

    @property
    def last_refresh(self) -> Optional[datetime]:
        return self._last_refresh

    # ── Cache refresh (called by NewsMonitor) ─────────────────────────────────

    async def refresh(self) -> None:
        """
        Fetch upcoming events from the provider and update the in-memory cache.
        Handles provider failures gracefully — cache is cleared, flag set.
        Called exclusively by NewsMonitor; never by Risk Manager hot-path.
        """
        if not self._provider.is_available:
            self._provider_ok   = False
            self._cached_events = []
            logger.debug("NewsFilter.refresh: provider unavailable — cache empty")
            return

        try:
            events = await self._provider.fetch_upcoming(hours=48)
            # Sanitize external strings
            safe: List[NewsEvent] = []
            for ev in events:
                try:
                    # Ensure event_time is timezone-aware UTC
                    et = ev.event_time
                    if et.tzinfo is None:
                        from datetime import timezone as _tz
                        et = et.replace(tzinfo=_tz.utc)
                    safe.append(NewsEvent(
                        id         = str(ev.id)[:64],
                        event_name = str(ev.event_name)[:255],
                        currency   = str(ev.currency).upper()[:10],
                        impact     = ev.impact,
                        event_time = et,
                        source     = str(ev.source or "")[:100],
                        actual     = ev.actual,
                        forecast   = ev.forecast,
                        previous   = ev.previous,
                        provider   = str(ev.provider or "unknown")[:50],
                    ))
                except Exception as ev_exc:
                    logger.warning("NewsFilter.refresh: malformed event skipped — %s", ev_exc)

            self._cached_events = safe
            self._provider_ok   = True
            self._last_refresh  = datetime.now(timezone.utc)
            logger.info("NewsFilter.refresh: cached %d events", len(safe))

        except Exception as exc:
            logger.error("NewsFilter.refresh: provider error — %s", exc)
            self._provider_ok   = False
            self._cached_events = []

    # ── INewsFilter.evaluate_pair ─────────────────────────────────────────────

    def evaluate_pair(self, pair: str, now: datetime) -> PairNewsStatus:
        """
        Synchronous deterministic evaluation against the in-memory cache.

        Returns PairNewsStatus — never raises.
        Distinguishes:
          • NO_NEWS              — cache has no relevant event for this pair
          • *_IMPACT_NEWS_WINDOW — within the block window
          • NEWS_PROVIDER_UNAVAILABLE — provider is down and filter is enabled
        """
        if not settings.NEWS_FILTER_ENABLED:
            return PairNewsStatus(
                pair=pair, affected=False, blocked=False,
                reason=NewsBlockReason.NO_RELEVANT_NEWS,
                provider_ok=True,
            )

        if not self._provider_ok:
            return PairNewsStatus(
                pair=pair, affected=False, blocked=False,
                reason=NewsBlockReason.NEWS_PROVIDER_UNAVAILABLE,
                provider_ok=False,
            )

        currencies = _extract_currencies(pair)
        before_min = settings.NEWS_PAUSE_BEFORE_MINUTES
        after_min  = settings.NEWS_RESUME_AFTER_MINUTES

        # Ensure now is tz-aware
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # Sort by event_time so we check the most imminent event first
        relevant = sorted(
            (ev for ev in self._cached_events if ev.currency.upper() in currencies),
            key=lambda e: abs((e.event_time - now).total_seconds()),
        )

        if not relevant:
            return PairNewsStatus(
                pair=pair, affected=False, blocked=False,
                reason=NewsBlockReason.NO_RELEVANT_NEWS,
                provider_ok=True,
            )

        # Among relevant events, find the one that causes a block (if any)
        for event in relevant:
            if not _impact_enabled(event.impact):
                continue

            delta_minutes = (event.event_time - now).total_seconds() / 60.0

            # Determine event status
            if delta_minutes > before_min:
                ev_status = NewsEventStatus.UPCOMING   # too far ahead — not yet blocking
                continue
            elif delta_minutes >= -after_min:
                # Within the block window: either upcoming-close or live
                ev_status = (
                    NewsEventStatus.UPCOMING if delta_minutes > 0
                    else NewsEventStatus.LIVE
                )
                minutes_to = delta_minutes if delta_minutes >= 0 else None

                return PairNewsStatus(
                    pair             = pair,
                    affected         = True,
                    blocked          = True,
                    reason           = _impact_reason(event.impact),
                    impact           = event.impact,
                    event_name       = event.event_name,
                    event_time       = event.event_time,
                    minutes_to_event = minutes_to,
                    status           = ev_status,
                    provider_ok      = True,
                )
            else:
                # delta_minutes < -after_min → finished, skip
                continue

        # All relevant events are either too far ahead or finished
        return PairNewsStatus(
            pair=pair, affected=True, blocked=False,
            reason=NewsBlockReason.NO_RELEVANT_NEWS,
            provider_ok=True,
        )

    # ── INewsFilter.get_affected_pairs ────────────────────────────────────────

    def get_affected_pairs(
        self,
        event: NewsEvent,
        all_pairs: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Return pairs (from all_pairs or the canonical list) whose base or
        quote currency matches the event's currency.  No duplicates.
        """
        pairs = all_pairs if all_pairs is not None else _SUPPORTED_PAIRS
        currency = event.currency.upper()
        seen: set = set()
        result: List[str] = []
        for pair in pairs:
            if pair in seen:
                continue
            currencies = _extract_currencies(pair)
            if currency in currencies:
                result.append(pair)
                seen.add(pair)
        return result

    # ── INewsFilter.is_trading_allowed (Risk Manager hot-path) ───────────────

    async def is_trading_allowed(self, pair: str) -> bool:
        """
        Return False when trading is suppressed for this pair.

        Wraps evaluate_pair() for async compatibility with the existing
        Risk Manager integration.  Never raises.
        """
        now = datetime.now(timezone.utc)
        status = self.evaluate_pair(pair, now)

        # Detect state transition for alerts
        was_blocked = self._last_blocked.get(pair, False)
        if status.blocked and not was_blocked:
            logger.warning(
                "NewsFilter [TRADING_PAUSED] %s — %s: %s (%.1f min)",
                pair,
                status.reason.value,
                status.event_name or "",
                status.minutes_to_event or 0.0,
            )
        elif not status.blocked and was_blocked:
            logger.info("NewsFilter [TRADING_RESUMED] %s", pair)

        self._last_blocked[pair] = status.blocked
        return not status.blocked

    # ── INewsFilter.get_upcoming_high_impact ──────────────────────────────────

    async def get_upcoming_high_impact(self) -> List[NewsEvent]:
        """Return all HIGH-impact events from the cache (no DB call)."""
        return [e for e in self._cached_events if e.impact == ImpactLevel.HIGH]

    # ── Public cache accessor ─────────────────────────────────────────────────

    def get_cached_events(self) -> List[NewsEvent]:
        """Return all currently cached events (copy-on-access, read-only)."""
        return list(self._cached_events)
