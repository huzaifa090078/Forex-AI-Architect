"""
Market Data Engine — Section 3 Data Validation Layer.

Validates OHLCV bars and tick dicts coming from the MT5 connector before
they reach any downstream module.  All validation is deterministic and safe —
no external calls, no I/O.

Public API:
    validate_bar(bar, symbol, timeframe)  → bar dict or raises BarValidationError
    validate_bars(bars, symbol, timeframe) → cleaned, deduplicated list
    validate_tick(tick, symbol)            → tick dict or raises TickValidationError
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class BarValidationError(ValueError):
    """Raised when a single OHLCV bar fails validation."""


class TickValidationError(ValueError):
    """Raised when a tick dict fails validation."""


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------

_REQUIRED_BAR_FIELDS: frozenset = frozenset({"time", "open", "high", "low", "close", "volume"})
_REQUIRED_TICK_FIELDS: frozenset = frozenset({"bid", "ask", "spread", "tick_time"})


# ---------------------------------------------------------------------------
# validate_bar
# ---------------------------------------------------------------------------

def validate_bar(
    bar: Dict[str, Any],
    symbol: str = "",
    timeframe: str = "",
) -> Dict[str, Any]:
    """
    Validate a single OHLCV bar dict.

    Checks performed:
    1. All required fields present.
    2. 'time' is a datetime instance.
    3. open/high/low/close are positive floats.
    4. high >= open, high >= close (no invalid wick).
    5. low  <= open, low  <= close (no invalid wick).
    6. low  <= high.
    7. volume is non-negative.

    Returns the bar unchanged on success.
    Raises BarValidationError with a descriptive message on failure.
    """
    label = f"[{symbol}/{timeframe}]" if (symbol or timeframe) else ""

    # 1. Required fields
    missing = _REQUIRED_BAR_FIELDS - set(bar.keys())
    if missing:
        raise BarValidationError(f"{label} Bar missing required fields: {sorted(missing)}")

    # 2. Timestamp type
    ts = bar["time"]
    if not isinstance(ts, datetime):
        raise BarValidationError(
            f"{label} Bar 'time' must be a datetime, got {type(ts).__name__}: {ts!r}"
        )

    # 3. Numeric prices — must be positive
    prices: Dict[str, float] = {}
    for field in ("open", "high", "low", "close"):
        raw = bar[field]
        try:
            val = float(raw)
        except (TypeError, ValueError):
            raise BarValidationError(
                f"{label} Field '{field}' is not numeric: {raw!r}"
            )
        if val <= 0.0:
            raise BarValidationError(
                f"{label} Field '{field}' must be > 0, got {val}"
            )
        prices[field] = val

    o, h, l, c = prices["open"], prices["high"], prices["low"], prices["close"]

    # 4. High must cover open and close
    if h < o:
        raise BarValidationError(
            f"{label} high ({h}) < open ({o}) — invalid OHLC relationship"
        )
    if h < c:
        raise BarValidationError(
            f"{label} high ({h}) < close ({c}) — invalid OHLC relationship"
        )

    # 5. Low must be under open and close
    if l > o:
        raise BarValidationError(
            f"{label} low ({l}) > open ({o}) — invalid OHLC relationship"
        )
    if l > c:
        raise BarValidationError(
            f"{label} low ({l}) > close ({c}) — invalid OHLC relationship"
        )

    # 6. Low <= High
    if l > h:
        raise BarValidationError(
            f"{label} low ({l}) > high ({h}) — corrupted bar"
        )

    # 7. Volume — non-negative
    raw_vol = bar["volume"]
    try:
        vol = float(raw_vol)
    except (TypeError, ValueError):
        raise BarValidationError(
            f"{label} Field 'volume' is not numeric: {raw_vol!r}"
        )
    if vol < 0.0:
        raise BarValidationError(
            f"{label} Field 'volume' is negative: {vol}"
        )

    return bar


# ---------------------------------------------------------------------------
# validate_bars
# ---------------------------------------------------------------------------

def validate_bars(
    bars: List[Dict[str, Any]],
    symbol: str = "",
    timeframe: str = "",
) -> List[Dict[str, Any]]:
    """
    Validate a list of OHLCV bars.

    Steps:
    1. Validate each bar individually; drop and log any that fail.
    2. Deduplicate by timestamp — when two bars share a timestamp the last
       occurrence (most recently received) wins.
    3. Sort ascending by time.
    4. Warn on abnormal candle gaps (gap > 5× the median interval).

    Returns the cleaned list.  Never raises — bad bars are dropped with a
    warning so a single corrupted record cannot poison an entire fetch.
    """
    label = f"[{symbol}/{timeframe}]" if (symbol or timeframe) else ""

    if not bars:
        return bars

    # Step 1 — individual validation
    valid: List[Dict[str, Any]] = []
    rejected = 0
    for bar in bars:
        try:
            validate_bar(bar, symbol, timeframe)
            valid.append(bar)
        except BarValidationError as exc:
            logger.warning("validate_bars: dropping bar — %s", exc)
            rejected += 1

    if rejected:
        logger.warning(
            "validate_bars %s dropped %d/%d bar(s) due to validation errors",
            label, rejected, len(bars),
        )

    if not valid:
        return valid

    # Step 2 — deduplicate by timestamp (last occurrence wins)
    seen: Dict[datetime, Dict[str, Any]] = {}
    for bar in valid:
        ts: datetime = bar["time"]
        if ts in seen:
            logger.debug(
                "validate_bars %s duplicate candle at %s — keeping latest", label, ts
            )
        seen[ts] = bar

    dupes = len(valid) - len(seen)
    if dupes:
        logger.warning(
            "validate_bars %s removed %d duplicate candle(s)", label, dupes
        )

    # Step 3 — sort ascending
    deduped = sorted(seen.values(), key=lambda b: b["time"])

    # Step 4 — gap detection (heuristic, warnings only)
    if len(deduped) >= 3:
        timestamps = [b["time"] for b in deduped]
        gaps = [
            (timestamps[i + 1] - timestamps[i]).total_seconds()
            for i in range(len(timestamps) - 1)
        ]
        sorted_gaps = sorted(gaps)
        median_gap = sorted_gaps[len(sorted_gaps) // 2]
        if median_gap > 0:
            for i, gap in enumerate(gaps):
                if gap > max(median_gap * 5.0, 60.0):
                    logger.warning(
                        "validate_bars %s abnormal gap between %s and %s "
                        "(%.0fs vs median %.0fs) — possible missing candles",
                        label,
                        timestamps[i].isoformat(),
                        timestamps[i + 1].isoformat(),
                        gap,
                        median_gap,
                    )

    return deduped


# ---------------------------------------------------------------------------
# validate_tick
# ---------------------------------------------------------------------------

def validate_tick(
    tick: Dict[str, Any],
    symbol: str = "",
) -> Dict[str, Any]:
    """
    Validate a tick dict returned by IMT5Connector.get_tick().

    Checks performed:
    1. All required fields present (bid, ask, spread, tick_time).
    2. bid and ask are positive floats.
    3. ask >= bid (non-inverted spread).
    4. tick_time is a datetime instance.

    Returns the tick unchanged on success.
    Raises TickValidationError on failure.
    """
    label = f"[{symbol}]" if symbol else ""

    # 1. Required fields
    missing = _REQUIRED_TICK_FIELDS - set(tick.keys())
    if missing:
        raise TickValidationError(
            f"{label} Tick missing required fields: {sorted(missing)}"
        )

    # 2. Numeric bid / ask — must be positive
    for field in ("bid", "ask"):
        raw = tick[field]
        try:
            val = float(raw)
        except (TypeError, ValueError):
            raise TickValidationError(
                f"{label} Tick field '{field}' is not numeric: {raw!r}"
            )
        if val <= 0.0:
            raise TickValidationError(
                f"{label} Tick field '{field}' must be > 0, got {val}"
            )

    bid = float(tick["bid"])
    ask = float(tick["ask"])

    # 3. Non-inverted spread
    if ask < bid:
        raise TickValidationError(
            f"{label} Tick ask ({ask}) < bid ({bid}) — inverted spread"
        )

    # 4. Timestamp type
    ts = tick["tick_time"]
    if not isinstance(ts, datetime):
        raise TickValidationError(
            f"{label} Tick 'tick_time' must be a datetime, got {type(ts).__name__}: {ts!r}"
        )

    return tick
