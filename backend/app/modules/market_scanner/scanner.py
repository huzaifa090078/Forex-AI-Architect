"""
Market Scanner — concrete implementation.

Scans 10 configured forex pairs across 5 timeframes using MarketDataService
(MT5/Exness).  Computes structural indicators (EMA trend, RSI momentum, ATR
volatility, VOLUME_20) to rank and describe market conditions.

Indicators are computed via IndicatorSuite (build_default_suite) — the single
authoritative source for all technical calculations in this project.  No
duplicate indicator logic exists in this module.

No trading logic.  No AI analysis.  No mock data.
"""

import asyncio
import logging
from typing import List, Optional

from app.modules.market_scanner.base import BaseMarketScanner
from app.modules.market_scanner.interfaces import PriorityLevel, ScanResult
from app.modules.market_scanner.market_data_service import MarketDataService
from app.modules.market_scanner.session import get_current_session
from app.modules.indicators.suite import (
    build_default_suite,
    EMA_20,
    EMA_50,
    RSI_14,
    ATR_14,
    VOLUME_20,
)

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

FOREX_PAIRS: List[str] = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD",
    "USDCAD", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP",
]

TIMEFRAMES: List[str] = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]

# Minimum bars required before indicators are considered reliable.
# EMA_50 needs at least 50 bars to produce a valid value; 51 gives one
# warm-up bar beyond the seed, matching calc_ema's minimum-bars contract.
_MIN_BARS = 51

# Bars fetched per scan — enough for EMA50 + RSI14 + ATR14 + VOLUME_20 with headroom
_OHLCV_COUNT = 60

# Minimum score a timeframe result must reach to be returned (directional only)
_SCORE_THRESHOLD = 0.6

# Score assigned to a positively-detected ranging market
_RANGING_SCORE = 0.45

# Maximum allowed spread in pips before a pair is skipped
_MAX_SPREAD_PIPS = 3.0

# Pairs quoted with 2 decimal places (JPY); all others use 4 decimal places
_JPY_PAIRS = frozenset({"USDJPY", "EURJPY", "GBPJPY"})

# Subset of indicators the scanner needs (avoids running all 13 unnecessarily)
_SCANNER_INDICATORS = [EMA_20, EMA_50, RSI_14, ATR_14, VOLUME_20]

# ── Shared IndicatorSuite ──────────────────────────────────────────────────────
# Built once at module load.  compute_all() is stateless — sharing is safe.
_indicator_suite = build_default_suite()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _pip_size(pair: str) -> float:
    """Return the pip size (price units per pip) for `pair`."""
    return 0.01 if pair in _JPY_PAIRS else 0.0001


def _spread_pips(pair: str, raw_spread: float) -> float:
    """Convert raw bid/ask spread to pips for `pair`."""
    ps = _pip_size(pair)
    return raw_spread / ps if ps > 0.0 else 0.0


def _classify_volume(vol_ratio: Optional[float], high_volume_flag: bool) -> str:
    """
    Classify volume as High Volume / Normal Volume / Low Volume.

    Uses the VolumeAnalysisIndicator vol_ratio (current volume / SMA20):
      > 1.5  → High Volume
      < 0.8  → Low Volume
      else   → Normal Volume
    """
    if vol_ratio is None:
        return "Normal Volume"
    if high_volume_flag or vol_ratio > 1.5:
        return "High Volume"
    if vol_ratio < 0.8:
        return "Low Volume"
    return "Normal Volume"


def _classify_volatility(atr_pct: float) -> str:
    """
    Classify volatility as High / Normal / Low based on ATR as % of price.

      > 0.10 %  → High
      > 0.03 %  → Normal
      ≤ 0.03 %  → Low
    """
    if atr_pct > 0.10:
        return "High"
    if atr_pct > 0.03:
        return "Normal"
    return "Low"


def _derive_priority(score: float) -> str:
    """
    Map composite score (0.0–1.0) to a priority level.

      ≥ 0.80  → HIGH
      ≥ 0.60  → MEDIUM
      < 0.60  → LOW
    """
    if score >= 0.80:
        return PriorityLevel.HIGH.value
    if score >= 0.60:
        return PriorityLevel.MEDIUM.value
    return PriorityLevel.LOW.value


