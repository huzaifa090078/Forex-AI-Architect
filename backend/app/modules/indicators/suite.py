"""
Technical Indicators — pre-built suite factory.

build_default_suite() constructs an IndicatorSuite loaded with the full set
of production indicators used across all consumers:

  Consumer          Indicators used
  ──────────────────────────────────────────────────────────────────────────
  MarketScanner     EMA_20, EMA_50, RSI_14, ATR_14, ADX_14, MACD, BB_20
  SMC Engine        EMA_20, EMA_50, EMA_200, ATR_14, ADX_14
  AI Engine         All 13 indicators (full feature vector)
  Dashboard         RSI_14, MACD, BB_20, STOCH_RSI, VOLUME_20, VWAP

Usage
─────
    from app.modules.indicators.suite import build_default_suite

    suite = build_default_suite()

    # Compute all indicators
    results = suite.compute_all(ohlcv_bars)

    # Compute a specific subset by name
    results = suite.compute_all(ohlcv_bars, indicators=["EMA_20", "RSI_14", "ATR_14"])

    # Access individual result
    rsi = results["RSI_14"]
    print(rsi.value)   # e.g. 62.4
    print(rsi.signal)  # "neutral"

All indicator names registered here are the canonical keys callers must use
when requesting a subset via compute_all(indicators=[...]).
"""

from app.modules.indicators.base import IndicatorSuite
from app.modules.indicators.indicators import (
    EMAIndicator,
    SMAIndicator,
    RSIIndicator,
    MACDIndicator,
    ATRIndicator,
    BollingerBandsIndicator,
    VWAPIndicator,
    ADXIndicator,
    StochasticRSIIndicator,
    VolumeAnalysisIndicator,
)


def build_default_suite() -> IndicatorSuite:
    """
    Construct and return a fully-loaded IndicatorSuite.

    Registered indicators (13 total):

    Trend
    ─────
    EMA_20   — fast trend (20-bar EMA)
    EMA_50   — mid trend (50-bar EMA); 20/50 crossover is a primary signal
    EMA_200  — long-term trend bias (200-bar EMA)
    SMA_20   — simple trend baseline alongside EMA_20
    SMA_50   — simple trend baseline alongside EMA_50

    Momentum
    ────────
    RSI_14      — overbought/oversold; Wilder-smoothed (standard)
    MACD        — 12/26/9; crossover and histogram direction
    STOCH_RSI   — 14/14/3/3; RSI-based stochastic for refined entry timing

    Volatility
    ──────────
    ATR_14   — absolute volatility in price units; used for stop-loss sizing
    BB_20    — 20-bar / 2σ Bollinger Bands; squeeze and breakout detection

    Volume / Price-Volume
    ─────────────────────
    VWAP        — cumulative session VWAP; institutional value area reference
    VOLUME_20   — OBV trend + 20-bar volume ratio (confirms directional moves)

    Trend Strength
    ──────────────
    ADX_14   — Wilder ADX with +DI/-DI; separates trending from ranging markets

    Returns:
        IndicatorSuite with all 13 indicators registered and ready to compute.
    """
    suite = IndicatorSuite()

    # ── Trend ─────────────────────────────────────────────────────────────────
    suite.register(EMAIndicator(period=20))
    suite.register(EMAIndicator(period=50))
    suite.register(EMAIndicator(period=200))
    suite.register(SMAIndicator(period=20))
    suite.register(SMAIndicator(period=50))

    # ── Momentum ──────────────────────────────────────────────────────────────
    suite.register(RSIIndicator(period=14))
    suite.register(MACDIndicator(fast=12, slow=26, signal_period=9))
    suite.register(StochasticRSIIndicator(
        rsi_period=14, stoch_period=14, k_period=3, d_period=3
    ))

    # ── Volatility ────────────────────────────────────────────────────────────
    suite.register(ATRIndicator(period=14))
    suite.register(BollingerBandsIndicator(period=20, std_dev=2.0))

    # ── Volume / Price-Volume ─────────────────────────────────────────────────
    suite.register(VWAPIndicator())
    suite.register(VolumeAnalysisIndicator(period=20))

    # ── Trend Strength ────────────────────────────────────────────────────────
    suite.register(ADXIndicator(period=14))

    return suite


# ── Canonical indicator name constants ────────────────────────────────────────
# Import these in consuming modules to avoid hard-coded strings.

EMA_20     = "EMA_20"
EMA_50     = "EMA_50"
EMA_200    = "EMA_200"
SMA_20     = "SMA_20"
SMA_50     = "SMA_50"
RSI_14     = "RSI_14"
MACD       = "MACD"
STOCH_RSI  = "STOCH_RSI"
ATR_14     = "ATR_14"
BB_20      = "BB_20"
VWAP       = "VWAP"
VOLUME_20  = "VOLUME_20"
ADX_14     = "ADX_14"
