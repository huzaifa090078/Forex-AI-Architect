"""
Technical Indicators — pure numpy calculation functions.

Stateless functions that operate on arrays extracted from MarketDataService
OHLCV bars.  No I/O, no side effects, no external dependencies beyond numpy.

Bar dict key contract (from MarketDataService / market_data_service.py):
    "open"   — float
    "high"   — float
    "low"    — float
    "close"  — float
    "volume" — float  (tick volume; may be 0 on some brokers/instruments)

All public functions raise ValueError when the input is too short to produce
a valid result.  Every output array uses np.nan for positions where the
indicator has not yet accumulated enough bars.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

def extract_arrays(
    ohlcv: List[Dict[str, Any]],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Extract (opens, highs, lows, closes, volumes) from a list of bar dicts.

    Tolerates both lower-case and Title-Case key names so the function works
    with raw MT5 bar dicts as well as any normalised form.

    Returns:
        opens, highs, lows, closes, volumes — each float64 ndarray, length n.

    Raises:
        ValueError  — ohlcv list is empty.
        KeyError    — a required key ('open', 'high', 'low', 'close') is absent
                      from the first bar.
    """
    if not ohlcv:
        raise ValueError("ohlcv list is empty; cannot extract arrays.")

    def _field(bar: Dict[str, Any], lc: str, tc: str) -> float:
        v = bar.get(lc) if bar.get(lc) is not None else bar.get(tc)
        if v is None:
            raise KeyError(
                f"Bar dict missing '{lc}' key.  Available keys: {list(bar.keys())}"
            )
        return float(v)

    opens   = np.array([_field(b, "open",   "Open")   for b in ohlcv], dtype=np.float64)
    highs   = np.array([_field(b, "high",   "High")   for b in ohlcv], dtype=np.float64)
    lows    = np.array([_field(b, "low",    "Low")    for b in ohlcv], dtype=np.float64)
    closes  = np.array([_field(b, "close",  "Close")  for b in ohlcv], dtype=np.float64)
    volumes = np.array(
        [float(b.get("volume", b.get("Volume", 0.0))) for b in ohlcv],
        dtype=np.float64,
    )
    return opens, highs, lows, closes, volumes


# ─────────────────────────────────────────────────────────────────────────────
# Trend
# ─────────────────────────────────────────────────────────────────────────────

def calc_ema(closes: np.ndarray, period: int) -> np.ndarray:
    """
    Exponential Moving Average, seeded with the SMA of the first `period` bars.
    Multiplier: 2 / (period + 1).

    Returns:
        float64 ndarray of length n.
        NaN for indices 0 … period-2.
        First valid value at index period-1.

    Raises:
        ValueError  — fewer than `period` bars supplied.
    """
    n = len(closes)
    if n < period:
        raise ValueError(
            f"EMA({period}) requires at least {period} bars; got {n}."
        )
    alpha = 2.0 / (period + 1.0)
    out   = np.full(n, np.nan, dtype=np.float64)
    # Seed: SMA of the first window
    out[period - 1] = float(np.mean(closes[:period]))
    for i in range(period, n):
        out[i] = alpha * closes[i] + (1.0 - alpha) * out[i - 1]
    return out


def calc_sma(closes: np.ndarray, period: int) -> np.ndarray:
    """
    Simple Moving Average (unweighted).

    Returns:
        float64 ndarray of length n.
        NaN for indices 0 … period-2.

    Raises:
        ValueError  — fewer than `period` bars supplied.
    """
    n = len(closes)
    if n < period:
        raise ValueError(
            f"SMA({period}) requires at least {period} bars; got {n}."
        )
    out = np.full(n, np.nan, dtype=np.float64)
    # np.convolve mode='valid' yields exactly n-period+1 values starting at
    # index period-1.
    kernel   = np.ones(period, dtype=np.float64) / period
    out[period - 1:] = np.convolve(closes, kernel, mode="valid")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Momentum
# ─────────────────────────────────────────────────────────────────────────────

