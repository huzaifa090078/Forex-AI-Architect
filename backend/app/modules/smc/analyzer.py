"""
Smart Money Concepts — concrete SMCAnalyzer implementation.

Architecture: Option D (project-native concrete extension).
  - ISMCAnalyzer ABC is unchanged.
  - BaseSMCAnalyzer is unchanged.
  - This class extends BaseSMCAnalyzer with full implementations.
  - classify_price_zone adds an optional `ohlcv` keyword argument beyond the
    ABC signature. Callers typed to ISMCAnalyzer continue to use the 2-arg
    form and receive Zone.EQUILIBRIUM as a safe documented fallback.
    Callers typed to SMCAnalyzer (e.g. MarketScanner, which already uses
    concrete types per the project pattern) pass ohlcv and get full zone
    classification.

Concurrency guarantee:
  Every method is a pure transformation of its inputs. No instance variables,
  no class-level mutable state. Safe as a module-level singleton under
  asyncio.gather() with up to 70 concurrent pair/timeframe coroutines.

Pair field:
  ISMCAnalyzer detect_* signatures do not include `pair`. Returned
  SMCStructure objects carry pair="" (the _PAIR_UNSET sentinel). The
  MarketScanner is responsible for enriching the pair field after calling
  these methods when it wires SMC in (future step per project implementation
  order).
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from app.modules.smc.base import BaseSMCAnalyzer
from app.modules.smc.interfaces import SMCPattern, SMCStructure, Zone
from app.modules.smc.calculations import (
    extract_arrays,
    calc_market_structure,
    calc_order_blocks,
    calc_fair_value_gaps,
    calc_liquidity_levels,
    calc_price_zone,
    calc_supply_demand,
)

logger = logging.getLogger(__name__)

# Sentinel used for the pair field when the interface does not supply it.
_PAIR_UNSET: str = ""


class SMCAnalyzer(BaseSMCAnalyzer):
    """
    Production SMC analyzer — stateless and concurrency-safe.

    All detect_* methods delegate computation to the pure functions in
    calculations.py and convert the resulting dicts into SMCStructure
    dataclass instances.  No mutable state is held between calls.
    """

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _zone_for_level(
        level: float,
        highs: np.ndarray,
        lows:  np.ndarray,
    ) -> Zone:
        """
        Classify a price level as Premium, Equilibrium, or Discount using the
        full OHLCV window's absolute high/low as the reference range.

        This is used internally when populating the `zone` field of detected
        SMCStructures so every structure carries contextual zone information.
        It differs from classify_price_zone (which uses swing-confirmed levels)
        by using the absolute range for speed and simplicity.
        """
        range_high = float(np.max(highs))
        range_low  = float(np.min(lows))
        if range_high <= range_low:
            return Zone.EQUILIBRIUM
        midpoint = (range_high + range_low) / 2.0
        if level > midpoint:
            return Zone.PREMIUM
        if level < midpoint:
            return Zone.DISCOUNT
        return Zone.EQUILIBRIUM

    # ── ISMCAnalyzer — detect_market_structure ────────────────────────────────

    def detect_market_structure(
        self,
        ohlcv:     List[Dict[str, Any]],
        timeframe: str,
    ) -> List[SMCStructure]:
        """
        Detect Break of Structure (BOS) and Change of Character (CHoCH) events.

        Each confirmed break of a swing level produces one SMCStructure:
          - BOS  → SMCPattern.BREAK_OF_STRUCTURE
          - CHoCH → SMCPattern.CHANGE_OF_CHARACTER

        price_low == price_high == the broken swing level (a point, not a zone).
        validated = True (the close that broke the level is the confirmation).

        Returns [] on data errors or insufficient bars (logged at WARNING).
        pair = "" — caller enriches when wiring into MarketScanner.
        """
        try:
            _, highs, lows, closes, _ = extract_arrays(ohlcv)
        except (ValueError, KeyError) as exc:
            logger.error("detect_market_structure: data extraction failed — %s", exc)
            return []

        try:
            raw = calc_market_structure(highs, lows, closes)
        except ValueError as exc:
            logger.warning("detect_market_structure: insufficient data — %s", exc)
            return []

        structures: List[SMCStructure] = []
        for r in raw:
            level   = r["level"]
            zone    = self._zone_for_level(level, highs, lows)
            pattern = (
                SMCPattern.BREAK_OF_STRUCTURE
                if r["pattern"] == "bos"
                else SMCPattern.CHANGE_OF_CHARACTER
            )
            structures.append(SMCStructure(
                pattern=pattern,
                pair=_PAIR_UNSET,
                timeframe=timeframe,
                zone=zone,
                price_low=r["level_low"],
                price_high=r["level_high"],
                direction=r["direction"],
                strength=r["strength"],
                validated=True,           # close-confirmed break
                metadata={
                    "bar_index":   r["bar_index"],
                    "raw_pattern": r["pattern"],   # 'bos' | 'choch'
                },
            ))

        logger.debug(
            "detect_market_structure(%s): %d structures detected",
            timeframe, len(structures),
        )
        return structures

    # ── ISMCAnalyzer — detect_order_blocks ────────────────────────────────────

    def detect_order_blocks(
        self,
        ohlcv:     List[Dict[str, Any]],
        timeframe: str,
    ) -> List[SMCStructure]:
        """
        Detect Order Blocks and Breaker Blocks.

        Bullish OB: last bearish candle before a bullish impulse that confirms
          a swing high. Zone: ob_low – ob_high of the OB candle.
        Bearish OB: last bullish candle before a bearish impulse that confirms
          a swing low.

        Pattern assignment:
          Unmitigated OB → SMCPattern.ORDER_BLOCK,   validated=True
          Mitigated OB   → SMCPattern.BREAKER_BLOCK, validated=True
          (Both are active structures; the Breaker Block is a flipped OB that
          acts as a new opposing zone. validated=True for both because the
          impulse move that formed the OB is already confirmed.)

        Returns [] on data errors or insufficient bars.
        pair = "" — caller enriches when wiring into MarketScanner.
        """
        try:
            opens, highs, lows, closes, _ = extract_arrays(ohlcv)
        except (ValueError, KeyError) as exc:
            logger.error("detect_order_blocks: data extraction failed — %s", exc)
            return []

        try:
            raw = calc_order_blocks(opens, highs, lows, closes)
        except ValueError as exc:
            logger.warning("detect_order_blocks: insufficient data — %s", exc)
            return []

        structures: List[SMCStructure] = []
        for r in raw:
            mid_level = (r["ob_low"] + r["ob_high"]) / 2.0
            zone      = self._zone_for_level(mid_level, highs, lows)
            pattern   = (
                SMCPattern.BREAKER_BLOCK
                if r["pattern"] == "breaker_block"
                else SMCPattern.ORDER_BLOCK
            )
            structures.append(SMCStructure(
                pattern=pattern,
                pair=_PAIR_UNSET,
                timeframe=timeframe,
                zone=zone,
                price_low=r["ob_low"],
                price_high=r["ob_high"],
                direction=r["direction"],
                strength=r["strength"],
                validated=True,           # impulse-confirmed OB
                metadata={
                    "ob_index":  r["ob_index"],
                    "mitigated": r["mitigated"],
                },
            ))

        logger.debug(
            "detect_order_blocks(%s): %d structures detected",
            timeframe, len(structures),
        )
        return structures

    # ── ISMCAnalyzer — detect_fair_value_gaps ────────────────────────────────

    def detect_fair_value_gaps(
        self,
        ohlcv:     List[Dict[str, Any]],
        timeframe: str,
    ) -> List[SMCStructure]:
        """
        Detect Fair Value Gaps and imbalances using the three-candle pattern.

        Both FVGs and imbalances are returned as SMCPattern.FAIR_VALUE_GAP.
        When metadata['size_class'] == 'imbalance', callers may reclassify
        to SMCPattern.IMBALANCE if needed.

        validated:
          True  — FVG is unfilled (still an active imbalance in the market)
          False — FVG has been filled (price traded back through the gap)

        price_low  = gap_low  (the lower boundary of the three-candle gap)
        price_high = gap_high (the upper boundary of the gap)

        Returns [] on data errors or insufficient bars.
        pair = "" — caller enriches when wiring into MarketScanner.
        """
        try:
            _, highs, lows, closes, _ = extract_arrays(ohlcv)
        except (ValueError, KeyError) as exc:
            logger.error("detect_fair_value_gaps: data extraction failed — %s", exc)
            return []

        try:
            raw = calc_fair_value_gaps(highs, lows, closes)
        except ValueError as exc:
            logger.warning("detect_fair_value_gaps: insufficient data — %s", exc)
            return []

        structures: List[SMCStructure] = []
        for r in raw:
            mid_level = (r["gap_low"] + r["gap_high"]) / 2.0
            zone      = self._zone_for_level(mid_level, highs, lows)
            structures.append(SMCStructure(
                pattern=SMCPattern.FAIR_VALUE_GAP,
                pair=_PAIR_UNSET,
                timeframe=timeframe,
                zone=zone,
                price_low=r["gap_low"],
                price_high=r["gap_high"],
                direction=r["direction"],
                strength=r["strength"],
                validated=not r["filled"],   # unfilled = still active
                metadata={
                    "bar_index":  r["bar_index"],
                    "gap_size":   r["gap_size"],
                    "filled":     r["filled"],
                    "size_class": r["size_class"],  # 'fair_value_gap' | 'imbalance'
                },
            ))

        logger.debug(
            "detect_fair_value_gaps(%s): %d structures detected",
            timeframe, len(structures),
        )
        return structures

    # ── ISMCAnalyzer — detect_liquidity_levels ────────────────────────────────

    def detect_liquidity_levels(
        self,
        ohlcv:     List[Dict[str, Any]],
        timeframe: str,
    ) -> List[SMCStructure]:
        """
        Detect liquidity pools, equal highs/lows, swing targets, and sweeps.

        Pattern mapping from calculations layer:
          'equal_high'      → SMCPattern.INDUCEMENT   (equal-high liquidity pool)
          'equal_low'       → SMCPattern.INDUCEMENT   (equal-low liquidity pool)
          'swing_liquidity' → SMCPattern.INDUCEMENT   (unswept swing = pending target)
          'sweep'           → SMCPattern.LIQUIDITY_SWEEP

        validated:
          True  — sweep (confirmed by close reversing inside the swing level)
          False — pool / target (pending; not yet triggered)

        price_low / price_high:
          For equal highs/lows: the band between the two equal levels.
          For swing_liquidity:  price_low == price_high == the swing level (a point).
          For sweeps:           price_low = swing level, price_high = wick extreme
                                (or vice versa for bullish sweeps).

        Returns [] on data errors or insufficient bars.
        pair = "" — caller enriches when wiring into MarketScanner.
        """
        try:
            _, highs, lows, closes, _ = extract_arrays(ohlcv)
        except (ValueError, KeyError) as exc:
            logger.error("detect_liquidity_levels: data extraction failed — %s", exc)
            return []

        try:
            raw = calc_liquidity_levels(highs, lows, closes)
        except ValueError as exc:
            logger.warning("detect_liquidity_levels: insufficient data — %s", exc)
            return []

        structures: List[SMCStructure] = []
        for r in raw:
            mid_level = (r["level_low"] + r["level_high"]) / 2.0
            zone      = self._zone_for_level(mid_level, highs, lows)

            if r["pattern"] == "sweep":
                pattern   = SMCPattern.LIQUIDITY_SWEEP
                validated = True    # close-confirmed
            else:
                pattern   = SMCPattern.INDUCEMENT
                validated = False   # pending target

            structures.append(SMCStructure(
                pattern=pattern,
                pair=_PAIR_UNSET,
                timeframe=timeframe,
                zone=zone,
                price_low=r["level_low"],
                price_high=r["level_high"],
                direction=r["direction"],
                strength=r["strength"],
                validated=validated,
                metadata={
                    "bar_index":      r["bar_index"],
                    "liquidity_type": r["pattern"],   # raw key for downstream use
                },
            ))

        logger.debug(
            "detect_liquidity_levels(%s): %d structures detected",
            timeframe, len(structures),
        )
        return structures

    # ── ISMCAnalyzer — classify_price_zone ────────────────────────────────────

    def classify_price_zone(
        self,
        pair:          str,
        current_price: float,
        ohlcv:         Optional[List[Dict[str, Any]]] = None,
    ) -> Zone:
        """
        Classify current_price as Premium, Equilibrium, or Discount.

        Concrete extension of the ISMCAnalyzer ABC (Option D architecture):
          - The ABC signature (pair, current_price) → Zone is preserved.
          - An optional `ohlcv` keyword argument is added here only.
          - Callers typed to ISMCAnalyzer use the 2-arg form → EQUILIBRIUM.
          - Callers typed to SMCAnalyzer (e.g. the future MarketScanner
            integration, matching the project's existing concrete-type pattern)
            pass ohlcv and receive full swing-based zone classification.

        Classification logic (with ohlcv):
          Uses calc_price_zone which:
            1. Finds the most recent confirmed swing high and swing low.
            2. Computes midpoint = (swing_high + swing_low) / 2.
            3. Premium   = current_price > midpoint
               Discount  = current_price < midpoint
               Equilibrium = current_price == midpoint or no valid swings found

        Fallback (without ohlcv, or ohlcv is empty):
          Returns Zone.EQUILIBRIUM — the neutral, safe default. Documented
          here so callers can make an informed decision about whether to
          supply ohlcv context. This is not a silent failure; it is the
          specified behaviour for the 2-arg ABC call path.

        Args:
            pair          — identifier used for logging only; not in calculation
            current_price — the price level to classify
            ohlcv         — optional OHLCV bar list (newest bars last).
                            If None or empty → returns EQUILIBRIUM.

        Returns:
            Zone.PREMIUM | Zone.EQUILIBRIUM | Zone.DISCOUNT
        """
        if not ohlcv:
            logger.debug(
                "classify_price_zone(%s, %.5f): no OHLCV — returning EQUILIBRIUM",
                pair, current_price,
            )
            return Zone.EQUILIBRIUM

        try:
            _, highs, lows, _, _ = extract_arrays(ohlcv)
        except (ValueError, KeyError) as exc:
            logger.warning(
                "classify_price_zone(%s): extraction failed (%s) — EQUILIBRIUM",
                pair, exc,
            )
            return Zone.EQUILIBRIUM

        zone_str = calc_price_zone(current_price, highs, lows)

        _map: Dict[str, Zone] = {
            "premium":     Zone.PREMIUM,
            "equilibrium": Zone.EQUILIBRIUM,
            "discount":    Zone.DISCOUNT,
        }
        zone = _map.get(zone_str, Zone.EQUILIBRIUM)

        logger.debug(
            "classify_price_zone(%s, %.5f): %s", pair, current_price, zone.value
        )
        return zone

    # ── ISMCAnalyzer — detect_supply_demand ───────────────────────────────────

    def detect_supply_demand(
        self,
        ohlcv:     List[Dict[str, Any]],
        timeframe: str,
    ) -> List[SMCStructure]:
        """
        Detect Supply Zones, Demand Zones, and mitigated zones (Mitigation Blocks).

        Algorithm (independent from Order Blocks — see calc_supply_demand docstring):
          1. Identify consolidation bases: runs of ≥2 bars with body ≤ 0.5 × ATR.
          2. Confirm a directional impulse ≥ 1.5 × ATR after the base.
          3. Zone bounds = [min(lows), max(highs)] of the base bars.
          4. Classify:
               Unmitigated Demand Zone → SMCPattern.DEMAND_ZONE,  validated=True
               Unmitigated Supply Zone → SMCPattern.SUPPLY_ZONE,  validated=True
               Mitigated zone          → SMCPattern.MITIGATION_BLOCK, validated=False

        Pattern population:
          SMCPattern.DEMAND_ZONE       — active bullish accumulation zone
          SMCPattern.SUPPLY_ZONE       — active bearish distribution zone
          SMCPattern.MITIGATION_BLOCK  — zone that has been revisited by price;
                                         may still act as a reference level but
                                         is no longer a fresh untested zone

        Returns [] on data errors or insufficient bars (logged at WARNING).
        pair = "" — caller enriches when wiring into MarketScanner.
        """
        try:
            opens, highs, lows, closes, _ = extract_arrays(ohlcv)
        except (ValueError, KeyError) as exc:
            logger.error("detect_supply_demand: data extraction failed — %s", exc)
            return []

        try:
            raw = calc_supply_demand(opens, highs, lows, closes)
        except ValueError as exc:
            logger.warning("detect_supply_demand: insufficient data — %s", exc)
            return []

        _pattern_map = {
            "demand_zone":      SMCPattern.DEMAND_ZONE,
            "supply_zone":      SMCPattern.SUPPLY_ZONE,
            "mitigation_block": SMCPattern.MITIGATION_BLOCK,
        }

        structures: List[SMCStructure] = []
        for r in raw:
            mid_level = (r["zone_low"] + r["zone_high"]) / 2.0
            zone      = self._zone_for_level(mid_level, highs, lows)
            pattern   = _pattern_map[r["pattern"]]
            validated = not r["mitigated"]   # active (untested) zone = validated

            structures.append(SMCStructure(
                pattern=pattern,
                pair=_PAIR_UNSET,
                timeframe=timeframe,
                zone=zone,
                price_low=r["zone_low"],
                price_high=r["zone_high"],
                direction=r["direction"],
                strength=r["strength"],
                validated=validated,
                metadata={
                    "zone_start": r["zone_start"],
                    "zone_end":   r["zone_end"],
                    "mitigated":  r["mitigated"],
                },
            ))

        logger.debug(
            "detect_supply_demand(%s): %d structures detected",
            timeframe, len(structures),
        )
        return structures
