"""
Section 7 — AI Decision Engine: unit and integration tests.

Tests 1–15, 18–19: pure unit tests of RuleBasedAIEngine.
  No MT5, no network, no file I/O. Use synthetic pre-computed inputs.

Tests 16–17: API integration tests.
  Require a running Windows MT5 terminal. Skipped automatically on Linux.

Run with:
    cd backend
    python -m pytest tests/test_ai_engine.py -v
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from app.core.config import settings
from app.modules.ai_engine.engine import (
    RuleBasedAIEngine,
    _Q_AVERAGE,
    _Q_EXCELLENT,
    _Q_GOOD,
    _Q_WEAK,
)
from app.modules.ai_engine.types import (
    TradeAction,
    TradeDecision,
    TradeQuality,
)
from app.modules.indicators.interfaces import IndicatorResult
from app.modules.market_scanner.interfaces import ScanResult
from app.modules.smc.interfaces import (
    ConfluenceFactor,
    ConfluenceResult,
    MTFAnalysis,
    SMCPattern,
    SMCStructure,
    TimeframeAnalysis,
    TrendBias,
    Zone,
)

# ── Shared engine instance ────────────────────────────────────────────────────
_engine = RuleBasedAIEngine()


# ── Synthetic data helpers ────────────────────────────────────────────────────

def _ind(
    name:     str,
    signal:   Optional[str] = "neutral",
    value:    Any           = 50.0,
    status:   str           = "active",
    metadata: Optional[Dict] = None,
) -> IndicatorResult:
    return IndicatorResult(
        name      = name,
        value     = value,
        status    = status,
        timestamp = datetime.now(timezone.utc),
        signal    = signal,
        metadata  = metadata or {},
    )


def _scan(
    pair:              str            = "EURUSD",
    timeframe:         str            = "H1",
    direction:         str            = "buy",
    trend_status:      str            = "bullish",
    volatility_status: str            = "Normal",
    volume_status:     str            = "Normal Volume",
    spread:            Optional[float] = 1.0,
    session:           str            = "London",
    current_price:     float          = 1.10000,
    spread_pips:       float          = 1.0,
) -> ScanResult:
    return ScanResult(
        pair              = pair,
        direction         = direction,
        score             = 0.75,
        smc_pattern       = "order_block",
        timeframe         = timeframe,
        trend_status      = trend_status,
        volatility_status = volatility_status,
        volume_status     = volume_status,
        current_price     = current_price,
        priority_level    = "HIGH",
        spread            = spread,
        session           = session,
        metadata          = {"spread_pips": spread_pips},
    )


def _confluence(
    score:             int,
    bias:              TrendBias,
    confirmed_factors: Optional[List[str]] = None,
) -> ConfluenceResult:
    factors = []
    if confirmed_factors:
        for fname in confirmed_factors:
            factors.append(ConfluenceFactor(
                name      = fname,
                score     = 10.0,
                max_score = 10.0,
                confirmed = True,
                reason    = "ok",
            ))
    return ConfluenceResult(
        score           = score,
        bias            = bias,
        factors         = factors,
        confirmed_count = len(factors),
        total_factors   = 8,
    )


def _mtf(
    bias:            TrendBias     = TrendBias.BULLISH,
    alignment_score: float         = 0.8,
    conflicting_tfs: List[str]     = None,
    timeframes:      Dict          = None,
) -> MTFAnalysis:
    return MTFAnalysis(
        bias                   = bias,
        aligned                = alignment_score >= 0.5,
        alignment_score        = alignment_score,
        dominant_timeframe     = "H1",
        conflicting_timeframes = conflicting_tfs or [],
        available_timeframes   = ["M5", "M15", "H1", "H4"],
        missing_timeframes     = [],
        timeframes             = timeframes or {},
        dominant_zones         = [],
    )


def _bullish_indicators() -> Dict[str, IndicatorResult]:
    """All five directional indicators signal BUY; ATR active; ADX trending bullish."""
    return {
        "RSI_14":    _ind("RSI_14",    signal="buy",  value=45.0),
        "MACD":      _ind("MACD",      signal="buy",
                          value={"macd": 0.001, "signal_line": 0.0, "histogram": 0.001}),
        "STOCH_RSI": _ind("STOCH_RSI", signal="buy",  value={"k": 30.0, "d": 25.0}),
        "BB_20":     _ind("BB_20",     signal="buy",
                          value={"upper": 1.105, "middle": 1.100,
                                 "lower": 1.095, "percent_b": 0.2}),
        "VWAP":      _ind("VWAP",      signal="buy",  value=1.101),
        "EMA_20":    _ind("EMA_20",    signal="buy",  value=1.098),
        "EMA_50":    _ind("EMA_50",    signal="neutral", value=1.095),
        "EMA_200":   _ind("EMA_200",   signal="neutral", value=1.090),
        "ATR_14":    _ind("ATR_14",    signal=None,   value=0.001),
        "ADX_14":    _ind("ADX_14",    signal=None,   value=28.0,
                          metadata={"trending": True, "di_bullish": True}),
        "VOLUME_20": _ind("VOLUME_20", signal="buy",  value=100.0,
                          metadata={"vol_ratio": 1.3, "volume_spike": True}),
    }


def _bearish_indicators() -> Dict[str, IndicatorResult]:
    """All five directional indicators signal SELL; ATR active; ADX trending bearish."""
    return {
        "RSI_14":    _ind("RSI_14",    signal="sell", value=72.0),
        "MACD":      _ind("MACD",      signal="sell",
                          value={"macd": -0.001, "signal_line": 0.0, "histogram": -0.001}),
        "STOCH_RSI": _ind("STOCH_RSI", signal="sell", value={"k": 80.0, "d": 82.0}),
        "BB_20":     _ind("BB_20",     signal="sell",
                          value={"upper": 1.105, "middle": 1.100,
                                 "lower": 1.095, "percent_b": 0.85}),
        "VWAP":      _ind("VWAP",      signal="sell", value=1.099),
        "EMA_20":    _ind("EMA_20",    signal="sell", value=1.102),
        "EMA_50":    _ind("EMA_50",    signal="neutral", value=1.105),
        "EMA_200":   _ind("EMA_200",   signal="neutral", value=1.108),
        "ATR_14":    _ind("ATR_14",    signal=None,   value=0.001),
        "ADX_14":    _ind("ADX_14",    signal=None,   value=30.0,
                          metadata={"trending": True, "di_bullish": False}),
        "VOLUME_20": _ind("VOLUME_20", signal="sell", value=100.0,
                          metadata={"vol_ratio": 1.4}),
    }


def _run(coro):
    """Run a coroutine synchronously (avoids pytest-asyncio dependency)."""
    return asyncio.run(coro)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: BUY decision on strong bullish confluence
# ─────────────────────────────────────────────────────────────────────────────

def test_01_buy_decision_strong_bullish():
    result = _run(_engine.evaluate(
        scan_result = _scan(direction="buy", trend_status="bullish"),
        indicators  = _bullish_indicators(),
        mtf         = _mtf(bias=TrendBias.BULLISH, alignment_score=0.85),
        confluence  = _confluence(80, TrendBias.BULLISH,
                                  ["bos_alignment", "order_block"]),
        ohlcv       = [],
    ))
    assert result.action == TradeAction.BUY, f"Expected BUY, got {result.action}"
    assert result.confidence >= settings.AI_MIN_CONFIDENCE
    assert len(result.rejection_reasons) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: SELL decision on strong bearish confluence
# ─────────────────────────────────────────────────────────────────────────────

def test_02_sell_decision_strong_bearish():
    result = _run(_engine.evaluate(
        scan_result = _scan(direction="sell", trend_status="bearish",
                            current_price=1.10000),
        indicators  = _bearish_indicators(),
        mtf         = _mtf(bias=TrendBias.BEARISH, alignment_score=0.80),
        confluence  = _confluence(78, TrendBias.BEARISH),
        ohlcv       = [],
    ))
    assert result.action == TradeAction.SELL, f"Expected SELL, got {result.action}"
    assert result.confidence >= settings.AI_MIN_CONFIDENCE


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: NO_TRADE when confidence < AI_MIN_CONFIDENCE
# ─────────────────────────────────────────────────────────────────────────────

def test_03_no_trade_low_confidence():
    """All-neutral indicators + low SMC + low MTF → confidence below threshold."""
    neutral_inds = {
        name: _ind(name, signal="neutral")
        for name in ["RSI_14", "MACD", "STOCH_RSI", "BB_20", "VWAP"]
    }
    neutral_inds["ATR_14"] = _ind("ATR_14", signal=None, value=0.0005)

    result = _run(_engine.evaluate(
        scan_result = _scan(direction="buy", session="Asian"),
        indicators  = neutral_inds,
        mtf         = _mtf(bias=TrendBias.BULLISH, alignment_score=0.1),
        confluence  = _confluence(10, TrendBias.BULLISH),
        ohlcv       = [],
    ))
    assert result.action == TradeAction.NO_TRADE
    reason_text = " ".join(result.rejection_reasons).lower()
    assert "confidence" in reason_text or "threshold" in reason_text, (
        f"Expected confidence/threshold reason; got: {result.rejection_reasons}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: NO_TRADE when spread exceeds AI_MAX_SPREAD_PIPS
# ─────────────────────────────────────────────────────────────────────────────

def test_04_no_trade_high_spread():
    high_spread = settings.AI_MAX_SPREAD_PIPS + 1.0
    result = _run(_engine.evaluate(
        scan_result = _scan(spread_pips=high_spread),
        indicators  = _bullish_indicators(),
        mtf         = _mtf(bias=TrendBias.BULLISH, alignment_score=0.90),
        confluence  = _confluence(90, TrendBias.BULLISH),
        ohlcv       = [],
    ))
    assert result.action == TradeAction.NO_TRADE
    reason_text = " ".join(result.rejection_reasons).lower()
    assert "spread" in reason_text, (
        f"Expected spread reason; got: {result.rejection_reasons}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: NO_TRADE when directional votes split (1–1–1)
# ─────────────────────────────────────────────────────────────────────────────

def test_05_no_trade_directional_split():
    """SMC=bullish, MTF=neutral, scan=ranging → no 2-of-3 majority."""
    result = _run(_engine.evaluate(
        scan_result = _scan(direction="ranging"),
        indicators  = _bullish_indicators(),
        mtf         = _mtf(bias=TrendBias.NEUTRAL, alignment_score=0.3),
        confluence  = _confluence(70, TrendBias.BULLISH),
        ohlcv       = [],
    ))
    assert result.action == TradeAction.NO_TRADE
    reason_text = " ".join(result.rejection_reasons).lower()
    assert any(kw in reason_text for kw in ("majority", "directional", "agree")), (
        f"Expected directional-majority reason; got: {result.rejection_reasons}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: NO_TRADE when SMC bias is NEUTRAL and MTF alignment < 0.5
# ─────────────────────────────────────────────────────────────────────────────

def test_06_no_trade_neutral_smc_low_mtf():
    result = _run(_engine.evaluate(
        scan_result = _scan(direction="buy"),
        indicators  = _bullish_indicators(),
        mtf         = _mtf(bias=TrendBias.NEUTRAL, alignment_score=0.30),
        confluence  = _confluence(40, TrendBias.NEUTRAL),
        ohlcv       = [],
    ))
    assert result.action == TradeAction.NO_TRADE
    reason_text = " ".join(result.rejection_reasons).lower()
    assert "neutral" in reason_text, (
        f"Expected NEUTRAL SMC reason; got: {result.rejection_reasons}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: NO_TRADE when AI_VOLATILITY_FILTER_ENABLED=True and volatility=High
# ─────────────────────────────────────────────────────────────────────────────

def test_07_no_trade_high_volatility_filter(monkeypatch):
    monkeypatch.setattr(settings, "AI_VOLATILITY_FILTER_ENABLED", True)
    result = _run(_engine.evaluate(
        scan_result = _scan(volatility_status="High"),
        indicators  = _bullish_indicators(),
        mtf         = _mtf(bias=TrendBias.BULLISH, alignment_score=0.85),
        confluence  = _confluence(85, TrendBias.BULLISH),
        ohlcv       = [],
    ))
    assert result.action == TradeAction.NO_TRADE
    reason_text = " ".join(result.rejection_reasons).lower()
    assert "volatility" in reason_text or "high" in reason_text, (
        f"Expected volatility reason; got: {result.rejection_reasons}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: Trade quality = EXCELLENT at confidence ≥ 0.90
# ─────────────────────────────────────────────────────────────────────────────

def test_08_trade_quality_excellent():
    """
    Perfect inputs: SMC 100 (→ 0.35), all BUY indicators (→ 0.30 + ADX bonus),
    MTF 1.0 (→ 0.20), High Volume (→ 0.08), London (→ 0.07) = 1.0 pre-penalty.
    """
    inds = _bullish_indicators()
    inds["VOLUME_20"] = _ind(
        "VOLUME_20", signal="buy", value=100.0, metadata={"vol_ratio": 2.0}
    )
    result = _run(_engine.evaluate(
        scan_result = _scan(volume_status="High Volume", session="London"),
        indicators  = inds,
        mtf         = _mtf(bias=TrendBias.BULLISH, alignment_score=1.0),
        confluence  = _confluence(100, TrendBias.BULLISH),
        ohlcv       = [],
    ))
    assert result.trade_quality == TradeQuality.EXCELLENT, (
        f"Expected EXCELLENT; conf={result.confidence:.3f}, "
        f"quality={result.trade_quality}"
    )
    assert result.confidence >= _Q_EXCELLENT


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: Trade quality = REJECT at confidence < 0.65
# ─────────────────────────────────────────────────────────────────────────────

def test_09_trade_quality_reject():
    """All-neutral indicators + near-zero SMC + no MTF + Sydney + Low Volume."""
    neutral_inds = {
        name: _ind(name, signal="neutral")
        for name in ["RSI_14", "MACD", "STOCH_RSI", "BB_20", "VWAP", "ATR_14"]
    }
    result = _run(_engine.evaluate(
        scan_result = _scan(
            direction     = "buy",
            volume_status = "Low Volume",
            session       = "Sydney",
        ),
        indicators = neutral_inds,
        mtf        = None,
        confluence = _confluence(5, TrendBias.BULLISH),
        ohlcv      = [],
    ))
    # Approximate: SMC=0.05*0.35 + IND=0.5*0.30 + MTF=0 + VOL=0.2*0.08 + SESS=0.2*0.07
    # ≈ 0.018 + 0.15 + 0 + 0.016 + 0.014 = ~0.198 → REJECT
    assert result.trade_quality == TradeQuality.REJECT, (
        f"Expected REJECT; conf={result.confidence:.3f}, "
        f"quality={result.trade_quality}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 10: Confidence very low when mtf=None, confluence=None, all warmup
# ─────────────────────────────────────────────────────────────────────────────

def test_10_confidence_near_zero_full_degradation():
    warmup_inds = {
        name: _ind(name, signal=None, status="warmup")
        for name in ["RSI_14", "MACD", "STOCH_RSI", "BB_20", "VWAP", "ATR_14"]
    }
    result = _run(_engine.evaluate(
        scan_result = _scan(
            direction     = "buy",
            session       = "Sydney",
            volume_status = "Low Volume",
        ),
        indicators = warmup_inds,
        mtf        = None,
        confluence = None,
        ohlcv      = [],
    ))
    # All warmup → ind_component = 0. No confluence → smc=0. No mtf → mtf=0.
    # Only vol (0.016) + sess (0.014) survive → conf ≈ 0.03.
    assert result.confidence < 0.10, (
        f"Expected very low confidence; got {result.confidence:.3f}"
    )
    assert result.action == TradeAction.NO_TRADE


# ─────────────────────────────────────────────────────────────────────────────
# Test 11: ATR-based SL candidate for BUY
# ─────────────────────────────────────────────────────────────────────────────

def test_11_sl_candidate_buy():
    """SL = entry - 1.5 × ATR_14 for BUY decisions."""
    entry_price = 1.10000
    atr_value   = 0.001
    inds = _bullish_indicators()
    inds["ATR_14"] = _ind("ATR_14", signal=None, value=atr_value)

    result = _run(_engine.evaluate(
        scan_result = _scan(current_price=entry_price, direction="buy"),
        indicators  = inds,
        mtf         = _mtf(bias=TrendBias.BULLISH, alignment_score=0.85),
        confluence  = _confluence(80, TrendBias.BULLISH),
        ohlcv       = [],
    ))
    if result.action == TradeAction.BUY:
        assert result.stop_loss is not None, "Expected SL candidate for BUY"
        expected_sl = round(entry_price - 1.5 * atr_value, 5)
        assert abs(result.stop_loss - expected_sl) < 1e-5, (
            f"Expected SL {expected_sl}; got {result.stop_loss}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 12: ATR-based SL candidate for SELL
# ─────────────────────────────────────────────────────────────────────────────

def test_12_sl_candidate_sell():
    """SL = entry + 1.5 × ATR_14 for SELL decisions."""
    entry_price = 1.10000
    atr_value   = 0.001
    inds = _bearish_indicators()
    inds["ATR_14"] = _ind("ATR_14", signal=None, value=atr_value)

    result = _run(_engine.evaluate(
        scan_result = _scan(direction="sell", trend_status="bearish",
                            current_price=entry_price),
        indicators  = inds,
        mtf         = _mtf(bias=TrendBias.BEARISH, alignment_score=0.80),
        confluence  = _confluence(80, TrendBias.BEARISH),
        ohlcv       = [],
    ))
    if result.action == TradeAction.SELL:
        assert result.stop_loss is not None, "Expected SL candidate for SELL"
        expected_sl = round(entry_price + 1.5 * atr_value, 5)
        assert abs(result.stop_loss - expected_sl) < 1e-5, (
            f"Expected SL {expected_sl}; got {result.stop_loss}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 13: TP candidates at 1:1 and 1:2 RR
# ─────────────────────────────────────────────────────────────────────────────

def test_13_tp_candidates_rr():
    result = _run(_engine.evaluate(
        scan_result = _scan(current_price=1.10000, direction="buy"),
        indicators  = _bullish_indicators(),
        mtf         = _mtf(bias=TrendBias.BULLISH, alignment_score=0.85),
        confluence  = _confluence(80, TrendBias.BULLISH),
        ohlcv       = [],
    ))
    if result.action == TradeAction.BUY and result.stop_loss is not None:
        risk = abs(result.entry_price - result.stop_loss)
        assert risk > 0, "Risk should be positive"
        if result.take_profit_1 is not None:
            expected_tp1 = round(result.entry_price + risk * 1.0, 5)
            assert abs(result.take_profit_1 - expected_tp1) < 1e-5, (
                f"TP1 mismatch: expected {expected_tp1}, got {result.take_profit_1}"
            )
        if result.take_profit_2 is not None:
            expected_tp2 = round(result.entry_price + risk * 2.0, 5)
            assert abs(result.take_profit_2 - expected_tp2) < 1e-5, (
                f"TP2 mismatch: expected {expected_tp2}, got {result.take_profit_2}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Test 14: Entry zone extracted from Order Block in MTF
# ─────────────────────────────────────────────────────────────────────────────

def test_14_entry_zone_from_order_block():
    """Entry zone low/high should match the nearest bullish OB below price."""
    ob = SMCStructure(
        pattern   = SMCPattern.ORDER_BLOCK,
        pair      = "EURUSD",
        timeframe = "M15",
        zone      = Zone.DISCOUNT,
        price_low = 1.0990,
        price_high= 1.0995,
        direction = "bullish",
        strength  = 0.8,
    )
    tf_m15 = TimeframeAnalysis(
        timeframe     = "M15",
        structures    = [],
        order_blocks  = [ob],
        fvgs          = [],
        liquidity     = [],
        supply_demand = [],
        bias          = TrendBias.BULLISH,
    )
    custom_mtf = _mtf(
        bias            = TrendBias.BULLISH,
        alignment_score = 0.85,
        timeframes      = {"M15": tf_m15},
    )
    result = _run(_engine.evaluate(
        scan_result = _scan(current_price=1.10000, direction="buy"),
        indicators  = _bullish_indicators(),
        mtf         = custom_mtf,
        confluence  = _confluence(80, TrendBias.BULLISH),
        ohlcv       = [],
    ))
    if result.action == TradeAction.BUY:
        assert result.entry_zone_low  is not None, "Expected entry zone from OB"
        assert result.entry_zone_high is not None, "Expected entry zone from OB"
        assert abs(result.entry_zone_low  - 1.0990) < 1e-5
        assert abs(result.entry_zone_high - 1.0995) < 1e-5


# ─────────────────────────────────────────────────────────────────────────────
# Test 15: Graceful degradation — 3 of 5 indicators in warmup
# ─────────────────────────────────────────────────────────────────────────────

def test_15_graceful_degradation_partial_warmup():
    """Engine must return a valid TradeDecision even with only 2 active indicators."""
    partial_inds = {
        "RSI_14":    _ind("RSI_14",    signal="buy",  status="active"),
        "MACD":      _ind("MACD",      signal="buy",  status="active"),
        "STOCH_RSI": _ind("STOCH_RSI", signal=None,   status="warmup"),
        "BB_20":     _ind("BB_20",     signal=None,   status="warmup"),
        "VWAP":      _ind("VWAP",      signal=None,   status="warmup"),
        "ATR_14":    _ind("ATR_14",    signal=None,   value=0.001, status="active"),
    }
    result = _run(_engine.evaluate(
        scan_result = _scan(direction="buy"),
        indicators  = partial_inds,
        mtf         = _mtf(bias=TrendBias.BULLISH, alignment_score=0.7),
        confluence  = _confluence(60, TrendBias.BULLISH),
        ohlcv       = [],
    ))
    assert isinstance(result, TradeDecision), (
        "Engine must return a TradeDecision even with partial indicator data"
    )
    assert result.pair == "EURUSD"
    # No exception raised → graceful degradation confirmed


# ─────────────────────────────────────────────────────────────────────────────
# Tests 16 & 17: API integration (skipped without MT5)
# ─────────────────────────────────────────────────────────────────────────────

try:
    from app.modules.mt5_integration.base import _MT5_AVAILABLE as _MT5_AVAIL
except (ImportError, AttributeError):
    _MT5_AVAIL = False


@pytest.mark.skipif(not _MT5_AVAIL, reason="Requires Windows MT5 terminal")
def test_16_api_signal_endpoint():
    import httpx
    resp = httpx.get(
        "http://localhost:8000/api/v1/ai/signal?pair=EURUSD&timeframe=H1",
        timeout=30,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "action" in data
    assert data["action"] in ("buy", "sell", "no_trade")
    assert "confidence" in data
    assert "tradeQuality" in data or "trade_quality" in data


@pytest.mark.skipif(not _MT5_AVAIL, reason="Requires Windows MT5 terminal")
def test_17_api_signals_endpoint():
    import httpx
    resp = httpx.get(
        "http://localhost:8000/api/v1/ai/signals?pairs=EURUSD,GBPUSD&timeframe=H1",
        timeout=60,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    for item in data:
        # NO_TRADE should never appear in the signals list
        assert item["action"] in ("buy", "sell"), (
            f"Unexpected action {item['action']!r} in /ai/signals response"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 18: AI_MIN_CONFIDENCE read from config, not hardcoded
# ─────────────────────────────────────────────────────────────────────────────

def test_18_threshold_from_config(monkeypatch):
    """Raising AI_MIN_CONFIDENCE above 1.0 must force NO_TRADE on any setup."""
    monkeypatch.setattr(settings, "AI_MIN_CONFIDENCE", 1.01)
    result = _run(_engine.evaluate(
        scan_result = _scan(direction="buy"),
        indicators  = _bullish_indicators(),
        mtf         = _mtf(bias=TrendBias.BULLISH, alignment_score=1.0),
        confluence  = _confluence(100, TrendBias.BULLISH),
        ohlcv       = [],
    ))
    assert result.action == TradeAction.NO_TRADE, (
        "With AI_MIN_CONFIDENCE=1.01, every decision must be NO_TRADE"
    )
    reason_text = " ".join(result.rejection_reasons).lower()
    assert "confidence" in reason_text or "threshold" in reason_text


# ─────────────────────────────────────────────────────────────────────────────
# Test 19: rejection_reasons is non-empty for every NO_TRADE decision
# ─────────────────────────────────────────────────────────────────────────────

def test_19_no_trade_always_has_rejection_reasons():
    """Every NO_TRADE result must carry at least one human-readable reason."""
    # Scenario: split vote (scan=ranging, MTF=neutral, SMC=neutral)
    result = _run(_engine.evaluate(
        scan_result = _scan(direction="ranging"),
        indicators  = {
            name: _ind(name, signal="neutral")
            for name in ["RSI_14", "MACD", "STOCH_RSI", "BB_20", "VWAP"]
        },
        mtf        = _mtf(bias=TrendBias.NEUTRAL, alignment_score=0.2),
        confluence = _confluence(20, TrendBias.NEUTRAL),
        ohlcv      = [],
    ))
    assert result.action == TradeAction.NO_TRADE
    assert len(result.rejection_reasons) > 0, (
        "NO_TRADE must always include at least one rejection reason"
    )
    for reason in result.rejection_reasons:
        assert isinstance(reason, str) and len(reason) > 0, (
            f"All rejection reasons must be non-empty strings; got {reason!r}"
        )
