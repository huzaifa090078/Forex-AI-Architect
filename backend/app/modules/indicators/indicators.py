"""
Technical Indicators — concrete IIndicator implementations.

Each class extends BaseIndicator, accepts configuration parameters in its
constructor, and implements compute(ohlcv) by:
  1. Extracting arrays via calculations.extract_arrays().
  2. Delegating the math to the corresponding calc_* function.
  3. Reading the last non-NaN value(s) from the result array(s).
  4. Constructing and returning an IndicatorResult.

Signal convention:
  "buy"     — indicator condition favours long bias.
  "sell"    — indicator condition favours short bias.
  "neutral" — indicator is active but shows no clear directional bias.
  None      — indicator does not produce a directional signal (e.g. ATR, ADX).

All compute() implementations raise ValueError (propagated from calculations)
when the ohlcv list is shorter than the indicator's minimum bar requirement.
Callers that want to tolerate short data should catch ValueError themselves.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from app.modules.indicators.base import BaseIndicator
from app.modules.indicators.interfaces import IndicatorResult
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


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _last_valid(arr: np.ndarray) -> Optional[float]:
    """Return the last non-NaN value in `arr`, or None if all are NaN."""
    valid = arr[~np.isnan(arr)]
    return float(valid[-1]) if len(valid) > 0 else None


def _round(value: Optional[float], decimals: int = 6) -> Optional[float]:
    if value is None:
        return None
    return round(value, decimals)


# ─────────────────────────────────────────────────────────────────────────────
# Trend indicators
# ─────────────────────────────────────────────────────────────────────────────

class EMAIndicator(BaseIndicator):
    """
    Exponential Moving Average.

    Name pattern: 'EMA_{period}'  e.g. 'EMA_20', 'EMA_50', 'EMA_200'.

    IndicatorResult.value : float — last valid EMA value.
    IndicatorResult.signal: None  — EMA is structural; signal requires price context.
    IndicatorResult.metadata:
      'period'     — configured period
      'series_len' — number of valid (non-NaN) EMA values computed
    """

    def __init__(self, period: int = 20) -> None:
        super().__init__(f"EMA_{period}")
        self._period = period

    def compute(self, ohlcv: List[Dict[str, Any]]) -> IndicatorResult:
        _, _, _, closes, _ = extract_arrays(ohlcv)
        arr   = calc_ema(closes, self._period)
        value = _last_valid(arr)
        valid = int(np.sum(~np.isnan(arr)))
        return IndicatorResult(
            name=self.name,
            value=_round(value),
            signal=None,
            metadata={"period": self._period, "series_len": valid},
        )


class SMAIndicator(BaseIndicator):
    """
    Simple Moving Average.

    Name pattern: 'SMA_{period}'  e.g. 'SMA_20', 'SMA_50'.

    IndicatorResult.value : float — last valid SMA value.
    IndicatorResult.signal: None  — structural; no directional signal.
    IndicatorResult.metadata:
      'period'     — configured period
      'series_len' — number of valid SMA values
    """

    def __init__(self, period: int = 50) -> None:
        super().__init__(f"SMA_{period}")
        self._period = period

    def compute(self, ohlcv: List[Dict[str, Any]]) -> IndicatorResult:
        _, _, _, closes, _ = extract_arrays(ohlcv)
        arr   = calc_sma(closes, self._period)
        value = _last_valid(arr)
        valid = int(np.sum(~np.isnan(arr)))
        return IndicatorResult(
            name=self.name,
            value=_round(value),
            signal=None,
            metadata={"period": self._period, "series_len": valid},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Momentum indicators
# ─────────────────────────────────────────────────────────────────────────────

class RSIIndicator(BaseIndicator):
    """
    Relative Strength Index (Wilder-smoothed).

    Name pattern: 'RSI_{period}'  e.g. 'RSI_14'.

    IndicatorResult.value : float — last RSI value (0-100).
    IndicatorResult.signal:
      'buy'     — RSI < oversold_level  (default 30)
      'sell'    — RSI > overbought_level (default 70)
      'neutral' — otherwise
    IndicatorResult.metadata:
      'period'          — configured period
      'overbought'      — overbought threshold used for signal
      'oversold'        — oversold threshold used for signal
      'prev_rsi'        — second-to-last RSI value (for momentum change detection)
    """

    def __init__(
        self,
        period:      int   = 14,
        overbought:  float = 70.0,
        oversold:    float = 30.0,
    ) -> None:
        super().__init__(f"RSI_{period}")
        self._period     = period
        self._overbought = overbought
        self._oversold   = oversold

    def compute(self, ohlcv: List[Dict[str, Any]]) -> IndicatorResult:
        _, _, _, closes, _ = extract_arrays(ohlcv)
        arr  = calc_rsi(closes, self._period)

        valid_vals = arr[~np.isnan(arr)]
        value      = float(valid_vals[-1]) if len(valid_vals) > 0 else None
        prev_rsi   = float(valid_vals[-2]) if len(valid_vals) > 1 else None

        if value is None:
            signal = "neutral"
        elif value < self._oversold:
            signal = "buy"
        elif value > self._overbought:
            signal = "sell"
        else:
            signal = "neutral"

        return IndicatorResult(
            name=self.name,
            value=_round(value, 2),
            signal=signal,
            metadata={
                "period":     self._period,
                "overbought": self._overbought,
                "oversold":   self._oversold,
                "prev_rsi":   _round(prev_rsi, 2),
            },
        )


class MACDIndicator(BaseIndicator):
    """
    Moving Average Convergence Divergence.

    Name: 'MACD'.

    IndicatorResult.value : dict with keys:
      'line'      — float : MACD line (EMA_fast - EMA_slow)
      'signal'    — float : Signal line (EMA of MACD line)
      'histogram' — float : line - signal
    IndicatorResult.signal:
      'buy'     — histogram > 0 (MACD line above signal line)
      'sell'    — histogram < 0 (MACD line below signal line)
      'neutral' — histogram == 0 or data unavailable
    IndicatorResult.metadata:
      'fast', 'slow', 'signal_period' — configured periods
      'crossed_up'   — bool: histogram turned positive on the last bar
      'crossed_down' — bool: histogram turned negative on the last bar
    """

    def __init__(
        self,
        fast:          int = 12,
        slow:          int = 26,
        signal_period: int = 9,
    ) -> None:
        super().__init__("MACD")
        self._fast          = fast
        self._slow          = slow
        self._signal_period = signal_period

    def compute(self, ohlcv: List[Dict[str, Any]]) -> IndicatorResult:
        _, _, _, closes, _ = extract_arrays(ohlcv)
        result = calc_macd(closes, self._fast, self._slow, self._signal_period)

        hist = result["histogram"]
        macd = result["macd"]
        sig  = result["signal"]

        last_hist = _last_valid(hist)
        last_macd = _last_valid(macd)
        last_sig  = _last_valid(sig)

        # Crossover detection: compare last two histogram values
        valid_hist = hist[~np.isnan(hist)]
        crossed_up   = False
        crossed_down = False
        if len(valid_hist) >= 2:
            crossed_up   = valid_hist[-2] <= 0.0 and valid_hist[-1] > 0.0
            crossed_down = valid_hist[-2] >= 0.0 and valid_hist[-1] < 0.0

        if last_hist is None:
            direction = "neutral"
        elif last_hist > 0.0:
            direction = "buy"
        elif last_hist < 0.0:
            direction = "sell"
        else:
            direction = "neutral"

        return IndicatorResult(
            name=self.name,
            value={
                "line":      _round(last_macd),
                "signal":    _round(last_sig),
                "histogram": _round(last_hist),
            },
            signal=direction,
            metadata={
                "fast":          self._fast,
                "slow":          self._slow,
                "signal_period": self._signal_period,
                "crossed_up":    crossed_up,
                "crossed_down":  crossed_down,
            },
        )


class StochasticRSIIndicator(BaseIndicator):
    """
    Stochastic RSI oscillator.

    Name: 'STOCH_RSI'.

    IndicatorResult.value : dict with keys:
      'k' — float : %K line (0-100), smoothed stochastic of RSI
      'd' — float : %D line (0-100), signal line (SMA of %K)
    IndicatorResult.signal:
      'buy'     — %K < 20  (oversold)
      'sell'    — %K > 80  (overbought)
      'neutral' — otherwise
    IndicatorResult.metadata:
      'rsi_period', 'stoch_period', 'k_period', 'd_period'
      'k_crossed_up'   — bool: %K crossed above %D on last bar
      'k_crossed_down' — bool: %K crossed below %D on last bar
    """

    def __init__(
        self,
        rsi_period:   int = 14,
        stoch_period: int = 14,
        k_period:     int = 3,
        d_period:     int = 3,
    ) -> None:
        super().__init__("STOCH_RSI")
        self._rsi_period   = rsi_period
        self._stoch_period = stoch_period
        self._k_period     = k_period
        self._d_period     = d_period

    def compute(self, ohlcv: List[Dict[str, Any]]) -> IndicatorResult:
        _, _, _, closes, _ = extract_arrays(ohlcv)
        result = calc_stochastic_rsi(
            closes,
            self._rsi_period,
            self._stoch_period,
            self._k_period,
            self._d_period,
        )

        k_arr = result["k"]
        d_arr = result["d"]

        last_k = _last_valid(k_arr)
        last_d = _last_valid(d_arr)

        # Crossover detection
        valid_k = k_arr[~np.isnan(k_arr)]
        valid_d = d_arr[~np.isnan(d_arr)]
        crossed_up   = False
        crossed_down = False
        if len(valid_k) >= 2 and len(valid_d) >= 2:
            crossed_up   = valid_k[-2] <= valid_d[-2] and valid_k[-1] > valid_d[-1]
            crossed_down = valid_k[-2] >= valid_d[-2] and valid_k[-1] < valid_d[-1]

        if last_k is None:
            signal = "neutral"
        elif last_k < 20.0:
            signal = "buy"
        elif last_k > 80.0:
            signal = "sell"
        else:
            signal = "neutral"

        return IndicatorResult(
            name=self.name,
            value={"k": _round(last_k, 2), "d": _round(last_d, 2)},
            signal=signal,
            metadata={
                "rsi_period":    self._rsi_period,
                "stoch_period":  self._stoch_period,
                "k_period":      self._k_period,
                "d_period":      self._d_period,
                "k_crossed_up":  crossed_up,
                "k_crossed_down": crossed_down,
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# Volatility indicators
# ─────────────────────────────────────────────────────────────────────────────

class ATRIndicator(BaseIndicator):
    """
    Average True Range (Wilder-smoothed).

    Name pattern: 'ATR_{period}'  e.g. 'ATR_14'.

    IndicatorResult.value : float — last ATR value (in price units).
    IndicatorResult.signal: None  — ATR is a volatility measure, not directional.
    IndicatorResult.metadata:
      'period'      — configured period
      'atr_pct'     — ATR as a percentage of the last close price
                      (useful for comparing volatility across pairs)
    """

    def __init__(self, period: int = 14) -> None:
        super().__init__(f"ATR_{period}")
        self._period = period

    def compute(self, ohlcv: List[Dict[str, Any]]) -> IndicatorResult:
        _, highs, lows, closes, _ = extract_arrays(ohlcv)
        arr   = calc_atr(highs, lows, closes, self._period)
        value = _last_valid(arr)

        last_close = float(closes[-1]) if len(closes) > 0 else 0.0
        atr_pct    = (value / last_close * 100.0) if (value and last_close > 0.0) else None

        return IndicatorResult(
            name=self.name,
            value=_round(value),
            signal=None,
            metadata={
                "period":  self._period,
                "atr_pct": _round(atr_pct, 4),
            },
        )


class BollingerBandsIndicator(BaseIndicator):
    """
    Bollinger Bands.

    Name pattern: 'BB_{period}'  e.g. 'BB_20'.

    IndicatorResult.value : dict with keys:
      'upper'     — float : upper band
      'middle'    — float : middle band (SMA)
      'lower'     — float : lower band
      'bandwidth' — float : (upper-lower)/middle × 100 (% squeeze measure)
      'percent_b' — float : (close-lower)/(upper-lower); 0=at lower, 1=at upper
    IndicatorResult.signal:
      'buy'     — price at or below lower band (percent_b ≤ 0.0)
      'sell'    — price at or above upper band (percent_b ≥ 1.0)
      'neutral' — price within the bands
    IndicatorResult.metadata:
      'period', 'std_dev' — configuration
      'squeeze' — bool: bandwidth in lowest 20% of recent 50-bar range
                  (True = BB squeeze, precursor to expansion)
    """

    def __init__(self, period: int = 20, std_dev: float = 2.0) -> None:
        super().__init__(f"BB_{period}")
        self._period  = period
        self._std_dev = std_dev

    def compute(self, ohlcv: List[Dict[str, Any]]) -> IndicatorResult:
        _, _, _, closes, _ = extract_arrays(ohlcv)
        result = calc_bollinger_bands(closes, self._period, self._std_dev)

        upper     = _last_valid(result["upper"])
        middle    = _last_valid(result["middle"])
        lower     = _last_valid(result["lower"])
        bandwidth = _last_valid(result["bandwidth"])
        pct_b     = _last_valid(result["percent_b"])

        if pct_b is None:
            signal = "neutral"
        elif pct_b <= 0.0:
            signal = "buy"
        elif pct_b >= 1.0:
            signal = "sell"
        else:
            signal = "neutral"

        # Squeeze detection: current bandwidth vs recent 50-bar range of bandwidth
        bw_arr       = result["bandwidth"]
        valid_bw     = bw_arr[~np.isnan(bw_arr)]
        squeeze      = False
        lookback     = min(50, len(valid_bw))
        if lookback > 5 and bandwidth is not None:
            recent  = valid_bw[-lookback:]
            bw_lo   = float(np.min(recent))
            bw_hi   = float(np.max(recent))
            bw_rng  = bw_hi - bw_lo
            if bw_rng > 0.0:
                squeeze = bandwidth <= (bw_lo + 0.2 * bw_rng)

        return IndicatorResult(
            name=self.name,
            value={
                "upper":     _round(upper),
                "middle":    _round(middle),
                "lower":     _round(lower),
                "bandwidth": _round(bandwidth, 4),
                "percent_b": _round(pct_b, 4),
            },
            signal=signal,
            metadata={
                "period":  self._period,
                "std_dev": self._std_dev,
                "squeeze": squeeze,
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# Volume / Price-Volume indicators
# ─────────────────────────────────────────────────────────────────────────────

class VWAPIndicator(BaseIndicator):
    """
    Cumulative VWAP over the supplied bar window.

    Name: 'VWAP'.

    IndicatorResult.value : float — VWAP of the last bar.
    IndicatorResult.signal:
      'buy'     — last close > VWAP (price above value area)
      'sell'    — last close < VWAP (price below value area)
      'neutral' — close == VWAP
    IndicatorResult.metadata:
      'last_close' — the close price used for signal determination
      'deviation'  — (close - VWAP) / VWAP × 100 (percentage distance)
      'zero_volume_fallback' — True if all volumes were zero (typical-price mean used)
    """

    def __init__(self) -> None:
        super().__init__("VWAP")

    def compute(self, ohlcv: List[Dict[str, Any]]) -> IndicatorResult:
        _, highs, lows, closes, volumes = extract_arrays(ohlcv)
        arr   = calc_vwap(highs, lows, closes, volumes)
        value = _last_valid(arr)

        last_close = float(closes[-1])
        zero_vol   = bool(np.all(volumes == 0.0))

        if value is None:
            signal    = "neutral"
            deviation = None
        elif last_close > value:
            signal    = "buy"
            deviation = _round((last_close - value) / value * 100.0, 4) if value != 0 else None
        elif last_close < value:
            signal    = "sell"
            deviation = _round((last_close - value) / value * 100.0, 4) if value != 0 else None
        else:
            signal    = "neutral"
            deviation = 0.0

        return IndicatorResult(
            name=self.name,
            value=_round(value),
            signal=signal,
            metadata={
                "last_close":          _round(last_close),
                "deviation":           deviation,
                "zero_volume_fallback": zero_vol,
            },
        )


class VolumeAnalysisIndicator(BaseIndicator):
    """
    Volume analysis: OBV trend and normalised volume ratio.

    Name pattern: 'VOLUME_{period}'  e.g. 'VOLUME_20'.

    IndicatorResult.value : dict with keys:
      'obv'       — float : current On-Balance Volume
      'vol_ratio' — float : current volume / SMA(volume, period)
    IndicatorResult.signal:
      'buy'     — OBV rising AND volume_ratio > 1.0 (bullish volume pressure)
      'sell'    — OBV falling AND volume_ratio > 1.0 (bearish volume pressure)
      'neutral' — OBV flat or volume below average
    IndicatorResult.metadata:
      'period'       — configured SMA period for volume normalisation
      'obv_rising'   — bool: last OBV > 20-bar OBV SMA
      'high_volume'  — bool: vol_ratio > 1.5 (significantly above average)
    """

    def __init__(self, period: int = 20) -> None:
        super().__init__(f"VOLUME_{period}")
        self._period = period

    def compute(self, ohlcv: List[Dict[str, Any]]) -> IndicatorResult:
        _, _, _, closes, volumes = extract_arrays(ohlcv)
        result = calc_volume_analysis(closes, volumes, self._period)

        obv       = result["obv"]
        vol_ratio = result["vol_ratio"]

        last_obv   = _last_valid(obv)
        last_ratio = _last_valid(vol_ratio)

        # OBV trend: compare last OBV to its own SMA over min(20, valid_len) bars
        obv_rising = False
        valid_obv  = obv[~np.isnan(obv)]
        if len(valid_obv) >= 2:
            lookback   = min(20, len(valid_obv))
            obv_sma    = float(np.mean(valid_obv[-lookback:]))
            obv_rising = float(valid_obv[-1]) > obv_sma

        high_volume = (last_ratio is not None) and (last_ratio > 1.5)

        # Signal: directional OBV move confirmed by above-average volume
        if last_obv is None or last_ratio is None:
            signal = "neutral"
        elif obv_rising and last_ratio > 1.0:
            signal = "buy"
        elif not obv_rising and last_ratio > 1.0:
            signal = "sell"
        else:
            signal = "neutral"

        return IndicatorResult(
            name=self.name,
            value={
                "obv":       _round(last_obv, 2),
                "vol_ratio": _round(last_ratio, 4),
            },
            signal=signal,
            metadata={
                "period":      self._period,
                "obv_rising":  obv_rising,
                "high_volume": high_volume,
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# Trend Strength
# ─────────────────────────────────────────────────────────────────────────────

class ADXIndicator(BaseIndicator):
    """
    Average Directional Index — measures trend *strength*, not direction.

    Name pattern: 'ADX_{period}'  e.g. 'ADX_14'.

    IndicatorResult.value : dict with keys:
      'adx'      — float : ADX value (0-100; > 25 = trending)
      'plus_di'  — float : +DI (bullish directional strength)
      'minus_di' — float : -DI (bearish directional strength)
    IndicatorResult.signal: None — ADX measures strength, not direction.
    IndicatorResult.metadata:
      'period'      — configured period
      'trending'    — bool: ADX > 25
      'strong_trend'— bool: ADX > 50
      'di_bullish'  — bool: +DI > -DI (dominant directional bias)
    """

    def __init__(self, period: int = 14) -> None:
        super().__init__(f"ADX_{period}")
        self._period = period

    def compute(self, ohlcv: List[Dict[str, Any]]) -> IndicatorResult:
        _, highs, lows, closes, _ = extract_arrays(ohlcv)
        result = calc_adx(highs, lows, closes, self._period)

        adx_val  = _last_valid(result["adx"])
        plus_di  = _last_valid(result["plus_di"])
        minus_di = _last_valid(result["minus_di"])

        trending     = adx_val is not None and adx_val > 25.0
        strong_trend = adx_val is not None and adx_val > 50.0
        di_bullish   = (plus_di is not None and minus_di is not None
                        and plus_di > minus_di)

        return IndicatorResult(
            name=self.name,
            value={
                "adx":      _round(adx_val, 2),
                "plus_di":  _round(plus_di, 2),
                "minus_di": _round(minus_di, 2),
            },
            signal=None,
            metadata={
                "period":       self._period,
                "trending":     trending,
                "strong_trend": strong_trend,
                "di_bullish":   di_bullish,
            },
        )
