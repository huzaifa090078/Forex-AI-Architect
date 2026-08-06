"""
Smart Money Concepts — pure numpy calculation functions.

Stateless functions that operate on arrays extracted from OHLCV bar dicts.
No I/O, no side effects, no external dependencies beyond numpy.

Bar dict key contract (from MarketDataService / MT5 output):
    "open"   — float
    "high"   — float
    "low"    — float
    "close"  — float
    "volume" — float  (may be 0 on some brokers/instruments)

All public functions raise ValueError when input is too short to produce a
valid result — consistent with the indicators/calculations.py convention.

Detection functions return lists of plain dicts. The SMCAnalyzer class in
analyzer.py converts these to SMCStructure dataclass instances. Keeping raw
computation here prevents dataclass imports and makes unit-testing trivial.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

# ── Constants ─────────────────────────────────────────────────────────────────

_SWING_LOOKBACK_DEFAULT: int   = 3       # bars each side for swing confirmation
_EQUAL_LEVEL_TOLERANCE:  float = 0.001   # 0.10% — two levels within this are "equal"
_IMPULSE_BARS_DEFAULT:   int   = 3       # bars back to search for order block candle


# ── Extraction ────────────────────────────────────────────────────────────────

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
        KeyError    — a required key is absent from the first bar.
    """
    if not ohlcv:
        raise ValueError("ohlcv list is empty; cannot extract arrays.")

    def _field(bar: Dict[str, Any], lc: str, tc: str) -> float:
        v = bar.get(lc) if bar.get(lc) is not None else bar.get(tc)
        if v is None:
            raise KeyError(
                f"Bar dict missing '{lc}' key. Available keys: {list(bar.keys())}"
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


# ── Swing detection ───────────────────────────────────────────────────────────

def find_swing_highs(
    highs:   np.ndarray,
    lookback: int = _SWING_LOOKBACK_DEFAULT,
) -> np.ndarray:
    """
    Return a boolean array where True marks a confirmed swing high.

    A swing high at index i satisfies:
      highs[i] > max(highs[i-lookback : i])   and
      highs[i] > max(highs[i+1 : i+lookback+1])

    Strict inequality is required; flat tops are not marked as swing highs
    to avoid ambiguity.

    Returns:
        bool ndarray of length n.
        Positions 0 … lookback-1 and n-lookback … n-1 are always False
        (insufficient neighbours for confirmation).

    Raises:
        ValueError — fewer than 2*lookback+1 bars supplied.
    """
    n = len(highs)
    min_bars = 2 * lookback + 1
    if n < min_bars:
        raise ValueError(
            f"find_swing_highs requires at least {min_bars} bars; got {n}."
        )

    result = np.zeros(n, dtype=bool)
    for i in range(lookback, n - lookback):
        left  = highs[i - lookback : i]
        right = highs[i + 1 : i + lookback + 1]
        if highs[i] > np.max(left) and highs[i] > np.max(right):
            result[i] = True
    return result


def find_swing_lows(
    lows:    np.ndarray,
    lookback: int = _SWING_LOOKBACK_DEFAULT,
) -> np.ndarray:
    """
    Return a boolean array where True marks a confirmed swing low.

    A swing low at index i satisfies:
      lows[i] < min(lows[i-lookback : i])   and
      lows[i] < min(lows[i+1 : i+lookback+1])

    Strict inequality required; flat bottoms are not marked.

    Returns:
        bool ndarray of length n.  Edges always False.

    Raises:
        ValueError — fewer than 2*lookback+1 bars supplied.
    """
    n = len(lows)
    min_bars = 2 * lookback + 1
    if n < min_bars:
        raise ValueError(
            f"find_swing_lows requires at least {min_bars} bars; got {n}."
        )

    result = np.zeros(n, dtype=bool)
    for i in range(lookback, n - lookback):
        left  = lows[i - lookback : i]
        right = lows[i + 1 : i + lookback + 1]
        if lows[i] < np.min(left) and lows[i] < np.min(right):
            result[i] = True
    return result


# ── Market Structure (BOS / CHoCH) ────────────────────────────────────────────

def calc_market_structure(
    highs:   np.ndarray,
    lows:    np.ndarray,
    closes:  np.ndarray,
    lookback: int = _SWING_LOOKBACK_DEFAULT,
) -> List[Dict[str, Any]]:
    """
    Detect Break of Structure (BOS) and Change of Character (CHoCH) events.

    Algorithm:
      1. Identify swing highs and swing lows.
      2. Track the active (most recent) swing high and swing low levels.
      3. On each bar, when a close breaks above the active swing high:
           - Prior trend BEARISH or UNDEFINED → CHoCH (bullish reversal signal)
           - Prior trend BULLISH              → BOS   (trend continuation)
         Update trend to BULLISH; consume the broken level.
      4. Symmetric logic for bearish breaks (close below active swing low).

    A level is "consumed" once triggered so the same swing level does not
    emit multiple events as subsequent bars continue beyond it.

    Strength:
      break_magnitude / recent_price_range, clamped to [0.3, 1.0].
      CHoCH events receive a +0.1 bonus (stronger signal) before clamping.

    Returns:
        List of dicts:
          'bar_index'  — int   : bar where break was confirmed by close
          'pattern'    — str   : 'bos' | 'choch'
          'direction'  — str   : 'bullish' | 'bearish'
          'level'      — float : the exact broken swing level
          'level_low'  — float : == level (a swing level is a point, not a zone)
          'level_high' — float : == level
          'strength'   — float : 0.30 – 1.0

    Raises:
        ValueError — fewer than 2*lookback+2 bars.
    """
    n = len(closes)
    min_bars = 2 * lookback + 2
    if n < min_bars:
        raise ValueError(
            f"calc_market_structure requires at least {min_bars} bars; got {n}."
        )

    sh_mask = find_swing_highs(highs, lookback)
    sl_mask = find_swing_lows(lows, lookback)

    results: List[Dict[str, Any]] = []

    # Trend state
    trend: str           = "undefined"
    active_sh: float | None = None
    active_sl: float | None = None
    sh_used:   bool      = False
    sl_used:   bool      = False

    # Normalisation range: full bar range of the input window
    recent_range = float(np.max(highs)) - float(np.min(lows))
    if recent_range <= 0.0:
        recent_range = 1.0

    for i in range(n):
        # Update active levels when new swings are confirmed
        if sh_mask[i]:
            active_sh = float(highs[i])
            sh_used   = False
        if sl_mask[i]:
            active_sl = float(lows[i])
            sl_used   = False

        c = float(closes[i])

        # ── Bullish break: close above active swing high ──────────────────────
        if active_sh is not None and not sh_used and c > active_sh:
            is_choch = trend in ("bearish", "undefined")
            pattern  = "choch" if is_choch else "bos"
            mag      = (c - active_sh) / recent_range
            bonus    = 0.10 if is_choch else 0.0
            strength = float(np.clip(mag + bonus, 0.30, 1.0))
            results.append({
                "bar_index":  i,
                "pattern":    pattern,
                "direction":  "bullish",
                "level":      active_sh,
                "level_low":  active_sh,
                "level_high": active_sh,
                "strength":   round(strength, 4),
            })
            trend   = "bullish"
            sh_used = True

        # ── Bearish break: close below active swing low ────────────────────────
        if active_sl is not None and not sl_used and c < active_sl:
            is_choch = trend in ("bullish", "undefined")
            pattern  = "choch" if is_choch else "bos"
            mag      = (active_sl - c) / recent_range
            bonus    = 0.10 if is_choch else 0.0
            strength = float(np.clip(mag + bonus, 0.30, 1.0))
            results.append({
                "bar_index":  i,
                "pattern":    pattern,
                "direction":  "bearish",
                "level":      active_sl,
                "level_low":  active_sl,
                "level_high": active_sl,
                "strength":   round(strength, 4),
            })
            trend   = "bearish"
            sl_used = True

    return results


# ── Order Blocks ──────────────────────────────────────────────────────────────

def calc_order_blocks(
    opens:        np.ndarray,
    highs:        np.ndarray,
    lows:         np.ndarray,
    closes:       np.ndarray,
    lookback:     int = _SWING_LOOKBACK_DEFAULT,
    impulse_bars: int = _IMPULSE_BARS_DEFAULT,
) -> List[Dict[str, Any]]:
    """
    Detect Order Blocks (OB) and Breaker Blocks.

    Order Block definition (SMC):
      Bullish OB — the last bearish candle (close < open) immediately before
                   a bullish impulse that confirms a swing high.
      Bearish OB — the last bullish candle (close > open) immediately before
                   a bearish impulse that confirms a swing low.

    Search window:
      For each confirmed swing high, search back `impulse_bars` candles for the
      last bearish candle. Symmetric for swing lows.

    Mitigation check:
      After OB formation, scan forward through remaining bars.
      Bullish OB mitigated if any subsequent bar has: low <= ob_high and
        close <= ob_high  (price traded back into and through the OB zone).
      Bearish OB mitigated if: high >= ob_low and close >= ob_low.
      A mitigated OB is reclassified as a BREAKER_BLOCK.

    Deduplication:
      Each candle index can produce at most one OB (first detection wins).

    Strength:
      OB candle body size / (2 × mean ATR), clamped to [0.30, 1.0].

    Returns:
        List of dicts:
          'ob_index'  — int   : bar index of the order block candle
          'pattern'   — str   : 'order_block' | 'breaker_block'
          'direction' — str   : 'bullish' | 'bearish'
          'ob_low'    — float : OB candle low
          'ob_high'   — float : OB candle high
          'mitigated' — bool  : True if price has traded back through the OB zone
          'strength'  — float : 0.30 – 1.0

    Raises:
        ValueError — fewer than 2*lookback + impulse_bars + 1 bars.
    """
    n = len(closes)
    min_bars = 2 * lookback + impulse_bars + 1
    if n < min_bars:
        raise ValueError(
            f"calc_order_blocks requires at least {min_bars} bars; got {n}."
        )

    sh_mask = find_swing_highs(highs, lookback)
    sl_mask = find_swing_lows(lows, lookback)

    # Mean ATR for strength normalisation
    if n >= 2:
        tr  = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:]  - closes[:-1]),
            ),
        )
        atr = float(np.mean(tr))
    else:
        atr = 1.0
    if atr <= 0.0:
        atr = 1.0

    results: List[Dict[str, Any]] = []
    seen: set                      = set()   # deduplicate by ob_index

    def _mitigated(ob_idx: int, ob_low: float, ob_high: float, direction: str) -> bool:
        """Return True if price has traded back into and through the OB zone."""
        for j in range(ob_idx + 1, n):
            if direction == "bullish":
                if lows[j] <= ob_high and closes[j] <= ob_high:
                    return True
            else:
                if highs[j] >= ob_low and closes[j] >= ob_low:
                    return True
        return False

    # ── Bullish OBs (from confirmed swing highs) ───────────────────────────────
    for sh_idx in np.where(sh_mask)[0]:
        sh_idx = int(sh_idx)
        ob_idx = None
        for k in range(sh_idx - 1, max(-1, sh_idx - impulse_bars - 1), -1):
            if closes[k] < opens[k]:   # bearish candle
                ob_idx = k
                break
        if ob_idx is None or ob_idx in seen:
            continue
        seen.add(ob_idx)

        ob_low   = float(lows[ob_idx])
        ob_high  = float(highs[ob_idx])
        body     = abs(float(closes[ob_idx]) - float(opens[ob_idx]))
        strength = float(np.clip(body / (2.0 * atr), 0.30, 1.0))
        mit      = _mitigated(sh_idx, ob_low, ob_high, "bullish")
        pattern  = "breaker_block" if mit else "order_block"

        results.append({
            "ob_index":  ob_idx,
            "pattern":   pattern,
            "direction": "bullish",
            "ob_low":    ob_low,
            "ob_high":   ob_high,
            "mitigated": mit,
            "strength":  round(strength, 4),
        })

    # ── Bearish OBs (from confirmed swing lows) ────────────────────────────────
    for sl_idx in np.where(sl_mask)[0]:
        sl_idx = int(sl_idx)
        ob_idx = None
        for k in range(sl_idx - 1, max(-1, sl_idx - impulse_bars - 1), -1):
            if closes[k] > opens[k]:   # bullish candle
                ob_idx = k
                break
        if ob_idx is None or ob_idx in seen:
            continue
        seen.add(ob_idx)

        ob_low   = float(lows[ob_idx])
        ob_high  = float(highs[ob_idx])
        body     = abs(float(closes[ob_idx]) - float(opens[ob_idx]))
        strength = float(np.clip(body / (2.0 * atr), 0.30, 1.0))
        mit      = _mitigated(sl_idx, ob_low, ob_high, "bearish")
        pattern  = "breaker_block" if mit else "order_block"

        results.append({
            "ob_index":  ob_idx,
            "pattern":   pattern,
            "direction": "bearish",
            "ob_low":    ob_low,
            "ob_high":   ob_high,
            "mitigated": mit,
            "strength":  round(strength, 4),
        })

    return results