def calc_rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """
    Relative Strength Index using Wilder's smoothing method.

    Algorithm:
      1. Compute bar-to-bar changes (np.diff).
      2. Seed avg_gain / avg_loss with the simple mean of the first `period`
         changes.
      3. Apply Wilder smoothing:
           avg_gain = (prev_avg_gain × (period-1) + gain) / period

    Returns:
        float64 ndarray of length n.
        NaN for indices 0 … period-1.
        First valid value at index `period`.

    Raises:
        ValueError  — fewer than period+1 bars supplied.
    """
    n = len(closes)
    if n < period + 1:
        raise ValueError(
            f"RSI({period}) requires at least {period + 1} bars; got {n}."
        )

    deltas = np.diff(closes)                                     # length n-1
    gains  = np.where(deltas > 0,  deltas,  0.0)
    losses = np.where(deltas < 0, -deltas,  0.0)

    out = np.full(n, np.nan, dtype=np.float64)

    # Seed
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    def _rsi(ag: float, al: float) -> float:
        if al == 0.0:
            return 100.0
        return 100.0 - (100.0 / (1.0 + ag / al))

    out[period] = _rsi(avg_gain, avg_loss)

    # Wilder smoothing for bar period+1 onward
    for i in range(period, n - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i])  / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = _rsi(avg_gain, avg_loss)

    return out


def calc_macd(
    closes:     np.ndarray,
    fast:       int = 12,
    slow:       int = 26,
    signal_period: int = 9,
) -> Dict[str, np.ndarray]:
    """
    Moving Average Convergence Divergence.

    Calculation:
      - MACD line  = EMA(fast) − EMA(slow)
      - Signal line = EMA(MACD line, signal_period)
      - Histogram  = MACD line − Signal line

    Returns:
        dict with keys 'macd', 'signal', 'histogram' — each float64 ndarray
        of length n with NaN where insufficient data.

    Raises:
        ValueError  — fewer than slow+signal_period−1 bars supplied.
    """
    n        = len(closes)
    min_bars = slow + signal_period - 1
    if n < min_bars:
        raise ValueError(
            f"MACD({fast},{slow},{signal_period}) requires at least "
            f"{min_bars} bars; got {n}."
        )

    ema_fast = calc_ema(closes, fast)
    ema_slow = calc_ema(closes, slow)

    macd_line = np.full(n, np.nan, dtype=np.float64)
    both_valid = ~np.isnan(ema_fast) & ~np.isnan(ema_slow)
    macd_line[both_valid] = ema_fast[both_valid] - ema_slow[both_valid]

    # Signal line: EMA of the MACD line (computed over its valid portion only)
    signal_arr = np.full(n, np.nan, dtype=np.float64)
    first_valid = int(np.argmax(~np.isnan(macd_line)))
    valid_macd  = macd_line[first_valid:]
    if len(valid_macd) >= signal_period:
        sig_ema = calc_ema(valid_macd, signal_period)
        signal_arr[first_valid:] = sig_ema

    histogram = np.full(n, np.nan, dtype=np.float64)
    both_sig  = ~np.isnan(macd_line) & ~np.isnan(signal_arr)
    histogram[both_sig] = macd_line[both_sig] - signal_arr[both_sig]

    return {
        "macd":      macd_line,
        "signal":    signal_arr,
        "histogram": histogram,
    }


