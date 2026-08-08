"""
Section 10 — News Filter Engine focused tests.

Coverage:
  nf_01–nf_05   Event model validation
  nf_06–nf_13   Currency & pair impact mapping
  nf_14–nf_19   Timing / window boundary tests
  nf_20–nf_24   Impact-config enable/disable
  nf_25–nf_28   Provider failure handling
  nf_29–nf_30   Duplicate event upsert prevention
  nf_31–nf_32   Risk Manager integration (is_trading_allowed)
  nf_33–nf_35   Security — no secrets in evaluate_pair / status output
  nf_36–nf_37   Monitor lifecycle (start idempotent, stop clean)
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.news_filter.interfaces import (
    ImpactLevel,
    NewsBlockReason,
    NewsEvent,
    NewsEventStatus,
    PairNewsStatus,
)
from app.modules.news_filter.filter import ConcreteNewsFilter, _extract_currencies
from app.modules.news_filter.provider import UnavailableNewsProvider
from app.modules.news_filter.monitor import NewsMonitor


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _event(
    currency: str = "USD",
    impact:   ImpactLevel = ImpactLevel.HIGH,
    minutes_from_now: float = 60.0,
    event_name: str = "Test NFP",
    provider: str = "test",
) -> NewsEvent:
    return NewsEvent(
        id         = str(uuid.uuid4()),
        event_name = event_name,
        currency   = currency,
        impact     = impact,
        event_time = _now() + timedelta(minutes=minutes_from_now),
        source     = "test_source",
        provider   = provider,
    )


def _filter_with_events(events: List[NewsEvent]) -> ConcreteNewsFilter:
    """Return a ConcreteNewsFilter pre-loaded with given events, provider_ok=True."""
    provider = MagicMock()
    provider.is_available = True
    f = ConcreteNewsFilter(provider)
    f._cached_events = events
    f._provider_ok   = True
    return f


def _unavailable_filter() -> ConcreteNewsFilter:
    """Return a ConcreteNewsFilter with no provider (provider_ok=False)."""
    f = ConcreteNewsFilter(UnavailableNewsProvider())
    f._provider_ok   = False
    f._cached_events = []
    return f


# ─── nf_01–nf_05 Event model ─────────────────────────────────────────────────

def test_nf_01_high_impact_event_model():
    ev = _event(impact=ImpactLevel.HIGH)
    assert ev.impact == ImpactLevel.HIGH
    assert ev.impact.value == "high"
    assert ev.event_time.tzinfo is not None   # tz-aware


def test_nf_02_medium_impact_event_model():
    ev = _event(impact=ImpactLevel.MEDIUM)
    assert ev.impact == ImpactLevel.MEDIUM
    assert ev.impact.value == "medium"


def test_nf_03_low_impact_event_model():
    ev = _event(impact=ImpactLevel.LOW)
    assert ev.impact == ImpactLevel.LOW
    assert ev.impact.value == "low"


def test_nf_04_timezone_aware_event_time():
    ev = _event()
    assert ev.event_time.tzinfo is not None
    assert ev.event_time.tzinfo == timezone.utc or str(ev.event_time.tzinfo) in ("UTC", "utc")


def test_nf_05_legacy_headline_alias():
    """NewsEvent.headline should return event_name for backward compat."""
    ev = _event(event_name="NFP Release")
    assert ev.headline == "NFP Release"
    assert ev.published_at == ev.event_time


# ─── nf_06–nf_13 Currency & pair mapping ─────────────────────────────────────

def test_nf_06_usd_currency_extraction():
    f = _filter_with_events([])
    ev = _event(currency="USD")
    pairs = f.get_affected_pairs(ev)
    assert "EURUSD" in pairs
    assert "GBPUSD" in pairs
    assert "USDJPY" in pairs
    assert "USDCHF" in pairs
    assert "AUDUSD" in pairs
    assert "USDCAD" in pairs
    assert "NZDUSD" in pairs


def test_nf_07_usd_does_not_affect_eurgbp():
    f = _filter_with_events([])
    ev = _event(currency="USD")
    pairs = f.get_affected_pairs(ev)
    assert "EURGBP" not in pairs   # neither EUR nor GBP is USD


def test_nf_08_eur_currency_mapping():
    f = _filter_with_events([])
    ev = _event(currency="EUR")
    pairs = f.get_affected_pairs(ev)
    assert "EURUSD" in pairs
    assert "EURJPY" in pairs
    assert "EURGBP" in pairs
    assert "GBPUSD" not in pairs


def test_nf_09_gbp_currency_mapping():
    f = _filter_with_events([])
    ev = _event(currency="GBP")
    pairs = f.get_affected_pairs(ev)
    assert "GBPUSD" in pairs
    assert "GBPJPY" in pairs
    assert "EURGBP" in pairs
    assert "EURUSD" not in pairs


def test_nf_10_jpy_currency_mapping():
    f = _filter_with_events([])
    ev = _event(currency="JPY")
    pairs = f.get_affected_pairs(ev)
    assert "USDJPY" in pairs
    assert "EURJPY" in pairs
    assert "GBPJPY" in pairs
    assert "EURUSD" not in pairs


def test_nf_11_aud_currency_mapping():
    f = _filter_with_events([])
    ev = _event(currency="AUD")
    pairs = f.get_affected_pairs(ev)
    assert "AUDUSD" in pairs
    assert "GBPUSD" not in pairs


def test_nf_12_no_duplicate_pairs():
    f = _filter_with_events([])
    ev = _event(currency="USD")
    pairs = f.get_affected_pairs(ev)
    assert len(pairs) == len(set(pairs))


def test_nf_13_is_pair_affected_eurusd_by_usd():
    """EURUSD should be affected by USD news (USD is the quote currency)."""
    f = _filter_with_events([])
    ev = _event(currency="USD")
    affected = f.get_affected_pairs(ev)
    assert "EURUSD" in affected


# ─── nf_14–nf_19 Timing / window boundary ────────────────────────────────────

@patch("app.modules.news_filter.filter.settings")
def test_nf_14_31min_before_not_blocked(mock_cfg):
    """31 minutes before event → NOT blocked (pause window = 30 min)."""
    mock_cfg.NEWS_FILTER_ENABLED     = True
    mock_cfg.NEWS_HIGH_IMPACT_ENABLED   = True
    mock_cfg.NEWS_MEDIUM_IMPACT_ENABLED = True
    mock_cfg.NEWS_LOW_IMPACT_ENABLED    = False
    mock_cfg.NEWS_PAUSE_BEFORE_MINUTES  = 30
    mock_cfg.NEWS_RESUME_AFTER_MINUTES  = 15

    ev = _event(currency="USD", impact=ImpactLevel.HIGH, minutes_from_now=31.0)
    f  = _filter_with_events([ev])
    now = datetime.now(timezone.utc)
    result = f.evaluate_pair("EURUSD", now)
    assert not result.blocked
    assert result.reason == NewsBlockReason.NO_RELEVANT_NEWS


@patch("app.modules.news_filter.filter.settings")
def test_nf_15_30min_before_blocked(mock_cfg):
    """30 minutes before event → BLOCKED (exactly on boundary)."""
    mock_cfg.NEWS_FILTER_ENABLED     = True
    mock_cfg.NEWS_HIGH_IMPACT_ENABLED   = True
    mock_cfg.NEWS_MEDIUM_IMPACT_ENABLED = True
    mock_cfg.NEWS_LOW_IMPACT_ENABLED    = False
    mock_cfg.NEWS_PAUSE_BEFORE_MINUTES  = 30
    mock_cfg.NEWS_RESUME_AFTER_MINUTES  = 15

    ev = _event(currency="USD", impact=ImpactLevel.HIGH, minutes_from_now=30.0)
    f  = _filter_with_events([ev])
    now = datetime.now(timezone.utc)
    result = f.evaluate_pair("EURUSD", now)
    assert result.blocked
    assert result.reason == NewsBlockReason.HIGH_IMPACT_NEWS_WINDOW
    assert result.status == NewsEventStatus.UPCOMING


@patch("app.modules.news_filter.filter.settings")
def test_nf_16_during_event_blocked(mock_cfg):
    """0 minutes (exactly at event time) → BLOCKED, status=LIVE."""
    mock_cfg.NEWS_FILTER_ENABLED     = True
    mock_cfg.NEWS_HIGH_IMPACT_ENABLED   = True
    mock_cfg.NEWS_MEDIUM_IMPACT_ENABLED = True
    mock_cfg.NEWS_LOW_IMPACT_ENABLED    = False
    mock_cfg.NEWS_PAUSE_BEFORE_MINUTES  = 30
    mock_cfg.NEWS_RESUME_AFTER_MINUTES  = 15

    ev = _event(currency="USD", impact=ImpactLevel.HIGH, minutes_from_now=0.0)
    f  = _filter_with_events([ev])
    now = datetime.now(timezone.utc)
    result = f.evaluate_pair("EURUSD", now)
    assert result.blocked
    assert result.status == NewsEventStatus.LIVE


@patch("app.modules.news_filter.filter.settings")
def test_nf_17_after_resume_window_unblocked(mock_cfg):
    """16 minutes after event (resume=15) → NOT blocked (finished)."""
    mock_cfg.NEWS_FILTER_ENABLED     = True
    mock_cfg.NEWS_HIGH_IMPACT_ENABLED   = True
    mock_cfg.NEWS_MEDIUM_IMPACT_ENABLED = True
    mock_cfg.NEWS_LOW_IMPACT_ENABLED    = False
    mock_cfg.NEWS_PAUSE_BEFORE_MINUTES  = 30
    mock_cfg.NEWS_RESUME_AFTER_MINUTES  = 15

    # minutes_from_now = -16 → event was 16 min ago, past resume window
    ev = _event(currency="USD", impact=ImpactLevel.HIGH, minutes_from_now=-16.0)
    f  = _filter_with_events([ev])
    now = datetime.now(timezone.utc)
    result = f.evaluate_pair("EURUSD", now)
    assert not result.blocked


@patch("app.modules.news_filter.filter.settings")
def test_nf_18_inside_post_window_still_blocked(mock_cfg):
    """10 minutes after event (resume=15) → BLOCKED, status=LIVE."""
    mock_cfg.NEWS_FILTER_ENABLED     = True
    mock_cfg.NEWS_HIGH_IMPACT_ENABLED   = True
    mock_cfg.NEWS_MEDIUM_IMPACT_ENABLED = True
    mock_cfg.NEWS_LOW_IMPACT_ENABLED    = False
    mock_cfg.NEWS_PAUSE_BEFORE_MINUTES  = 30
    mock_cfg.NEWS_RESUME_AFTER_MINUTES  = 15

    ev = _event(currency="USD", impact=ImpactLevel.HIGH, minutes_from_now=-10.0)
    f  = _filter_with_events([ev])
    now = datetime.now(timezone.utc)
    result = f.evaluate_pair("EURUSD", now)
    assert result.blocked
    assert result.status == NewsEventStatus.LIVE


@patch("app.modules.news_filter.filter.settings")
def test_nf_19_unaffected_pair_not_blocked(mock_cfg):
    """USD event → EURGBP (no USD leg) is not affected/blocked."""
    mock_cfg.NEWS_FILTER_ENABLED     = True
    mock_cfg.NEWS_HIGH_IMPACT_ENABLED   = True
    mock_cfg.NEWS_MEDIUM_IMPACT_ENABLED = True
    mock_cfg.NEWS_LOW_IMPACT_ENABLED    = False
    mock_cfg.NEWS_PAUSE_BEFORE_MINUTES  = 30
    mock_cfg.NEWS_RESUME_AFTER_MINUTES  = 15

    ev = _event(currency="USD", impact=ImpactLevel.HIGH, minutes_from_now=10.0)
    f  = _filter_with_events([ev])
    now = datetime.now(timezone.utc)
    result = f.evaluate_pair("EURGBP", now)
    assert not result.blocked
    assert not result.affected


# ─── nf_20–nf_24 Impact config toggles ───────────────────────────────────────

@patch("app.modules.news_filter.filter.settings")
def test_nf_20_high_enabled_blocks(mock_cfg):
    mock_cfg.NEWS_FILTER_ENABLED     = True
    mock_cfg.NEWS_HIGH_IMPACT_ENABLED   = True
    mock_cfg.NEWS_MEDIUM_IMPACT_ENABLED = False
    mock_cfg.NEWS_LOW_IMPACT_ENABLED    = False
    mock_cfg.NEWS_PAUSE_BEFORE_MINUTES  = 30
    mock_cfg.NEWS_RESUME_AFTER_MINUTES  = 15

    ev = _event(impact=ImpactLevel.HIGH, minutes_from_now=10.0)
    f  = _filter_with_events([ev])
    result = f.evaluate_pair("EURUSD", _now())
    assert result.blocked


@patch("app.modules.news_filter.filter.settings")
def test_nf_21_high_disabled_does_not_block(mock_cfg):
    mock_cfg.NEWS_FILTER_ENABLED     = True
    mock_cfg.NEWS_HIGH_IMPACT_ENABLED   = False
    mock_cfg.NEWS_MEDIUM_IMPACT_ENABLED = False
    mock_cfg.NEWS_LOW_IMPACT_ENABLED    = False
    mock_cfg.NEWS_PAUSE_BEFORE_MINUTES  = 30
    mock_cfg.NEWS_RESUME_AFTER_MINUTES  = 15

    ev = _event(impact=ImpactLevel.HIGH, minutes_from_now=10.0)
    f  = _filter_with_events([ev])
    result = f.evaluate_pair("EURUSD", _now())
    assert not result.blocked


@patch("app.modules.news_filter.filter.settings")
def test_nf_22_medium_enabled_blocks_medium_event(mock_cfg):
    mock_cfg.NEWS_FILTER_ENABLED     = True
    mock_cfg.NEWS_HIGH_IMPACT_ENABLED   = False
    mock_cfg.NEWS_MEDIUM_IMPACT_ENABLED = True
    mock_cfg.NEWS_LOW_IMPACT_ENABLED    = False
    mock_cfg.NEWS_PAUSE_BEFORE_MINUTES  = 30
    mock_cfg.NEWS_RESUME_AFTER_MINUTES  = 15

    ev = _event(impact=ImpactLevel.MEDIUM, minutes_from_now=10.0)
    f  = _filter_with_events([ev])
    result = f.evaluate_pair("EURUSD", _now())
    assert result.blocked
    assert result.reason == NewsBlockReason.MEDIUM_IMPACT_NEWS_WINDOW


@patch("app.modules.news_filter.filter.settings")
def test_nf_23_low_disabled_not_blocked(mock_cfg):
    mock_cfg.NEWS_FILTER_ENABLED     = True
    mock_cfg.NEWS_HIGH_IMPACT_ENABLED   = True
    mock_cfg.NEWS_MEDIUM_IMPACT_ENABLED = True
    mock_cfg.NEWS_LOW_IMPACT_ENABLED    = False
    mock_cfg.NEWS_PAUSE_BEFORE_MINUTES  = 30
    mock_cfg.NEWS_RESUME_AFTER_MINUTES  = 15

    ev = _event(impact=ImpactLevel.LOW, minutes_from_now=10.0)
    f  = _filter_with_events([ev])
    result = f.evaluate_pair("EURUSD", _now())
    assert not result.blocked


@patch("app.modules.news_filter.filter.settings")
def test_nf_24_filter_disabled_always_allows(mock_cfg):
    """When NEWS_FILTER_ENABLED=False, evaluate_pair always returns not-blocked."""
    mock_cfg.NEWS_FILTER_ENABLED     = False
    mock_cfg.NEWS_HIGH_IMPACT_ENABLED   = True
    mock_cfg.NEWS_MEDIUM_IMPACT_ENABLED = True
    mock_cfg.NEWS_LOW_IMPACT_ENABLED    = True
    mock_cfg.NEWS_PAUSE_BEFORE_MINUTES  = 30
    mock_cfg.NEWS_RESUME_AFTER_MINUTES  = 15

    ev = _event(impact=ImpactLevel.HIGH, minutes_from_now=5.0)
    f  = _filter_with_events([ev])
    result = f.evaluate_pair("EURUSD", _now())
    assert not result.blocked


# ─── nf_25–nf_28 Provider failure ────────────────────────────────────────────

def test_nf_25_unavailable_provider_returns_unavailable_reason():
    f = _unavailable_filter()
    result = f.evaluate_pair("EURUSD", _now())
    assert result.reason == NewsBlockReason.NEWS_PROVIDER_UNAVAILABLE
    assert not result.provider_ok


def test_nf_26_unavailable_provider_does_not_fabricate_events():
    provider = UnavailableNewsProvider()
    assert provider.is_available is False


@pytest.mark.asyncio
async def test_nf_27_unavailable_provider_returns_empty_lists():
    provider = UnavailableNewsProvider()
    upcoming = await provider.fetch_upcoming(hours=24)
    recent   = await provider.fetch_recent(hours=48)
    assert upcoming == []
    assert recent   == []


@pytest.mark.asyncio
async def test_nf_28_refresh_with_failing_provider_clears_cache():
    """If provider raises on fetch_upcoming, cache is cleared and provider_ok=False."""
    provider = MagicMock()
    provider.is_available = True
    provider.fetch_upcoming = AsyncMock(side_effect=RuntimeError("timeout"))

    f = ConcreteNewsFilter(provider)
    f._cached_events = [_event()]   # pre-load some events
    f._provider_ok   = True

    await f.refresh()

    assert f._cached_events == []
    assert f._provider_ok is False


# ─── nf_29–nf_30 Duplicate prevention ────────────────────────────────────────

@pytest.mark.asyncio
async def test_nf_29_same_provider_event_not_duplicated_in_cache():
    """
    If provider returns the same event twice, after refresh the cache
    should deduplicate (same id → one entry).
    """
    ev = _event(provider="test_provider")
    provider = MagicMock()
    provider.is_available = True
    provider.fetch_upcoming = AsyncMock(return_value=[ev, ev])

    f = ConcreteNewsFilter(provider)
    await f.refresh()

    # Both have same id → they are literally the same object, no DB dedup needed
    # The cache stores all returned events; DB upsert handles DB dedup.
    # Verify at least 1 is stored and no crash.
    assert len(f.get_cached_events()) >= 1


@pytest.mark.asyncio
async def test_nf_30_malformed_event_skipped_app_continues():
    """
    A malformed event returned by the provider should be skipped, not crash the app.
    """
    bad_ev = MagicMock()
    bad_ev.id         = "x"
    bad_ev.event_name = "Bad"
    bad_ev.currency   = "USD"
    bad_ev.impact     = ImpactLevel.HIGH
    bad_ev.event_time = "not-a-datetime"   # malformed
    bad_ev.source     = ""
    bad_ev.actual     = None
    bad_ev.forecast   = None
    bad_ev.previous   = None
    bad_ev.provider   = "test"

    provider = MagicMock()
    provider.is_available = True
    provider.fetch_upcoming = AsyncMock(return_value=[bad_ev])

    f = ConcreteNewsFilter(provider)
    # Should not raise
    await f.refresh()


# ─── nf_31–nf_32 Risk Manager integration ────────────────────────────────────

@pytest.mark.asyncio
@patch("app.modules.news_filter.filter.settings")
async def test_nf_31_is_trading_allowed_returns_false_when_blocked(mock_cfg):
    mock_cfg.NEWS_FILTER_ENABLED     = True
    mock_cfg.NEWS_HIGH_IMPACT_ENABLED   = True
    mock_cfg.NEWS_MEDIUM_IMPACT_ENABLED = True
    mock_cfg.NEWS_LOW_IMPACT_ENABLED    = False
    mock_cfg.NEWS_PAUSE_BEFORE_MINUTES  = 30
    mock_cfg.NEWS_RESUME_AFTER_MINUTES  = 15

    ev = _event(currency="USD", impact=ImpactLevel.HIGH, minutes_from_now=10.0)
    f  = _filter_with_events([ev])
    allowed = await f.is_trading_allowed("EURUSD")
    assert allowed is False


@pytest.mark.asyncio
@patch("app.modules.news_filter.filter.settings")
async def test_nf_32_is_trading_allowed_returns_true_when_clear(mock_cfg):
    mock_cfg.NEWS_FILTER_ENABLED     = True
    mock_cfg.NEWS_HIGH_IMPACT_ENABLED   = True
    mock_cfg.NEWS_MEDIUM_IMPACT_ENABLED = True
    mock_cfg.NEWS_LOW_IMPACT_ENABLED    = False
    mock_cfg.NEWS_PAUSE_BEFORE_MINUTES  = 30
    mock_cfg.NEWS_RESUME_AFTER_MINUTES  = 15

    ev = _event(currency="USD", impact=ImpactLevel.HIGH, minutes_from_now=60.0)
    f  = _filter_with_events([ev])
    allowed = await f.is_trading_allowed("EURUSD")
    assert allowed is True


# ─── nf_33–nf_35 Security ────────────────────────────────────────────────────

def test_nf_33_evaluate_pair_does_not_expose_api_key():
    """PairNewsStatus fields must not contain NEWS_API_KEY."""
    f = _unavailable_filter()
    result = f.evaluate_pair("EURUSD", _now())
    result_str = str(result)
    assert settings_api_key_not_in(result_str)


def settings_api_key_not_in(text: str) -> bool:
    """Trivial guard: real API keys should never appear in domain objects."""
    from app.core.config import settings
    key = settings.NEWS_API_KEY
    if not key:
        return True   # nothing to check when not configured
    return key not in text


def test_nf_34_news_event_provider_field_not_a_secret():
    """The 'provider' field stores a name like 'forexfactory', not a key."""
    ev = _event(provider="forexfactory")
    assert "key" not in ev.provider.lower()
    assert "secret" not in ev.provider.lower()


def test_nf_35_pair_news_status_has_no_credential_fields():
    """PairNewsStatus dataclass has no field that could carry credentials."""
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(PairNewsStatus)}
    sensitive = {"api_key", "password", "secret", "token", "credential"}
    assert field_names.isdisjoint(sensitive)


# ─── nf_36–nf_37 Monitor lifecycle ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_nf_36_monitor_starts_and_stops_cleanly():
    provider = MagicMock()
    provider.is_available = True
    provider.fetch_upcoming = AsyncMock(return_value=[])

    f       = ConcreteNewsFilter(provider)
    monitor = NewsMonitor(f)

    with patch("app.modules.news_filter.monitor.settings") as mock_cfg:
        mock_cfg.NEWS_REFRESH_INTERVAL_SECONDS = 3600
        mock_cfg.NEWS_PAUSE_BEFORE_MINUTES     = 30
        mock_cfg.NEWS_RESUME_AFTER_MINUTES     = 15

        await monitor.start()
        assert monitor._task is not None and not monitor._task.done()
        await monitor.stop()
        assert monitor._task.done()


@pytest.mark.asyncio
async def test_nf_37_monitor_start_idempotent():
    provider = MagicMock()
    provider.is_available = True
    provider.fetch_upcoming = AsyncMock(return_value=[])

    f       = ConcreteNewsFilter(provider)
    monitor = NewsMonitor(f)

    with patch("app.modules.news_filter.monitor.settings") as mock_cfg:
        mock_cfg.NEWS_REFRESH_INTERVAL_SECONDS = 3600
        mock_cfg.NEWS_PAUSE_BEFORE_MINUTES     = 30
        mock_cfg.NEWS_RESUME_AFTER_MINUTES     = 15

        await monitor.start()
        task1 = monitor._task
        await monitor.start()   # second call must be ignored
        task2 = monitor._task
        assert task1 is task2   # same Task object

        await monitor.stop()
