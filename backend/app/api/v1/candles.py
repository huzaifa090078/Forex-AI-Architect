"""
Candles route — OHLCV data for the live chart.

GET /v1/candles?pair=EURUSD&timeframe=H1&count=200

Data comes from the same market-data pipeline used by the bot scanner.
Frontend chart library (lightweight-charts) consumes these directly.
No synthetic candles are ever returned.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.modules.market_scanner.market_data_service import MarketDataService
from app.modules.market_scanner.scanner import FOREX_PAIRS, TIMEFRAMES

logger = logging.getLogger(__name__)
router = APIRouter()

_data_service = MarketDataService()

# Acceptable pairs & timeframes (mirrors scanner constants)
_VALID_PAIRS = set(FOREX_PAIRS)
_VALID_TF    = set(TIMEFRAMES)


@router.get("", response_model=List[Dict[str, Any]])
async def get_candles(
    pair:      str = Query(..., description="Forex pair e.g. EURUSD"),
    timeframe: str = Query(default="H1", description=f"One of: {', '.join(TIMEFRAMES)}"),
    count:     int = Query(default=200, ge=10, le=1000),
) -> List[Dict[str, Any]]:
    """
    Return OHLCV candles for the requested pair and timeframe.

    Each candle:
      time  — Unix timestamp (seconds, UTC)
      open  — float
      high  — float
      low   — float
      close — float

    Returns 503 when MT5 is unavailable (Linux/Replit environment).
    Never returns synthetic or random candles.
    """
    pair_upper = pair.upper().strip()
    tf_upper   = timeframe.upper().strip()

    if pair_upper not in _VALID_PAIRS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid pair '{pair}'. Supported: {sorted(_VALID_PAIRS)}",
        )
    if tf_upper not in _VALID_TF:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid timeframe '{timeframe}'. Supported: {sorted(_VALID_TF)}",
        )

    try:
        bars = await _data_service.get_ohlcv(pair_upper, tf_upper, count)
    except Exception as exc:
        logger.warning("candles: data fetch failed %s %s — %s", pair_upper, tf_upper, exc)
        raise HTTPException(
            status_code=503,
            detail="Market data unavailable — MT5 is not connected in this environment.",
        )

    if not bars:
        raise HTTPException(
            status_code=503,
            detail="No candle data returned — MT5 connection required.",
        )

    # Normalise to lightweight-charts format (Unix timestamp in seconds)
    result: List[Dict[str, Any]] = []
    for bar in bars:
        ts = bar.get("time")
        if isinstance(ts, datetime):
            ts = int(ts.timestamp())
        elif isinstance(ts, (int, float)):
            ts = int(ts)
        else:
            continue
        result.append({
            "time":  ts,
            "open":  bar["open"],
            "high":  bar["high"],
            "low":   bar["low"],
            "close": bar["close"],
        })

    return result