def calc_stochastic_rsi(
    closes:       np.ndarray,
    rsi_period:   int = 14,
    stoch_period: int = 14,
    k_period:     int = 3,
    d_period:     int = 3,
) -> Dict[str, np.ndarray]:
    """
    Stochastic RSI oscillator.

    Algorithm:
      1. Compute RSI(rsi_period).
      2. Apply stochastic formula over rsi_period bars of RSI → raw %K.
      3. Smooth raw %K with SMA(k_period) → smoothed %K.
      4. Smooth %K with SMA(d_period)     → %D.

    Returns:
        dict with keys 'k', 'd' — float64 ndarrays of length n, values 0-100,
        NaN where insufficient data.

    Raises:
        ValueError  — fewer than rsi_period+stoch_period+k_period+d_period bars.
    """
    n        = len(closes)
    min_bars = rsi_period + stoch_period + k_period + d_period
    if n < min_bars:
        raise ValueError(
            f"StochRSI requires at least {min_bars} bars; got {n}."
        )

    rsi_arr = calc_rsi(closes, rsi_period)

    # Raw %K — stochastic of the RSI series
    raw_k = np.full(n, np.nan, dtype=np.float64)
    start = rsi_period + stoch_period - 1
    for i in range(start, n):
        window = rsi_arr[i - stoch_period + 1 : i + 1]
        if np.any(np.isnan(window)):
            continue
        lo  = float(np.min(window))
        hi  = float(np.max(window))
        rng = hi - lo
        raw_k[i] = 100.0 * (rsi_arr[i] - lo) / rng if rng > 0.0 else 50.0

    # Smooth %K with SMA(k_period)
    k_line = np.full(n, np.nan, dtype=np.float64)
    for i in range(k_period - 1, n):
        w = raw_k[i - k_period + 1 : i + 1]
        if not np.any(np.isnan(w)):
            k_line[i] = float(np.mean(w))

    # %D = SMA(k_line, d_period)
    d_line = np.full(n, np.nan, dtype=np.float64)
    for i in range(d_period - 1, n):
        w = k_line[i - d_period + 1 : i + 1]
        if not np.any(np.isnan(w)):
            d_line[i] = float(np.mean(w))

    return {"k": k_line, "d": d_line}


# ─────────────────────────────────────────────────────────────────────────────
# Volatility
# ─────────────────────────────────────────────────────────────────────────────

