"""
Market Scanner routes — live pair quotes and opportunity scanning.

GET /v1/market/pairs          — current quotes for all 10 configured pairs
GET /v1/market/scan           — full scanner run (best timeframe per pair)
GET /v1/market/scan?timeframe — scanner run filtered to a single timeframe
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

import numpy as np
from fastapi import APIRouter, HTTPException, Query

from app.db.schemas import MarketOpportunityOut, MarketPairOut
from app.modules.market_scanner.scanner import FOREX_PAIRS, TIMEFRAMES, market_scanner as _scanner_singleton
from app.modules.market_scanner.market_data_service import MarketDataService

logger = logging.getLogger(__name__)
router = APIRouter()

# Use the shared singleton from scanner module; _data_service is local to this router
_scanner = _scanner_singleton
_data_service = MarketDataService()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trend_from_bars(bars: list) -> str:
    """Derive simple trend label from H1 OHLCV bars via 20-bar SMA."""
    if len(bars) < 20:
        return "ranging"
    closes = np.array([b["close"] for b in bars], dtype=float)
    sma20  = float(np.mean(closes[-20:]))
    price  = closes[-1]
    if price > sma20 * 1.001:
        return "bullish"
    if price < sma20 * 0.999:
        return "bearish"
    return "ranging"


def _volatility_from_bars(bars: list) -> Optional[float]:
    """
    Compute ATR(14) as a percentage of the last close price.

    Uses the simple ATR formula (mean of True Range over 14 bars) as a
    volatility proxy.  Returns None when fewer than 15 bars are available.
    The value is expressed as a percentage, e.g. 0.0650 means 0.065 % ATR.
    """
    if len(bars) < 15:
        return None
    closes = np.array([b["close"] for b in bars], dtype=float)
    highs  = np.array([b["high"]  for b in bars], dtype=float)
    lows   = np.array([b["low"]   for b in bars], dtype=float)
    if len(closes) < 2:
        return None
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:]  - closes[:-1]),
        ),
    )
    atr   = float(tr[-14:].mean()) if len(tr) >= 14 else float(tr.mean())
    price = float(closes[-1])
    if price <= 0.0:
        return None
    return round(atr / price * 100.0, 4)


async def _build_pair_out(pair: str) -> Optional[MarketPairOut]:
    """
    Fetch tick and H1 OHLCV for one pair concurrently, build MarketPairOut.
    Returns None if either call fails so one bad pair never breaks the list.
    """
    try:
        tick, bars = await asyncio.gather(
            _data_service.get_tick(pair),
            _data_service.get_ohlcv(pair, "H1", 50),
        )
    except Exception as exc:
        logger.error("get_pairs: data fetch failed for %s — %s", pair, exc)
        return None

    return MarketPairOut(
        symbol=pair,
        bid=tick["bid"],
        ask=tick["ask"],
        spread=round(tick["spread"], 5),
        change_24h=tick["change_24h"],
        volatility=_volatility_from_bars(bars),
        trend=_trend_from_bars(bars),
        updated_at=datetime.now(timezone.utc),
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/pairs", response_model=List[MarketPairOut])
async def get_pairs() -> List[MarketPairOut]:
    """
    Return current bid/ask, spread, 24h change, and trend direction for
    every pair in the configured FOREX_PAIRS list.
    Data is sourced from MT5/Exness via MarketDataService.
    """
    results = await asyncio.gather(
        *[_build_pair_out(pair) for pair in FOREX_PAIRS]
    )
    pairs = [r for r in results if r is not None]

    if not pairs:
        raise HTTPException(
            status_code=503,
            detail="Market data unavailable — all pair fetches failed.",
        )
    return pairs


@router.get("/scan", response_model=List[MarketOpportunityOut])
async def scan(
    timeframe: Optional[str] = Query(
        default=None,
        description=(
            "Restrict scan to a single timeframe. "
            f"Allowed values: {', '.join(TIMEFRAMES)}. "
            "Omit to return the best timeframe per pair."
        ),
    ),
) -> List[MarketOpportunityOut]:
    """
    Run the Market Scanner across all 10 configured pairs on demand.

    - Without `timeframe`: returns the highest-scoring timeframe per pair.
    - With `timeframe`: returns all pairs that qualify on that specific timeframe.

    Only pairs/timeframes with sufficient structural confluence are returned.
    No trading logic is applied; results are structural observations only.
    """
    if timeframe is not None and timeframe not in TIMEFRAMES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid timeframe '{timeframe}'. "
                f"Must be one of: {', '.join(TIMEFRAMES)}"
            ),
        )

    if timeframe:
        raw = await _scanner.scan_all_timeframe(FOREX_PAIRS, timeframe)
    else:
        raw = await _scanner.scan_all(FOREX_PAIRS)

    return [
        MarketOpportunityOut(
            pair=r.pair,
            direction=r.direction,
            score=round(r.score * 100.0, 1),   # internal 0–1 → API 0–100
            smc_pattern=r.smc_pattern,
            timeframe=r.timeframe,
            current_price=r.current_price,
            trend_status=r.trend_status,
            volatility_status=r.volatility_status,
            volume_status=r.volume_status,
            spread=r.spread,
            session=r.session,
            priority_level=r.priority_level,
            confluence_factors=r.confluence_factors,
            detected_at=r.detected_at,
        )
        for r in raw
    ]