# ── Supply & Demand Zones ─────────────────────────────────────────────────────

def calc_supply_demand(
    opens:            np.ndarray,
    highs:            np.ndarray,
    lows:             np.ndarray,
    closes:           np.ndarray,
    base_bars:        int   = 2,
    base_body_pct:    float = 0.5,
    impulse_bars:     int   = 3,
    impulse_atr_mult: float = 1.5,
) -> List[Dict[str, Any]]:
    """
    Detect Supply Zones and Demand Zones from consolidation-base patterns.

    Conceptually distinct from Order Blocks:
      Order Block — single opposing candle before a swing-confirmed impulse.
      Supply/Demand — multi-bar consolidation base (tight range) before any
                      strong directional impulse, regardless of swing status.

    Detection algorithm:
      1. Compute ATR for the window (mean true range).
      2. Walk bars sequentially. At each position, test whether a run of
         `base_bars` consecutive bars qualifies as a consolidation base:
           body_size = |close - open| ≤ base_body_pct × ATR  (for every bar).
      3. Immediately after the base, measure the net directional move over the
         next `impulse_bars` bars:
           net_move = close[base_end + impulse_bars] − close[base_end]
         If |net_move| ≥ impulse_atr_mult × ATR:
           net_move > 0  → Demand Zone (bullish)
           net_move < 0  → Supply  Zone (bearish)
      4. Zone bounds:
           zone_low  = min(lows  of base bars)
           zone_high = max(highs of base bars)
      5. Deduplication:
           Once a base is consumed (matched), advance past its last bar so
           overlapping bases do not produce redundant zones.
      6. Mitigation check (static, same-window):
           Scan all bars after the impulse.
           Demand Zone mitigated: high[j] ≥ zone_low AND close[j] ≥ zone_low
             (price returned into the zone from above).
           Supply Zone mitigated: low[j]  ≤ zone_high AND close[j] ≤ zone_high
             (price returned into the zone from below).
           A mitigated zone pattern becomes 'mitigation_block'.

    Strength:
      |net_move| / (impulse_atr_mult × ATR × impulse_bars), clamped [0.30, 1.0].

    Returns:
        List of dicts:
          'zone_start' — int   : first bar index of the consolidation base
          'zone_end'   — int   : last bar index of the consolidation base
          'pattern'    — str   : 'supply_zone' | 'demand_zone' | 'mitigation_block'
          'direction'  — str   : 'bullish' (demand) | 'bearish' (supply)
          'zone_low'   — float : min(lows of base bars)
          'zone_high'  — float : max(highs of base bars)
          'mitigated'  — bool  : True if price traded back into the zone
          'strength'   — float : 0.30 – 1.0

    Raises:
        ValueError — fewer than base_bars + impulse_bars + 1 bars supplied.
    """
    n = len(closes)
    min_bars = base_bars + impulse_bars + 1
    if n < min_bars:
        raise ValueError(
            f"calc_supply_demand requires at least {min_bars} bars; got {n}."
        )
    if len(opens) != n or len(highs) != n or len(lows) != n:
        raise ValueError("opens, highs, lows, closes must all have the same length.")

    # Mean ATR for body-size threshold and impulse comparison
    if n >= 2:
        tr  = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:]  - closes[:-1]),
            ),
        )
        atr = float(np.mean(tr))
    else:
        atr = 1.0
    if atr <= 0.0:
        atr = 1.0

    body_threshold    = base_body_pct * atr
    impulse_threshold = impulse_atr_mult * atr
    strength_denom    = impulse_atr_mult * atr * impulse_bars

    results: List[Dict[str, Any]] = []
    i = 0

    while i <= n - base_bars - impulse_bars:
        # ── Test consolidation base starting at i ─────────────────────────────
        base_valid = True
        for k in range(i, i + base_bars):
            body = abs(float(closes[k]) - float(opens[k]))
            if body > body_threshold:
                base_valid = False
                break

        if not base_valid:
            i += 1
            continue

        base_start = i
        base_end   = i + base_bars - 1
        impulse_end = base_end + impulse_bars

        if impulse_end >= n:
            i += 1
            continue

        # ── Measure impulse immediately after the base ─────────────────────
        net_move = float(closes[impulse_end]) - float(closes[base_end])

        if abs(net_move) < impulse_threshold:
            i += 1
            continue

        # ── Valid zone found ───────────────────────────────────────────────
        zone_low  = float(np.min(lows[base_start : base_end + 1]))
        zone_high = float(np.max(highs[base_start : base_end + 1]))

        direction = "bullish" if net_move > 0 else "bearish"
        raw_pattern = "demand_zone" if direction == "bullish" else "supply_zone"

        strength = float(np.clip(abs(net_move) / strength_denom, 0.30, 1.0))

        # ── Mitigation check (static, scan forward from impulse_end) ──────
        mitigated = False
        for j in range(impulse_end + 1, n):
            if direction == "bullish":
                # Demand zone: price returns into zone from below
                if float(highs[j]) >= zone_low and float(closes[j]) >= zone_low:
                    mitigated = True
                    break
            else:
                # Supply zone: price returns into zone from above
                if float(lows[j]) <= zone_high and float(closes[j]) <= zone_high:
                    mitigated = True
                    break

        pattern = "mitigation_block" if mitigated else raw_pattern

        results.append({
            "zone_start": base_start,
            "zone_end":   base_end,
            "pattern":    pattern,
            "direction":  direction,
            "zone_low":   round(zone_low,  6),
            "zone_high":  round(zone_high, 6),
            "mitigated":  mitigated,
            "strength":   round(strength,  4),
        })

        # Advance past the consumed base to avoid overlapping zones
        i = base_end + 1

    return results