def calc_atr(
    highs:  np.ndarray,
    lows:   np.ndarray,
    closes: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """
    Average True Range using Wilder's smoothing (same multiplier as Wilder RSI).

    True Range for bar i:
      max(high - low, |high - prev_close|, |low - prev_close|)

    Seed: SMA of the first `period` True Ranges.

    Returns:
        float64 ndarray of length n.
        Valid from index period-1 onward.

    Raises:
        ValueError  — fewer than period+1 bars supplied.
    """
    n = len(closes)
    if n < period + 1:
        raise ValueError(
            f"ATR({period}) requires at least {period + 1} bars; got {n}."
        )

    # True Range
    tr    = np.zeros(n, dtype=np.float64)
    tr[0] = float(highs[0] - lows[0])
    for i in range(1, n):
        tr[i] = max(
            float(highs[i]  - lows[i]),
            float(abs(highs[i]  - closes[i - 1])),
            float(abs(lows[i]   - closes[i - 1])),
        )

    out  = np.full(n, np.nan, dtype=np.float64)
    # Seed with SMA of first `period` TR values
    out[period - 1] = float(np.mean(tr[:period]))
    # Wilder smoothing
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period

    return out


def calc_bollinger_bands(
    closes:  np.ndarray,
    period:  int   = 20,
    std_dev: float = 2.0,
) -> Dict[str, np.ndarray]:
    """
    Bollinger Bands.

    middle  = SMA(period)
    upper   = middle + std_dev × population std-dev
    lower   = middle − std_dev × population std-dev

    Additional outputs:
    bandwidth = (upper − lower) / middle × 100  (volatility measure)
    percent_b = (close − lower) / (upper − lower)  (0=at lower, 1=at upper)

    Returns:
        dict with keys 'upper', 'middle', 'lower', 'bandwidth', 'percent_b' —
        each float64 ndarray of length n with NaN before the first valid bar.

    Raises:
        ValueError  — fewer than `period` bars supplied.
    """
    n = len(closes)
    if n < period:
        raise ValueError(
            f"BB({period}) requires at least {period} bars; got {n}."
        )

    middle    = calc_sma(closes, period)
    upper     = np.full(n, np.nan, dtype=np.float64)
    lower     = np.full(n, np.nan, dtype=np.float64)
    bandwidth = np.full(n, np.nan, dtype=np.float64)
    percent_b = np.full(n, np.nan, dtype=np.float64)

    for i in range(period - 1, n):
        std      = float(np.std(closes[i - period + 1 : i + 1], ddof=0))
        upper[i] = middle[i] + std_dev * std
        lower[i] = middle[i] - std_dev * std
        if middle[i] != 0.0:
            bandwidth[i] = (upper[i] - lower[i]) / middle[i] * 100.0
        band_range = upper[i] - lower[i]
        if band_range > 0.0:
            percent_b[i] = (closes[i] - lower[i]) / band_range

    return {
        "upper":     upper,
        "middle":    middle,
        "lower":     lower,
        "bandwidth": bandwidth,
        "percent_b": percent_b,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Volume / Price-Volume
# ─────────────────────────────────────────────────────────────────────────────

def calc_vwap(
    highs:   np.ndarray,
    lows:    np.ndarray,
    closes:  np.ndarray,
    volumes: np.ndarray,
) -> np.ndarray:
    """
    Cumulative VWAP computed over the entire supplied bar window.

    Typical price = (high + low + close) / 3
    VWAP[i]       = cumsum(typical_price × volume)[i] / cumsum(volume)[i]

    When the broker reports zero volume on all bars (common for some Exness
    instruments), VWAP falls back to a simple arithmetic mean of the typical
    price to preserve a meaningful value for callers.

    Returns:
        float64 ndarray of length n.  All values are valid (no NaN) unless the
        arrays themselves contain NaN.

    Raises:
        ValueError  — arrays are empty or have different lengths.
    """
    n = len(closes)
    if n == 0:
        raise ValueError("VWAP requires at least 1 bar.")
    if not (len(highs) == len(lows) == len(volumes) == n):
        raise ValueError(
            "highs, lows, closes, and volumes must all have the same length."
        )

    typical  = (highs + lows + closes) / 3.0
    cum_tpv  = np.cumsum(typical * volumes)
    cum_vol  = np.cumsum(volumes)

    out  = np.full(n, np.nan, dtype=np.float64)
    mask = cum_vol > 0.0
    out[mask] = cum_tpv[mask] / cum_vol[mask]

    # Fallback: if volume is zero throughout, use cumulative typical-price mean
    if not np.any(mask):
        out = np.cumsum(typical) / np.arange(1, n + 1, dtype=np.float64)

    return out


def calc_volume_analysis(
    closes:  np.ndarray,
    volumes: np.ndarray,
    period:  int = 20,
) -> Dict[str, np.ndarray]:
    """
    Volume analysis: On-Balance Volume (OBV) and normalised volume ratio.

    OBV:
      obv[0] = volumes[0]
      obv[i] = obv[i-1] + volume  if close > prev_close
      obv[i] = obv[i-1] - volume  if close < prev_close
      obv[i] = obv[i-1]           if close == prev_close

    vol_ratio = current_volume / SMA(volume, period)
      > 1.0  → above-average volume (confirmed move)
      < 1.0  → below-average volume (low conviction)

    Returns:
        dict with keys:
          'obv'       — float64 ndarray (cumulative, signed)
          'vol_sma'   — float64 ndarray (SMA of volume over `period` bars)
          'vol_ratio' — float64 ndarray (volume / vol_sma; NaN before period-1)

    Raises:
        ValueError  — fewer than `period` bars, or array length mismatch.
    """
    n = len(closes)
    if n < period:
        raise ValueError(
            f"VolumeAnalysis({period}) requires at least {period} bars; got {n}."
        )
    if len(volumes) != n:
        raise ValueError("closes and volumes must have the same length.")

    # OBV
    obv    = np.zeros(n, dtype=np.float64)
    obv[0] = float(volumes[0])
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            obv[i] = obv[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            obv[i] = obv[i - 1] - volumes[i]
        else:
            obv[i] = obv[i - 1]

    vol_sma   = calc_sma(volumes, period)
    vol_ratio = np.full(n, np.nan, dtype=np.float64)
    mask      = ~np.isnan(vol_sma) & (vol_sma > 0.0)
    vol_ratio[mask] = volumes[mask] / vol_sma[mask]

    return {
        "obv":       obv,
        "vol_sma":   vol_sma,
        "vol_ratio": vol_ratio,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Trend Strength
# ─────────────────────────────────────────────────────────────────────────────

def calc_adx(
    highs:  np.ndarray,
    lows:   np.ndarray,
    closes: np.ndarray,
    period: int = 14,
) -> Dict[str, np.ndarray]:
    """
    Average Directional Index (ADX) with +DI and -DI.

    Algorithm (Wilder, 1978):
      1. Compute True Range (TR) and Directional Movement (+DM / -DM) per bar.
      2. Wilder-smooth TR, +DM, -DM over `period` bars.
      3. +DI = 100 × smoothed_+DM / smoothed_TR
         -DI = 100 × smoothed_-DM / smoothed_TR
      4. DX  = 100 × |+DI − -DI| / (+DI + -DI)
      5. ADX = Wilder smooth of DX over `period` bars.
         First ADX = SMA of the first `period` DX values.

    ADX interpretation:
      0-25  → absent or weak trend
      25-50 → strong trend
      50+   → very strong / potentially exhausted trend

    Returns:
        dict with keys 'adx', 'plus_di', 'minus_di' — each float64 ndarray
        of length n with NaN where insufficient data.

    Raises:
        ValueError  — fewer than 2×period bars supplied.
    """
    n        = len(closes)
    min_bars = 2 * period
    if n < min_bars:
        raise ValueError(
            f"ADX({period}) requires at least {2 * period} bars; got {n}."
        )

    # ── Step 1: TR and directional movement ──────────────────────────────────
    tr       = np.zeros(n, dtype=np.float64)
    plus_dm  = np.zeros(n, dtype=np.float64)
    minus_dm = np.zeros(n, dtype=np.float64)

    tr[0] = float(highs[0] - lows[0])
    for i in range(1, n):
        up_move   = float(highs[i]      - highs[i - 1])
        down_move = float(lows[i - 1]   - lows[i])
        tr[i] = max(
            float(highs[i] - lows[i]),
            float(abs(highs[i] - closes[i - 1])),
            float(abs(lows[i]  - closes[i - 1])),
        )
        if up_move > down_move and up_move > 0.0:
            plus_dm[i]  = up_move
        if down_move > up_move and down_move > 0.0:
            minus_dm[i] = down_move

    # ── Step 2: Wilder smoothing ──────────────────────────────────────────────
    # Initial sum (bars 1..period, skipping bar 0 which has no prev close)
    atr_s    = np.zeros(n, dtype=np.float64)
    plus_dms  = np.zeros(n, dtype=np.float64)
    minus_dms = np.zeros(n, dtype=np.float64)

    atr_s[period]    = float(np.sum(tr[1 : period + 1]))
    plus_dms[period]  = float(np.sum(plus_dm[1 : period + 1]))
    minus_dms[period] = float(np.sum(minus_dm[1 : period + 1]))

    for i in range(period + 1, n):
        atr_s[i]     = atr_s[i - 1]    - atr_s[i - 1]    / period + tr[i]
        plus_dms[i]  = plus_dms[i - 1]  - plus_dms[i - 1]  / period + plus_dm[i]
        minus_dms[i] = minus_dms[i - 1] - minus_dms[i - 1] / period + minus_dm[i]

    # ── Step 3: +DI and -DI ───────────────────────────────────────────────────
    plus_di  = np.full(n, np.nan, dtype=np.float64)
    minus_di = np.full(n, np.nan, dtype=np.float64)

    for i in range(period, n):
        if atr_s[i] > 0.0:
            plus_di[i]  = 100.0 * plus_dms[i]  / atr_s[i]
            minus_di[i] = 100.0 * minus_dms[i] / atr_s[i]

    # ── Step 4: DX ────────────────────────────────────────────────────────────
    dx = np.full(n, np.nan, dtype=np.float64)
    for i in range(period, n):
        if not (np.isnan(plus_di[i]) or np.isnan(minus_di[i])):
            di_sum = plus_di[i] + minus_di[i]
            if di_sum > 0.0:
                dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / di_sum

    # ── Step 5: ADX = Wilder smooth of DX ─────────────────────────────────────
    adx           = np.full(n, np.nan, dtype=np.float64)
    first_adx_idx = 2 * period - 1          # earliest bar where ADX is defined

    if first_adx_idx < n:
        dx_seed = dx[period : first_adx_idx + 1]
        if not np.any(np.isnan(dx_seed)):
            adx[first_adx_idx] = float(np.mean(dx_seed))
            for i in range(first_adx_idx + 1, n):
                if not np.isnan(dx[i]):
                    adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    return {
        "adx":      adx,
        "plus_di":  plus_di,
        "minus_di": minus_di,
    }
