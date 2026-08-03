"""
Market Scanner — concrete implementation.

Scans 10 configured forex pairs across 5 timeframes using MarketDataService
(yfinance).  Computes structural indicators (EMA trend, RSI momentum, ATR
volatility) to rank and describe market conditions.

No trading logic.  No AI analysis.  No mock data.
"""

import asyncio
import logging
from typing import List, Optional

import numpy as np

from app.modules.market_scanner.base import BaseMarketScanner
from app.modules.market_scanner.interfaces import ScanResult
from app.modules.market_scanner.market_data_service import MarketDataService

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

FOREX_PAIRS: List[str] = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD",
    "USDCAD", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP",
]

TIMEFRAMES: List[str] = ["M1", "M5", "M15", "H1", "H4"]

# Minimum bars required before indicators are considered reliable
_MIN_BARS = 20

# Bars fetched per scan — enough for EMA50 + RSI14 + ATR14 with headroom
_OHLCV_COUNT = 60

# Minimum score a timeframe result must reach to be returned
_SCORE_THRESHOLD = 0.6


# ── Indicator helpers ─────────────────────────────────────────────────────────

def _ema(values: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average over `values`."""
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1.0 - alpha) * out[i - 1]
    return out


def _rsi(closes: np.ndarray, period: int = 14) -> float:
    """Simple RSI for the most recent bar (Wilder-smoothed not required here)."""
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes[-(period + 1):])
    gains  = np.where(deltas > 0, deltas,  0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains.mean()
    avg_loss = losses.mean()
    if avg_loss == 0.0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    """Average True Range over the last `period` bars."""
    if len(closes) < 2:
        return 0.0
    tr = np.maximum(
        highs[1:]  - lows[1:],
        np.maximum(
            np.abs(highs[1:]  - closes[:-1]),
            np.abs(lows[1:]   - closes[:-1]),
        ),
    )
    return float(tr[-period:].mean())


# ── MarketScanner ─────────────────────────────────────────────────────────────

class MarketScanner(BaseMarketScanner):
    """
    Concrete market scanner backed by MarketDataService.

    For each pair, all five timeframes are evaluated in parallel.
    The timeframe with the highest confluence score is returned.
    Pairs with no timeframe above `_SCORE_THRESHOLD` are excluded.
    """

    def __init__(self) -> None:
        super().__init__(data_provider=MarketDataService())

    # ── IMarketScanner ────────────────────────────────────────────────────────

    async def scan_all(self, pairs: List[str]) -> List[ScanResult]:
        """
        Scan all `pairs` concurrently.  Returns results sorted by score
        descending; pairs with no qualifying opportunity are omitted.
        """
        raw = await asyncio.gather(
            *[self.scan_pair(p) for p in pairs],
            return_exceptions=False,
        )
        results = [r for r in raw if r is not None]
        results.sort(key=lambda r: r.score, reverse=True)
        logger.info(
            "MarketScanner.scan_all: %d/%d pairs returned opportunities",
            len(results), len(pairs),
        )
        return results

    async def scan_pair(self, pair: str) -> Optional[ScanResult]:
        """
        Evaluate all timeframes for a single pair concurrently.
        Returns the result from the timeframe with the highest score,
        or None if no timeframe clears the score threshold.
        """
        tf_results = await asyncio.gather(
            *[self._scan_pair_timeframe(pair, tf) for tf in TIMEFRAMES],
            return_exceptions=False,
        )
        valid = [r for r in tf_results if r is not None]
        if not valid:
            return None
        return max(valid, key=lambda r: r.score)

    # ── Per-timeframe scan ────────────────────────────────────────────────────

    async def _scan_pair_timeframe(
        self, pair: str, timeframe: str
    ) -> Optional[ScanResult]:
        """
        Scan one pair on one timeframe.

        Steps:
          1. Fetch OHLCV via MarketDataService.
          2. Compute EMA20, EMA50, RSI(14), ATR(14).
          3. Assess structural alignment (trend + momentum + volatility).
          4. Return ScanResult if score ≥ threshold, else None.

        Returns None on data errors or insufficient bars.
        """
        try:
            bars = await self._provider.get_ohlcv(pair, timeframe, _OHLCV_COUNT)
        except Exception as exc:
            logger.warning(
                "MarketScanner: data fetch failed for %s/%s — %s",
                pair, timeframe, exc,
            )
            return None

        if len(bars) < _MIN_BARS:
            logger.debug(
                "MarketScanner: insufficient bars for %s/%s (%d < %d)",
                pair, timeframe, len(bars), _MIN_BARS,
            )
            return None

        closes = np.array([b["close"] for b in bars], dtype=float)
        highs  = np.array([b["high"]  for b in bars], dtype=float)
        lows   = np.array([b["low"]   for b in bars], dtype=float)

        ema20 = _ema(closes, 20)
        ema50 = _ema(closes, 50)
        rsi   = _rsi(closes)
        atr   = _atr(highs, lows, closes)

        price      = closes[-1]
        ema20_last = ema20[-1]
        ema50_last = ema50[-1]

        # ── Structural observations (no trading decisions) ────────────────
        ema_bullish      = ema20_last > ema50_last
        price_above_ema20 = price > ema20_last
        rsi_bullish       = rsi > 50.0
        rsi_strong_bull   = rsi > 60.0
        rsi_strong_bear   = rsi < 40.0
        atr_pct           = (atr / price * 100.0) if price > 0.0 else 0.0
        elevated_volatility = atr_pct > 0.05

        # Full structural alignment required — otherwise no result
        aligned_bull = ema_bullish       and price_above_ema20  and rsi_bullish
        aligned_bear = (not ema_bullish) and (not price_above_ema20) and (not rsi_bullish)

        if not (aligned_bull or aligned_bear):
            return None

        # ── Score: base 0.6 for alignment + bonuses ───────────────────────
        score = 0.6
        momentum_confirmed = rsi_strong_bull if aligned_bull else rsi_strong_bear
        if momentum_confirmed:
            score += 0.2
        if elevated_volatility:
            score += 0.2

        if score < _SCORE_THRESHOLD:
            return None

        # ── Pattern description ───────────────────────────────────────────
        momentum_suffix = " + RSI Momentum" if momentum_confirmed else ""
        if aligned_bull:
            pattern   = f"EMA Bullish Structure{momentum_suffix}"
            direction = "buy"
        else:
            pattern   = f"EMA Bearish Structure{momentum_suffix}"
            direction = "sell"

        # ── Confluence factor labels ──────────────────────────────────────
        factors: List[str] = []
        factors.append("EMA20>EMA50" if ema_bullish else "EMA20<EMA50")
        factors.append("Price>EMA20" if price_above_ema20 else "Price<EMA20")
        factors.append("RSI>50" if rsi_bullish else "RSI<50")
        if rsi_strong_bull:
            factors.append("RSI>60")
        elif rsi_strong_bear:
            factors.append("RSI<40")
        if elevated_volatility:
            factors.append(f"ATR {atr_pct:.2f}%")

        return ScanResult(
            pair=pair,
            direction=direction,
            score=score,
            smc_pattern=pattern,
            timeframe=timeframe,
            confluence_factors=factors,
            metadata={
                "ema20":  round(float(ema20_last), 5),
                "ema50":  round(float(ema50_last), 5),
                "rsi":    round(rsi, 2),
                "atr":    round(atr, 5),
                "price":  round(price, 5),
            },
        )

    # ── Timeframe-filtered scan ───────────────────────────────────────────────

    async def scan_all_timeframe(
        self, pairs: List[str], timeframe: str
    ) -> List[ScanResult]:
        """
        Scan all `pairs` on a single `timeframe` concurrently.
        Returns results sorted by score descending.
        """
        raw = await asyncio.gather(
            *[self._scan_pair_timeframe(p, timeframe) for p in pairs],
            return_exceptions=False,
        )
        results = [r for r in raw if r is not None]
        results.sort(key=lambda r: r.score, reverse=True)
        logger.info(
            "MarketScanner.scan_all_timeframe(%s): %d/%d pairs returned opportunities",
            timeframe, len(results), len(pairs),
        )
        return results
