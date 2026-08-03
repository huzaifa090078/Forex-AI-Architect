# Technical Indicators — public API
#
# Preferred import patterns for consuming modules:
#
#   # 1. Ready-to-use suite (most common)
#   from app.modules.indicators import build_default_suite
#   suite = build_default_suite()
#   results = suite.compute_all(ohlcv_bars)
#
#   # 2. Individual indicator class (for custom suites or direct use)
#   from app.modules.indicators import EMAIndicator, RSIIndicator
#   ema = EMAIndicator(period=50)
#   result = ema.compute(ohlcv_bars)
#
#   # 3. Raw calculation functions (for AI feature extraction)
#   from app.modules.indicators import calc_ema, calc_rsi, extract_arrays
#   opens, highs, lows, closes, volumes = extract_arrays(ohlcv_bars)
#   ema_arr = calc_ema(closes, period=20)
#
#   # 4. Canonical name constants (avoids hard-coded strings)
#   from app.modules.indicators import EMA_20, RSI_14, ATR_14
#   results = suite.compute_all(ohlcv_bars, indicators=[EMA_20, RSI_14, ATR_14])

# ── Interfaces & base classes ─────────────────────────────────────────────────
from app.modules.indicators.interfaces import (
    IndicatorResult,
    IIndicator,
    IIndicatorSuite,
)
from app.modules.indicators.base import (
    BaseIndicator,
    IndicatorSuite,
)

# ── Concrete indicator classes ─────────────────────────────────────────────────
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

# ── Suite factory ─────────────────────────────────────────────────────────────
from app.modules.indicators.suite import build_default_suite

# ── Canonical indicator name constants ────────────────────────────────────────
from app.modules.indicators.suite import (
    EMA_20,
    EMA_50,
    EMA_200,
    SMA_20,
    SMA_50,
    RSI_14,
    MACD,
    STOCH_RSI,
    ATR_14,
    BB_20,
    VWAP,
    VOLUME_20,
    ADX_14,
)

# ── Pure calculation functions (for direct use by AI Engine, etc.) ────────────
from app.modules.indicators.calculations import (
    extract_arrays,
    calc_ema,
    calc_sma,
    calc_rsi,
    calc_macd,
    calc_atr,
    calc_bollinger_bands,
    calc_vwap,
    calc_adx,
    calc_stochastic_rsi,
    calc_volume_analysis,
)

__all__ = [
    # Interfaces
    "IndicatorResult",
    "IIndicator",
    "IIndicatorSuite",
    # Base
    "BaseIndicator",
    "IndicatorSuite",
    # Concrete indicators
    "EMAIndicator",
    "SMAIndicator",
    "RSIIndicator",
    "MACDIndicator",
    "ATRIndicator",
    "BollingerBandsIndicator",
    "VWAPIndicator",
    "ADXIndicator",
    "StochasticRSIIndicator",
    "VolumeAnalysisIndicator",
    # Suite factory
    "build_default_suite",
    # Name constants
    "EMA_20", "EMA_50", "EMA_200",
    "SMA_20", "SMA_50",
    "RSI_14",
    "MACD",
    "STOCH_RSI",
    "ATR_14",
    "BB_20",
    "VWAP",
    "VOLUME_20",
    "ADX_14",
    # Calculation functions
    "extract_arrays",
    "calc_ema",
    "calc_sma",
    "calc_rsi",
    "calc_macd",
    "calc_atr",
    "calc_bollinger_bands",
    "calc_vwap",
    "calc_adx",
    "calc_stochastic_rsi",
    "calc_volume_analysis",
]