# ── MarketScanner ─────────────────────────────────────────────────────────────

class MarketScanner(BaseMarketScanner):
    """
    Concrete market scanner backed by MarketDataService.

    For each pair, all configured timeframes are evaluated in parallel.
    The timeframe with the highest confluence score is returned.
    Pairs with no timeframe above `_SCORE_THRESHOLD` are excluded unless
    a ranging condition is positively detected.
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
        or None if no timeframe yields a result.
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
          1. Fetch OHLCV and live tick concurrently via MarketDataService.
          2. Filter pairs whose live spread exceeds _MAX_SPREAD_PIPS.
          3. Compute EMA_20, EMA_50, RSI_14, ATR_14, VOLUME_20 via IndicatorSuite.
          4. Detect trend state: bullish / bearish / ranging.
          5. Classify volatility, volume, and trading session.
          6. Score the opportunity and derive priority level.
          7. Return ScanResult with full output fields, or None when no setup found.

        Returns None on data errors, insufficient bars, indicator failures,
        or spread above threshold.
        """
        # ── 1. Fetch OHLCV + tick concurrently ───────────────────────────────
        fetch = await asyncio.gather(
            self._provider.get_ohlcv(pair, timeframe, _OHLCV_COUNT),
            self._provider.get_tick(pair),
            return_exceptions=True,
        )
        bars_or_exc = fetch[0]
        tick_or_exc = fetch[1]

        if isinstance(bars_or_exc, Exception):
            logger.warning(
                "MarketScanner: OHLCV fetch failed for %s/%s — %s",
                pair, timeframe, bars_or_exc,
            )
            return None

        bars = bars_or_exc
        tick: Optional[dict] = None if isinstance(tick_or_exc, Exception) else tick_or_exc

        if isinstance(tick_or_exc, Exception):
            logger.debug(
                "MarketScanner: tick fetch failed for %s — %s (spread filter skipped)",
                pair, tick_or_exc,
            )

        # ── 2. Spread filtering ───────────────────────────────────────────────
        raw_spread: Optional[float] = None
        if tick is not None:
            raw_spread = float(tick.get("spread", 0.0))
            pips = _spread_pips(pair, raw_spread)
            if pips > _MAX_SPREAD_PIPS:
                logger.debug(
                    "MarketScanner: %s spread %.1f pips > %.1f threshold; skipping",
                    pair, pips, _MAX_SPREAD_PIPS,
                )
                return None

        # ── Bar count guard ───────────────────────────────────────────────────
        if len(bars) < _MIN_BARS:
            logger.debug(
                "MarketScanner: insufficient bars for %s/%s (%d < %d)",
                pair, timeframe, len(bars), _MIN_BARS,
            )
            return None

        # ── 3. Indicator computation via IndicatorSuite ───────────────────────
        ind_results = _indicator_suite.compute_all(
            bars, indicators=_SCANNER_INDICATORS
        )

        missing = [k for k in _SCANNER_INDICATORS if k not in ind_results]
        if missing:
            logger.debug(
                "MarketScanner: indicator(s) %s unavailable for %s/%s; skipping",
                missing, pair, timeframe,
            )
            return None

        ema20_last  = ind_results[EMA_20].value
        ema50_last  = ind_results[EMA_50].value
        rsi         = ind_results[RSI_14].value
        atr         = ind_results[ATR_14].value
        vol_result  = ind_results[VOLUME_20]

        if any(v is None for v in (ema20_last, ema50_last, rsi, atr)):
            logger.debug(
                "MarketScanner: None indicator value for %s/%s; skipping",
                pair, timeframe,
            )
            return None

        price = float(bars[-1]["close"])

        # ── 4. Structural observations ────────────────────────────────────────
        ema_bullish       = ema20_last > ema50_last
        price_above_ema20 = price > ema20_last
        rsi_bullish       = rsi > 50.0
        rsi_strong_bull   = rsi > 60.0
        rsi_strong_bear   = rsi < 40.0
        atr_pct           = (atr / price * 100.0) if price > 0.0 else 0.0
        elevated_volatility = atr_pct > 0.05

        # Ranging: EMAs converging AND RSI near neutral zone
        ema_spread_pct = (
            abs(ema20_last - ema50_last) / price * 100.0
            if price > 0.0 else 1.0
        )
        is_ranging = ema_spread_pct < 0.15 and 40.0 <= rsi <= 60.0

        aligned_bull = ema_bullish and price_above_ema20 and rsi_bullish
        aligned_bear = (not ema_bullish) and (not price_above_ema20) and (not rsi_bullish)

        # ── 5. Volume classification ──────────────────────────────────────────
        vol_value = vol_result.value  # dict {"obv": float, "vol_ratio": float} | None
        vol_ratio: Optional[float] = None
        high_vol_flag = False
        if isinstance(vol_value, dict):
            vol_ratio     = vol_value.get("vol_ratio")
            high_vol_flag = bool(vol_result.metadata.get("high_volume", False))
        volume_status = _classify_volume(vol_ratio, high_vol_flag)

        # ── 6. Volatility classification ──────────────────────────────────────
        volatility_status = _classify_volatility(atr_pct)

        # ── 7. Session detection ──────────────────────────────────────────────
        session = get_current_session().value

        # ── Ranging path — do not silently discard ranging markets ────────────
        if is_ranging and not (aligned_bull or aligned_bear):
            factors = [
                f"EMA Spread {ema_spread_pct:.3f}%",
                f"RSI Neutral {rsi:.1f}",
            ]
            if elevated_volatility:
                factors.append(f"ATR {atr_pct:.2f}%")
            factors.append(f"Vol {volume_status}")

            return ScanResult(
                pair=pair,
                direction="ranging",
                score=_RANGING_SCORE,
                smc_pattern="EMA Convergence (Ranging)",
                timeframe=timeframe,
                trend_status="ranging",
                volatility_status=volatility_status,
                volume_status=volume_status,
                current_price=round(price, 5),
                priority_level=PriorityLevel.LOW.value,
                spread=raw_spread,
                session=session,
                confluence_factors=factors,
                metadata={
                    "ema20":         round(float(ema20_last), 5),
                    "ema50":         round(float(ema50_last), 5),
                    "ema_spread_pct": round(ema_spread_pct, 4),
                    "rsi":           round(rsi, 2),
                    "atr":           round(atr, 5),
                    "price":         round(price, 5),
                    "vol_ratio":     round(vol_ratio, 4) if vol_ratio is not None else None,
                },
            )

        # No directional alignment and no ranging — nothing to report
        if not (aligned_bull or aligned_bear):
            return None

        # ── 8. Directional score: base 0.6 for alignment + bonuses ───────────
        score = 0.6
        momentum_confirmed = rsi_strong_bull if aligned_bull else rsi_strong_bear
        if momentum_confirmed:
            score += 0.2
        if elevated_volatility:
            score += 0.2

        if score < _SCORE_THRESHOLD:
            return None

        # ── 9. Direction, trend status, and pattern ───────────────────────────
        momentum_suffix = " + RSI Momentum" if momentum_confirmed else ""
        if aligned_bull:
            direction    = "buy"
            trend_status = "bullish"
            pattern      = f"EMA Bullish Structure{momentum_suffix}"
        else:
            direction    = "sell"
            trend_status = "bearish"
            pattern      = f"EMA Bearish Structure{momentum_suffix}"

        # ── 10. Priority level ────────────────────────────────────────────────
        priority_level = _derive_priority(score)

        # ── 11. Confluence factor labels ──────────────────────────────────────
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
        factors.append(f"Vol {volume_status}")

        return ScanResult(
            pair=pair,
            direction=direction,
            score=score,
            smc_pattern=pattern,
            timeframe=timeframe,
            trend_status=trend_status,
            volatility_status=volatility_status,
            volume_status=volume_status,
            current_price=round(price, 5),
            priority_level=priority_level,
            spread=raw_spread,
            session=session,
            confluence_factors=factors,
            metadata={
                "ema20":     round(float(ema20_last), 5),
                "ema50":     round(float(ema50_last), 5),
                "rsi":       round(rsi, 2),
                "atr":       round(atr, 5),
                "price":     round(price, 5),
                "vol_ratio": round(vol_ratio, 4) if vol_ratio is not None else None,
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


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

#: Shared MarketScanner instance — used by the HTTP API and the live-feed
#: candle callback registered in main.py.
market_scanner: MarketScanner = MarketScanner()