# ── Fair Value Gaps ───────────────────────────────────────────────────────────

def calc_fair_value_gaps(
    highs:       np.ndarray,
    lows:        np.ndarray,
    closes:      np.ndarray,
    min_gap_pct: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Detect Fair Value Gaps (FVGs) and imbalances using the three-candle pattern.

    Bullish FVG:  lows[i] > highs[i-2]
      Gap zone: highs[i-2] (gap_low) → lows[i] (gap_high)

    Bearish FVG:  highs[i] < lows[i-2]
      Gap zone: highs[i] (gap_low) → lows[i-2] (gap_high)

    Size classification (stored in metadata only; both use the same 'fvg' key):
      gap_size >= 0.5 × ATR → FAIR_VALUE_GAP
      gap_size <  0.5 × ATR → IMBALANCE
    Callers may use metadata['size_class'] to distinguish if needed.

    Filled check:
      After gap formation at bar i, scan subsequent bars. A gap is "filled"
      when any bar has: low <= gap_high AND high >= gap_low (price traded
      through the gap zone in either direction).
      Filled FVGs remain in the output with metadata['filled']=True.

    Strength:
      gap_size / (1.5 × ATR), clamped to [0.20, 1.0].

    Returns:
        List of dicts:
          'bar_index' — int   : index of bar i (the third candle)
          'pattern'   — str   : 'fvg'
          'direction' — str   : 'bullish' | 'bearish'
          'gap_low'   — float
          'gap_high'  — float
          'gap_size'  — float : gap_high − gap_low
          'filled'    — bool  : True if price has since traded through the gap
          'size_class'— str   : 'fair_value_gap' | 'imbalance'
          'strength'  — float : 0.20 – 1.0

    Raises:
        ValueError — fewer than 3 bars.
    """
    n = len(closes)
    if n < 3:
        raise ValueError(
            f"calc_fair_value_gaps requires at least 3 bars; got {n}."
        )

    # ATR proxy for strength and size classification
    if n >= 2:
        tr  = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:]  - closes[:-1]),
            ),
        )
        atr = float(np.mean(tr))
    else:
        atr = 1.0
    if atr <= 0.0:
        atr = 1.0

    atr_threshold = 0.5 * atr   # size boundary between FVG and imbalance

    def _is_filled(from_bar: int, gap_low: float, gap_high: float) -> bool:
        for j in range(from_bar + 1, n):
            if lows[j] <= gap_high and highs[j] >= gap_low:
                return True
        return False

    results: List[Dict[str, Any]] = []

    for i in range(2, n):
        # ── Bullish FVG ───────────────────────────────────────────────────────
        if lows[i] > highs[i - 2]:
            gap_low  = float(highs[i - 2])
            gap_high = float(lows[i])
            gap_size = gap_high - gap_low
            if gap_size <= 0.0:
                continue
            ref_price = gap_low
            if ref_price > 0.0 and gap_size / ref_price < min_gap_pct:
                continue
            strength   = float(np.clip(gap_size / (1.5 * atr), 0.20, 1.0))
            size_class = "fair_value_gap" if gap_size >= atr_threshold else "imbalance"
            results.append({
                "bar_index":  i,
                "pattern":    "fvg",
                "direction":  "bullish",
                "gap_low":    gap_low,
                "gap_high":   gap_high,
                "gap_size":   round(gap_size, 6),
                "filled":     _is_filled(i, gap_low, gap_high),
                "size_class": size_class,
                "strength":   round(strength, 4),
            })

        # ── Bearish FVG ───────────────────────────────────────────────────────
        elif highs[i] < lows[i - 2]:
            gap_low  = float(highs[i])
            gap_high = float(lows[i - 2])
            gap_size = gap_high - gap_low
            if gap_size <= 0.0:
                continue
            ref_price = gap_high
            if ref_price > 0.0 and gap_size / ref_price < min_gap_pct:
                continue
            strength   = float(np.clip(gap_size / (1.5 * atr), 0.20, 1.0))
            size_class = "fair_value_gap" if gap_size >= atr_threshold else "imbalance"
            results.append({
                "bar_index":  i,
                "pattern":    "fvg",
                "direction":  "bearish",
                "gap_low":    gap_low,
                "gap_high":   gap_high,
                "gap_size":   round(gap_size, 6),
                "filled":     _is_filled(i, gap_low, gap_high),
                "size_class": size_class,
                "strength":   round(strength, 4),
            })

    return results


# ── Liquidity Levels ──────────────────────────────────────────────────────────

def calc_liquidity_levels(
    highs:               np.ndarray,
    lows:                np.ndarray,
    closes:              np.ndarray,
    lookback:            int   = _SWING_LOOKBACK_DEFAULT,
    equal_tolerance_pct: float = _EQUAL_LEVEL_TOLERANCE,
) -> List[Dict[str, Any]]:
    """
    Detect liquidity pools, equal highs/lows, swing targets, and sweep events.

    Four detection methods:

    1. Equal Highs
       Two or more confirmed swing highs within `equal_tolerance_pct` of each
       other form a liquidity cluster. Price tends to sweep these before
       reversing → direction='bearish' (stop-hunt above equal highs).
       pattern='equal_high', level = average of the pair.

    2. Equal Lows
       Same as equal highs but for swing lows.
       direction='bullish' (stop-hunt below equal lows).
       pattern='equal_low'.

    3. Swing Liquidity (unswept)
       The most recent 5 swing highs and 5 swing lows that have not yet
       been swept are reported as pending liquidity targets.
       pattern='swing_liquidity'.

    4. Liquidity Sweep
       A bar where the wick exceeds a swing level but the close returns
       inside it confirms a stop-hunt (sweep). Only the first sweep of each
       swing level is reported.
         Bearish sweep: high[j] > swing_high AND close[j] < swing_high
         Bullish sweep: low[j]  < swing_low  AND close[j] > swing_low
       pattern='sweep'.

    Deduplication (equal highs/lows):
       Level pairs are rounded to 5 decimal places for deduplication so the
       same cluster does not appear from multiple pair combinations.

    Strength:
       equal_high / equal_low : 0.70 (two confirmed touches = significant pool)
       swing_liquidity        : 0.50 (target identified, not yet confirmed)
       sweep                  : 0.80 (stop-hunt confirmed by close reversal)

    Returns:
        List of dicts:
          'bar_index'  — int   : bar where event is detected or confirmed
          'pattern'    — str   : 'equal_high' | 'equal_low' |
                                 'swing_liquidity' | 'sweep'
          'direction'  — str   : 'bullish' | 'bearish'
          'level_low'  — float
          'level_high' — float
          'strength'   — float : 0.50 – 0.80

    Raises:
        ValueError — fewer than 2*lookback+1 bars.
    """
    n = len(closes)
    min_bars = 2 * lookback + 1
    if n < min_bars:
        raise ValueError(
            f"calc_liquidity_levels requires at least {min_bars} bars; got {n}."
        )

    sh_mask = find_swing_highs(highs, lookback)
    sl_mask = find_swing_lows(lows, lookback)

    sh_indices = np.where(sh_mask)[0].tolist()
    sl_indices = np.where(sl_mask)[0].tolist()

    results: List[Dict[str, Any]] = []

    # ── 1. Equal Highs ─────────────────────────────────────────────────────────
    reported_eq_highs: set = set()
    for a in range(len(sh_indices)):
        for b in range(a + 1, len(sh_indices)):
            ia, ib = sh_indices[a], sh_indices[b]
            ha, hb = float(highs[ia]), float(highs[ib])
            if ha <= 0.0:
                continue
            if abs(ha - hb) / ha <= equal_tolerance_pct:
                avg = (ha + hb) / 2.0
                key = round(avg, 5)
                if key not in reported_eq_highs:
                    reported_eq_highs.add(key)
                    results.append({
                        "bar_index":  ib,
                        "pattern":    "equal_high",
                        "direction":  "bearish",
                        "level_low":  min(ha, hb),
                        "level_high": max(ha, hb),
                        "strength":   0.70,
                    })

    # ── 2. Equal Lows ─────────────────────────────────────────────────────────
    reported_eq_lows: set = set()
    for a in range(len(sl_indices)):
        for b in range(a + 1, len(sl_indices)):
            ia, ib = sl_indices[a], sl_indices[b]
            la, lb = float(lows[ia]), float(lows[ib])
            if la <= 0.0:
                continue
            if abs(la - lb) / la <= equal_tolerance_pct:
                avg = (la + lb) / 2.0
                key = round(avg, 5)
                if key not in reported_eq_lows:
                    reported_eq_lows.add(key)
                    results.append({
                        "bar_index":  ib,
                        "pattern":    "equal_low",
                        "direction":  "bullish",
                        "level_low":  min(la, lb),
                        "level_high": max(la, lb),
                        "strength":   0.70,
                    })

    # ── 3 + 4. Swing Liquidity and Sweep ──────────────────────────────────────
    recent_sh = sh_indices[-5:] if len(sh_indices) >= 5 else sh_indices
    recent_sl = sl_indices[-5:] if len(sl_indices) >= 5 else sl_indices

    for sh_idx in recent_sh:
        sh_level = float(highs[sh_idx])
        swept    = False
        for j in range(sh_idx + 1, n):
            if float(highs[j]) > sh_level and float(closes[j]) < sh_level:
                results.append({
                    "bar_index":  j,
                    "pattern":    "sweep",
                    "direction":  "bearish",
                    "level_low":  sh_level,
                    "level_high": float(highs[j]),
                    "strength":   0.80,
                })
                swept = True
                break
        if not swept:
            results.append({
                "bar_index":  sh_idx,
                "pattern":    "swing_liquidity",
                "direction":  "bearish",
                "level_low":  sh_level,
                "level_high": sh_level,
                "strength":   0.50,
            })

    for sl_idx in recent_sl:
        sl_level = float(lows[sl_idx])
        swept    = False
        for j in range(sl_idx + 1, n):
            if float(lows[j]) < sl_level and float(closes[j]) > sl_level:
                results.append({
                    "bar_index":  j,
                    "pattern":    "sweep",
                    "direction":  "bullish",
                    "level_low":  float(lows[j]),
                    "level_high": sl_level,
                    "strength":   0.80,
                })
                swept = True
                break
        if not swept:
            results.append({
                "bar_index":  sl_idx,
                "pattern":    "swing_liquidity",
                "direction":  "bullish",
                "level_low":  sl_level,
                "level_high": sl_level,
                "strength":   0.50,
            })

    return results


# ── Price Zone ────────────────────────────────────────────────────────────────

def calc_price_zone(
    current_price: float,
    highs:         np.ndarray,
    lows:          np.ndarray,
    lookback:      int = _SWING_LOOKBACK_DEFAULT,
) -> str:
    """
    Classify current_price relative to the recent swing range.

    Algorithm:
      1. Find the most recent confirmed swing high and swing low.
      2. midpoint = (swing_high + swing_low) / 2
      3. Premium     = current_price > midpoint   (upper half of range)
         Discount    = current_price < midpoint   (lower half of range)
         Equilibrium = current_price == midpoint  (on the 50% level)

    Fallback (insufficient data):
      If no confirmed swing highs or lows are found, uses the absolute max
      and min of the supplied arrays. If arrays are flat, returns 'equilibrium'.

    Returns:
        str — 'premium' | 'equilibrium' | 'discount'

    Never raises: returns 'equilibrium' on any data problem so the caller
    always gets a valid Zone.
    """
    n = len(highs)
    min_bars = 2 * lookback + 1

    if n < min_bars:
        return "equilibrium"

    try:
        sh_mask = find_swing_highs(highs, lookback)
        sl_mask = find_swing_lows(lows,  lookback)
    except ValueError:
        return "equilibrium"

    sh_idx_arr = np.where(sh_mask)[0]
    sl_idx_arr = np.where(sl_mask)[0]

    if len(sh_idx_arr) > 0 and len(sl_idx_arr) > 0:
        range_high = float(highs[sh_idx_arr[-1]])
        range_low  = float(lows[sl_idx_arr[-1]])
    else:
        # Fall back to absolute extremes of the supplied window
        range_high = float(np.max(highs))
        range_low  = float(np.min(lows))

    if range_high <= range_low:
        return "equilibrium"

    midpoint = (range_high + range_low) / 2.0

    if current_price > midpoint:
        return "premium"
    if current_price < midpoint:
        return "discount"
    return "equilibrium"
