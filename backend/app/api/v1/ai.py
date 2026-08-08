"""
AI Decision Engine routes.

GET /v1/ai/signal?pair=EURUSD&timeframe=H1
    Run the full AI evaluation pipeline for a single pair/timeframe.
    Returns a TradeDecisionOut (BUY / SELL / NO_TRADE).

GET /v1/ai/signals?pairs=EURUSD,GBPUSD&timeframe=H1&min_confidence=0.75
    Evaluate multiple pairs concurrently.
    Returns only actionable BUY/SELL decisions (NO_TRADE results excluded).

No auth required — these are pure analysis endpoints (no user data).
Pattern follows /v1/market and /v1/smc.

Data pipeline (orchestrated here, never inside the engine):
  1. Fetch OHLCV for the primary timeframe (200 bars).
  2. Fetch live tick for spread concurrently with step 1.
  3. Fetch OHLCV for all four SMC timeframes (60 bars each, concurrent, failures tolerated).
  4. Compute all 16 indicators via build_default_suite().
  5. Run SMC multi-timeframe analysis + confluence scoring.
  6. Build a ScanResult from the fetched/computed data.
  7. Call RuleBasedAIEngine.evaluate() with the pre-computed inputs.
  8. Serialize TradeDecision → TradeDecisionOut and return.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.db.schemas import IndicatorSummaryOut, SMCSummaryOut, TradeDecisionOut
from app.modules.ai_engine.engine import RuleBasedAIEngine
from app.modules.ai_engine.types import TradeAction, TradeDecision
from app.modules.indicators.suite import build_default_suite
from app.modules.market_scanner.interfaces import ScanResult
from app.modules.market_scanner.market_data_service import MarketDataService
from app.modules.market_scanner.scanner import FOREX_PAIRS
from app.modules.smc.analyzer import SMCAnalyzer
from app.modules.smc.interfaces import TrendBias

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Module-level singletons ───────────────────────────────────────────────────
# Each singleton is stateless / concurrency-safe per its module's guarantee.
_engine          = RuleBasedAIEngine()
_data_service    = MarketDataService()
_smc_analyzer    = SMCAnalyzer()
_indicator_suite = build_default_suite()

# ── Pipeline constants ────────────────────────────────────────────────────────
_SMC_TIMEFRAMES  = ["M5", "M15", "H1", "H4"]   # mirrors scanner._SMC_TIMEFRAMES
_OHLCV_COUNT     = 200                           # bars for indicator computation
_SMC_OHLCV_COUNT = 60                            # bars per SMC timeframe

# Pip size per pair family — used for raw spread → pips conversion
_JPY_PAIRS = {"USDJPY", "EURJPY", "GBPJPY"}


def _pip(pair: str) -> float:
    return 0.01 if pair.upper() in _JPY_PAIRS else 0.0001


# ── Session detection ─────────────────────────────────────────────────────────

def _detect_session(utc_hour: int) -> str:
    """Approximate active trading session from UTC hour."""
    if utc_hour >= 22 or utc_hour < 7:
        return "Asian"
    if 7 <= utc_hour < 12:
        return "London"
    if 12 <= utc_hour < 16:
        return "London/New York Overlap"
    if 16 <= utc_hour < 21:
        return "New York"
    return "Sydney"   # 21–22 UTC


# ── Derived market-state helpers ──────────────────────────────────────────────

def _derive_trend(indicators: Dict[str, Any]) -> str:
    """Derive trend from EMA stack alignment (EMA_20 / EMA_50 / EMA_200)."""
    ema20  = indicators.get("EMA_20")
    ema50  = indicators.get("EMA_50")
    ema200 = indicators.get("EMA_200")

    if any(r is None or r.status != "active" for r in [ema20, ema50, ema200]):
        # Fallback to EMA_20 directional signal when higher EMAs are not active
        if ema20 and ema20.status == "active" and ema20.signal:
            if ema20.signal == "buy":
                return "bullish"
            if ema20.signal == "sell":
                return "bearish"
        return "ranging"

    v20, v50, v200 = float(ema20.value), float(ema50.value), float(ema200.value)
    if v20 > v50 > v200:
        return "bullish"
    if v20 < v50 < v200:
        return "bearish"
    return "ranging"


def _derive_volatility(indicators: Dict[str, Any], current_price: float) -> str:
    """
    Classify volatility using the same ATR% thresholds as the scanner:
      ATR% > 0.10 → High
      ATR% > 0.03 → Normal
      ATR% ≤ 0.03 → Low
    """
    atr = indicators.get("ATR_14")
    if atr is None or atr.status != "active":
        return "Normal"
    try:
        atr_val = float(atr.value)
        atr_pct = atr_val / current_price if current_price > 0 else 0.0
        if atr_pct > 0.10:
            return "High"
        if atr_pct > 0.03:
            return "Normal"
        return "Low"
    except (TypeError, ValueError):
        return "Normal"


def _derive_volume(indicators: Dict[str, Any]) -> str:
    """
    Derive volume status from VOLUME_20 indicator.
    vol_ratio > 1.2  → "High Volume"
    vol_ratio > 0.8  → "Normal Volume"
    vol_ratio ≤ 0.8  → "Low Volume"
    """
    vol = indicators.get("VOLUME_20")
    if vol is None or vol.status != "active" or not vol.metadata:
        return "Normal Volume"
    try:
        vol_ratio = float(vol.metadata.get("vol_ratio", 1.0) or 1.0)
    except (TypeError, ValueError):
        return "Normal Volume"
    if vol_ratio > 1.2:
        return "High Volume"
    if vol_ratio > 0.8:
        return "Normal Volume"
    return "Low Volume"


# ── Full evaluation pipeline ──────────────────────────────────────────────────

async def _run_evaluation(pair: str, timeframe: str) -> TradeDecision:
    """
    Orchestrate data fetching → indicator computation → SMC analysis → evaluate().

    Raises HTTPException:
      400 — unsupported timeframe string.
      503 — MT5 unavailable, no OHLCV data returned, or engine fault.
    """
    # 1. Fetch primary OHLCV + live tick concurrently
    try:
        ohlcv, tick = await asyncio.gather(
            _data_service.get_ohlcv(pair, timeframe, _OHLCV_COUNT),
            _data_service.get_tick(pair),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Market data unavailable for {pair}/{timeframe}: {exc}",
        )

    if not ohlcv:
        raise HTTPException(
            status_code=503,
            detail=f"No OHLCV data returned for {pair}/{timeframe}",
        )

    current_price = float(ohlcv[-1]["close"])

    # Raw spread → pips conversion
    raw_spread  = float(tick.get("spread", 0.0) or 0.0)
    spread_pips = raw_spread / _pip(pair) if raw_spread > 0 else 0.0

    # 2. Fetch SMC timeframes concurrently (individual failures tolerated)
    smc_fetches = await asyncio.gather(
        *[
            _data_service.get_ohlcv(pair, tf, _SMC_OHLCV_COUNT)
            for tf in _SMC_TIMEFRAMES
        ],
        return_exceptions=True,
    )
    smc_ohlcv_map: Dict[str, List[Dict[str, Any]]] = {}
    for tf, result in zip(_SMC_TIMEFRAMES, smc_fetches):
        if isinstance(result, Exception):
            logger.debug(
                "AI endpoint: SMC fetch failed for %s/%s — %s", pair, tf, result
            )
        elif result:
            smc_ohlcv_map[tf] = result

    # 3. Compute indicators (200 bars from primary timeframe)
    try:
        indicators = _indicator_suite.compute_all(ohlcv)
    except Exception as exc:
        logger.warning(
            "AI endpoint: indicator computation failed for %s — %s", pair, exc
        )
        indicators = {}

    # 4. SMC multi-timeframe analysis + confluence (both tolerate missing data)
    mtf        = None
    confluence = None
    if smc_ohlcv_map:
        try:
            mtf      = _smc_analyzer.analyze_multi_timeframe(smc_ohlcv_map)
            mtf.pair = pair
        except Exception as exc:
            logger.warning(
                "AI endpoint: MTF analysis failed for %s — %s", pair, exc
            )
        if mtf is not None:
            try:
                confluence = _smc_analyzer.score_confluence(
                    mtf, ohlcv, current_price
                )
            except Exception as exc:
                logger.warning(
                    "AI endpoint: confluence scoring failed for %s — %s", pair, exc
                )

    # 5. Derive market-state fields for ScanResult
    utc_hour     = datetime.now(timezone.utc).hour
    session      = _detect_session(utc_hour)
    trend_status = _derive_trend(indicators)
    volatility   = _derive_volatility(indicators, current_price)
    volume       = _derive_volume(indicators)
    direction    = (
        "buy"    if trend_status == "bullish"
        else ("sell" if trend_status == "bearish" else "ranging")
    )
    score        = float(confluence.score) / 100.0 if confluence else 0.5

    # Derive a human-readable SMC pattern label
    smc_pattern_str = "SMC Analysis"
    if mtf and mtf.dominant_timeframe and mtf.timeframes:
        dom = mtf.timeframes.get(mtf.dominant_timeframe)
        if dom and dom.structures:
            smc_pattern_str = dom.structures[-1].pattern.value

    scan_result = ScanResult(
        pair              = pair,
        direction         = direction,
        score             = score,
        smc_pattern       = smc_pattern_str,
        timeframe         = timeframe,
        trend_status      = trend_status,
        volatility_status = volatility,
        volume_status     = volume,
        current_price     = current_price,
        priority_level    = (
            "HIGH"   if score >= 0.80
            else ("MEDIUM" if score >= 0.60 else "LOW")
        ),
        # Store spread as pips in both the spread field and metadata so the
        # engine can read it from either location.
        spread            = spread_pips,
        session           = session,
        metadata          = {
            "spread_pips":          spread_pips,
            "raw_spread":           raw_spread,
            "smc_confluence_score": confluence.score  if confluence else 0,
            "smc_bias":             (
                confluence.bias.value if confluence else TrendBias.NEUTRAL.value
            ),
        },
    )

    # 6. Run the engine
    try:
        decision = await _engine.evaluate(
            scan_result = scan_result,
            indicators  = indicators,
            mtf         = mtf,
            confluence  = confluence,
            ohlcv       = ohlcv,
        )
    except Exception as exc:
        logger.error(
            "AI engine evaluation failed for %s/%s — %s", pair, timeframe, exc
        )
        raise HTTPException(
            status_code=503,
            detail=f"AI engine evaluation failed: {exc}",
        )

    return decision


# ── Schema conversion ─────────────────────────────────────────────────────────

def _to_schema(decision: TradeDecision) -> TradeDecisionOut:
    """Map TradeDecision dataclass → TradeDecisionOut Pydantic schema."""
    smc_out: Optional[SMCSummaryOut] = None
    if decision.smc_summary is not None:
        s = decision.smc_summary
        smc_out = SMCSummaryOut(
            bias                   = s.bias,
            alignment_score        = s.alignment_score,
            confluence_score       = s.confluence_score,
            dominant_timeframe     = s.dominant_timeframe,
            confirmed_factors      = s.confirmed_factors,
            conflicting_timeframes = s.conflicting_timeframes,
        )

    ind_out = [
        IndicatorSummaryOut(
            name   = i.name,
            signal = i.signal,
            value  = i.value,
            status = i.status,
        )
        for i in decision.indicators_summary
    ]

    return TradeDecisionOut(
        pair               = decision.pair,
        timeframe          = decision.timeframe,
        action             = decision.action.value,
        confidence         = decision.confidence,
        trade_quality      = decision.trade_quality.value,
        trend              = decision.trend,
        smc_summary        = smc_out,
        indicators_summary = ind_out,
        entry_price        = decision.entry_price,
        entry_zone_low     = decision.entry_zone_low,
        entry_zone_high    = decision.entry_zone_high,
        stop_loss          = decision.stop_loss,
        take_profit_1      = decision.take_profit_1,
        take_profit_2      = decision.take_profit_2,
        rejection_reasons  = decision.rejection_reasons,
        evaluated_at       = decision.evaluated_at,
        metadata           = decision.metadata,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/signal", response_model=TradeDecisionOut)
async def get_signal(
    pair:      str = Query(...,   description="Forex pair symbol, e.g. EURUSD"),
    timeframe: str = Query("H1", description="Timeframe: M1 M5 M15 M30 H1 H4 D1"),
) -> TradeDecisionOut:
    """
    Run the AI Decision Engine for a single pair/timeframe on demand.

    Fetches live market data, computes indicators and SMC analysis, and
    returns a TradeDecision — BUY, SELL, or NO_TRADE — with a full audit
    trail of confidence components and rejection reasons.

    Returns 503 when MT5 is unavailable (non-Windows environments).
    """
    decision = await _run_evaluation(pair.upper(), timeframe.upper())
    return _to_schema(decision)


@router.get("/signals", response_model=List[TradeDecisionOut])
async def get_signals(
    pairs:          Optional[str] = Query(
        default=None,
        description=(
            "Comma-separated pair symbols, e.g. EURUSD,GBPUSD. "
            "Defaults to all 10 configured pairs."
        ),
    ),
    timeframe:      str   = Query(
        default="H1",
        description="Timeframe applied to all pairs",
    ),
    min_confidence: float = Query(
        default=settings.AI_MIN_CONFIDENCE,
        description=(
            "Minimum confidence threshold (0.0–1.0). "
            "NO_TRADE results are always excluded regardless of this value."
        ),
    ),
) -> List[TradeDecisionOut]:
    """
    Evaluate multiple pairs concurrently and return only actionable signals.

    NO_TRADE decisions are always excluded.
    Results with confidence below ``min_confidence`` are also excluded.
    Pairs that fail data fetching (e.g. MT5 unavailable) are silently skipped
    and logged at WARNING level.
    """
    pair_list = (
        [p.strip().upper() for p in pairs.split(",") if p.strip()]
        if pairs
        else list(FOREX_PAIRS)
    )

    results_raw = await asyncio.gather(
        *[_run_evaluation(p, timeframe.upper()) for p in pair_list],
        return_exceptions=True,
    )

    out: List[TradeDecisionOut] = []
    for p, result in zip(pair_list, results_raw):
        if isinstance(result, Exception):
            logger.warning(
                "AI signals: evaluation failed for %s — %s", p, result
            )
            continue
        if result.action == TradeAction.NO_TRADE:
            continue
        if result.confidence < min_confidence:
            continue
        out.append(_to_schema(result))

    return out
