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
from app.modules.indicators.calculations import calc_ema, calc_rsi
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

# Canonical timeframe order, high → low. Used for priority-ranked iteration
# throughout MTF analysis (H4 evaluated first, M5 last).
_CANONICAL_TFS = ["H4", "H1", "M15", "M5"]

# Alignment score weights for lower timeframes (H1, M15, M5).
# Roadmap Section 6.12 hierarchy:
#   H1  = 0.50  (primary structure — highest confirmation weight)
#   M15 = 0.30  (confirmation layer — medium weight)
#   M5  = 0.20  (entry context — lowest weight)
# Weights sum to 1.0. When a timeframe is absent the score is
# re-normalised against the sum of the available weights only.
_TF_WEIGHTS = {"H1": 0.50, "M15": 0.30, "M5": 0.20}


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

    @staticmethod
    def _get_dominant_zones(
        tf_analyses: Dict[str, TimeframeAnalysis],
    ) -> List[SMCStructure]:
        """
        Identify SMC zones confirmed across ≥2 timeframes.

        For each category (order_blocks, fvgs, supply_demand), every zone is
        compared against zones from all other timeframes. Two zones are
        considered the same level when all three conditions hold:
          1. Same SMCPattern
          2. Same direction
          3. Price ranges overlap:
               zone_a.price_low  <= zone_b.price_high
               zone_b.price_low  <= zone_a.price_high

        From each overlapping pair the higher-timeframe zone is returned
        (iteration order is H4 → H1 → M15 → M5, so zone_a is always the
        higher-TF candidate when a match is found further along the list).
        Each zone appears in the output at most once.
        """
        dominant: List[SMCStructure] = []
        added_ids: set = set()

        for category in ("order_blocks", "fvgs", "supply_demand"):
            # Build (timeframe, zone) list ordered high → low (H4 first)
            ordered: List[tuple] = []
            for tf in _CANONICAL_TFS:
                if tf not in tf_analyses:
                    continue
                for zone in getattr(tf_analyses[tf], category):
                    ordered.append((tf, zone))

            # For each zone find an overlap from a different timeframe
            for i, (tf_a, zone_a) in enumerate(ordered):
                for tf_b, zone_b in ordered[i + 1:]:
                    if tf_b == tf_a:
                        continue
                    if (
                        zone_a.pattern    == zone_b.pattern
                        and zone_a.direction  == zone_b.direction
                        and zone_a.price_low  <= zone_b.price_high
                        and zone_b.price_low  <= zone_a.price_high
                    ):
                        # zone_a is the higher-TF version; add it once
                        zone_id = id(zone_a)
                        if zone_id not in added_ids:
                            dominant.append(zone_a)
                            added_ids.add(zone_id)
                        break   # one confirmed overlap is sufficient

        return dominant

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

    # ── ISMCAnalyzer — analyze_multi_timeframe ────────────────────────────────

    def analyze_multi_timeframe(
        self,
        ohlcv_per_timeframe: Dict[str, List[Dict[str, Any]]],
    ) -> MTFAnalysis:
        """
        Aggregate SMC analysis across multiple timeframes.

        Roadmap hierarchy (Section 6.12):
          H4  — higher-timeframe bias source
          H1  — primary market structure
          M15 — confirmation layer
          M5  — entry context

        Alignment score weighting (lower timeframes only):
          H1  = 0.50  (primary structure — highest confirmation weight)
          M15 = 0.30  (confirmation layer — medium weight)
          M5  = 0.20  (entry context — lowest weight)
        Weights sum to 1.0 across all three lower timeframes. When one or
        more are absent, the score is re-normalised against the sum of the
        available weights only.

        Analysis-only: this method makes no trading decisions, computes no
        lot sizes, and applies no risk rules. It is a pure aggregation of
        existing detect_* output.

        Args:
            ohlcv_per_timeframe — dict mapping timeframe label to OHLCV bar
                                  list. Accepts any subset of the canonical
                                  set {"H4", "H1", "M15", "M5"}.

        Returns:
            MTFAnalysis with pair="" (the _PAIR_UNSET sentinel).
            Caller sets pair after receiving the result if needed.
        """
        # ── Step 1: Available and missing timeframes ──────────────────────
        available: List[str] = [
            tf for tf in _CANONICAL_TFS if tf in ohlcv_per_timeframe
        ]
        missing: List[str] = [
            tf for tf in _CANONICAL_TFS if tf not in ohlcv_per_timeframe
        ]

        # ── Step 2: Per-timeframe detection ──────────────────────────────
        tf_analyses: Dict[str, TimeframeAnalysis] = {}
        for tf in available:
            ohlcv = ohlcv_per_timeframe[tf]
            structures    = self.detect_market_structure(ohlcv, tf)
            order_blocks  = self.detect_order_blocks(ohlcv, tf)
            fvgs          = self.detect_fair_value_gaps(ohlcv, tf)
            liquidity     = self.detect_liquidity_levels(ohlcv, tf)
            supply_demand = self.detect_supply_demand(ohlcv, tf)

            # Derive per-TF bias from most recent structure event
            tf_bias = TrendBias.NEUTRAL
            if structures:
                most_recent = max(
                    structures,
                    key=lambda s: s.metadata.get("bar_index", 0),
                )
                if most_recent.direction == TrendBias.BULLISH:
                    tf_bias = TrendBias.BULLISH
                elif most_recent.direction == TrendBias.BEARISH:
                    tf_bias = TrendBias.BEARISH

            tf_analyses[tf] = TimeframeAnalysis(
                timeframe=tf,
                structures=structures,
                order_blocks=order_blocks,
                fvgs=fvgs,
                liquidity=liquidity,
                supply_demand=supply_demand,
                bias=tf_bias,
            )

        # ── Step 3: Overall bias (H4 preferred; H1 fallback) ─────────────
        overall_bias = TrendBias.NEUTRAL
        for tf in ("H4", "H1"):
            if tf in tf_analyses and tf_analyses[tf].bias != TrendBias.NEUTRAL:
                overall_bias = tf_analyses[tf].bias
                break

        # ── Step 4: Dominant timeframe ────────────────────────────────────
        # Highest-priority timeframe with a non-neutral bias AND at least
        # one confirmed structure event.
        dominant_timeframe: str = ""
        for tf in _CANONICAL_TFS:
            if (
                tf in tf_analyses
                and tf_analyses[tf].bias != TrendBias.NEUTRAL
                and tf_analyses[tf].structures
            ):
                dominant_timeframe = tf
                break

        # ── Step 5: Weighted alignment score and conflict detection ───────
        lower_tfs: List[str] = [
            tf for tf in ("H1", "M15", "M5") if tf in tf_analyses
        ]

        if lower_tfs and overall_bias != TrendBias.NEUTRAL:
            weight_sum   = sum(_TF_WEIGHTS.get(tf, 0.0) for tf in lower_tfs)
            agree_weight = sum(
                _TF_WEIGHTS.get(tf, 0.0)
                for tf in lower_tfs
                if tf_analyses[tf].bias == overall_bias
            )
            alignment_score = (agree_weight / weight_sum) if weight_sum > 0.0 else 0.0
        else:
            alignment_score = 0.0

        # A timeframe conflicts only when it actively opposes the bias;
        # NEUTRAL timeframes are not conflicts — they simply lack a signal.
        conflicting_timeframes: List[str] = [
            tf for tf in lower_tfs
            if tf_analyses[tf].bias != overall_bias
            and tf_analyses[tf].bias != TrendBias.NEUTRAL
        ]

        # H1 must agree AND overall bias must be non-neutral for alignment.
        aligned: bool = (
            "H1" in tf_analyses
            and tf_analyses["H1"].bias == overall_bias
            and overall_bias != TrendBias.NEUTRAL
        )

        # ── Step 6: Dominant zone detection ──────────────────────────────
        dominant_zones = self._get_dominant_zones(tf_analyses)

        logger.debug(
            "analyze_multi_timeframe: bias=%s aligned=%s score=%.2f "
            "available=%s dominant_tf=%s dominant_zones=%d",
            overall_bias.value, aligned, alignment_score,
            available, dominant_timeframe, len(dominant_zones),
        )

        return MTFAnalysis(
            bias=overall_bias,
            aligned=aligned,
            alignment_score=round(alignment_score, 4),
            dominant_timeframe=dominant_timeframe,
            conflicting_timeframes=conflicting_timeframes,
            available_timeframes=available,
            missing_timeframes=missing,
            timeframes=tf_analyses,
            dominant_zones=dominant_zones,
        )

    # ── ISMCAnalyzer — score_confluence ───────────────────────────────────────

    def score_confluence(
        self,
        mtf: MTFAnalysis,
        ohlcv: List[Dict[str, Any]],
        current_price: float,
    ) -> ConfluenceResult:
        """
        Compute a normalized 0–100 confluence score from pre-computed SMC data.

        Eight independent factors are scored and summed. Factor max scores
        sum to exactly 100 so no normalization step is needed.

        All SMC inputs are taken from the supplied MTFAnalysis; no detect_*
        methods are called here. ohlcv is used only for RSI-14 and EMA-20.
        Analysis-only — no trading decisions, no lot sizing, no risk rules.

        Args:
            mtf           — pre-computed MTFAnalysis (from analyze_multi_timeframe)
            ohlcv         — OHLCV bar list used only for RSI-14 and EMA-20
            current_price — the price level to score at

        Returns:
            ConfluenceResult with score 0–100 and per-factor breakdown.
        """
        bias    = mtf.bias
        factors: List[ConfluenceFactor] = []

        # ── Pre-compute closes array for RSI/EMA (shared; fail gracefully) ────
        closes_arr: Optional[np.ndarray] = None
        if ohlcv:
            try:
                _, _, _, closes_arr, _ = extract_arrays(ohlcv)
            except Exception as exc:
                logger.debug("score_confluence: OHLCV extraction failed — %s", exc)

        # ── Factor 1: BOS/CHoCH multi-timeframe alignment (max 20) ───────────
        if bias == TrendBias.NEUTRAL:
            f1_score  = 0.0
            f1_reason = "No directional bias established — BOS/CHoCH alignment skipped."
        elif mtf.aligned:
            # H1 agrees with overall bias; full weighted score
            f1_score  = round(20.0 * mtf.alignment_score, 2)
            f1_reason = (
                f"H1 confirms {bias.value} bias; MTF alignment "
                f"{mtf.alignment_score:.0%} across "
                f"{', '.join(mtf.available_timeframes)}."
            )
        else:
            # Bias present but H1 not aligned — partial credit
            f1_score  = round(10.0 * mtf.alignment_score, 2)
            f1_reason = (
                f"{bias.value.capitalize()} bias from "
                f"{mtf.dominant_timeframe or 'higher TF'} "
                f"but H1 not aligned — partial score."
            )
        factors.append(ConfluenceFactor(
            name="bos_choch_alignment",
            score=f1_score,
            max_score=20.0,
            confirmed=f1_score > 0.0,
            reason=f1_reason,
        ))

        # ── Factor 2: Order Block at current price (max 15) ───────────────────
        # Active = validated (impulse-confirmed) and not mitigated.
        # Direction must match bias; zone must contain current_price.
        f2_strength = 0.0
        f2_tf       = ""
        for tf in _CANONICAL_TFS:
            if tf not in mtf.timeframes:
                continue
            for ob in mtf.timeframes[tf].order_blocks:
                if (
                    ob.validated
                    and not ob.metadata.get("mitigated", False)
                    and ob.direction == bias.value
                    and ob.price_low <= current_price <= ob.price_high
                    and ob.strength > f2_strength
                ):
                    f2_strength = ob.strength
                    f2_tf       = tf

        if f2_strength > 0.0:
            f2_score  = round(15.0 * f2_strength, 2)
            f2_reason = (
                f"Active {bias.value} order block on {f2_tf} contains "
                f"current price (strength {f2_strength:.2f})."
            )
            f2_confirmed = True
        else:
            f2_score     = 0.0
            f2_confirmed = False
            f2_reason    = (
                f"No active {bias.value} order block at current price "
                f"{current_price:.5f}."
            )
        factors.append(ConfluenceFactor(
            name="order_block_alignment",
            score=f2_score,
            max_score=15.0,
            confirmed=f2_confirmed,
            reason=f2_reason,
        ))

        # ── Factor 3: Fair Value Gap at current price (max 15) ────────────────
        # Unfilled (validated=True) FVG whose zone contains current_price
        # and whose direction matches bias.
        f3_strength = 0.0
        f3_tf       = ""
        for tf in _CANONICAL_TFS:
            if tf not in mtf.timeframes:
                continue
            for fvg in mtf.timeframes[tf].fvgs:
                if (
                    fvg.validated   # unfilled = still active imbalance
                    and fvg.direction == bias.value
                    and fvg.price_low <= current_price <= fvg.price_high
                    and fvg.strength > f3_strength
                ):
                    f3_strength = fvg.strength
                    f3_tf       = tf

        if f3_strength > 0.0:
            f3_score  = round(15.0 * f3_strength, 2)
            f3_reason = (
                f"Unfilled {bias.value} FVG on {f3_tf} contains "
                f"current price (strength {f3_strength:.2f})."
            )
            f3_confirmed = True
        else:
            f3_score     = 0.0
            f3_confirmed = False
            f3_reason    = (
                f"No unfilled {bias.value} FVG at current price "
                f"{current_price:.5f}."
            )
        factors.append(ConfluenceFactor(
            name="fvg_alignment",
            score=f3_score,
            max_score=15.0,
            confirmed=f3_confirmed,
            reason=f3_reason,
        ))

        # ── Factor 4: Liquidity Sweep confirmation (max 15) ───────────────────
        # A confirmed sweep (close-reversed wick) in the bias direction means
        # opposing stops have been cleared, supporting the next move.
        # Prioritise higher timeframes (H4 → M5 iteration order).
        f4_found = False
        f4_tf    = ""
        for tf in _CANONICAL_TFS:
            if tf not in mtf.timeframes:
                continue
            for liq in mtf.timeframes[tf].liquidity:
                if (
                    liq.pattern == SMCPattern.LIQUIDITY_SWEEP
                    and liq.direction == bias.value
                ):
                    f4_found = True
                    f4_tf    = tf
                    break
            if f4_found:
                break

        if bias == TrendBias.NEUTRAL:
            f4_score     = 0.0
            f4_confirmed = False
            f4_reason    = "No bias — liquidity sweep evaluation skipped."
        elif f4_found:
            f4_score     = 15.0
            f4_confirmed = True
            f4_reason    = (
                f"{bias.value.capitalize()} liquidity sweep confirmed on {f4_tf}; "
                "opposing stops cleared."
            )
        else:
            f4_score     = 0.0
            f4_confirmed = False
            f4_reason    = (
                f"No {bias.value} liquidity sweep detected — opposing stops "
                "not yet confirmed cleared."
            )
        factors.append(ConfluenceFactor(
            name="liquidity_sweep",
            score=f4_score,
            max_score=15.0,
            confirmed=f4_confirmed,
            reason=f4_reason,
        ))

        # ── Factor 5: Supply/Demand zone alignment (max 15) ───────────────────
        # Active (validated, not mitigated) zone whose direction matches bias.
        # "Near" = current_price within 2× zone height from the zone edge.
        target_pattern = (
            SMCPattern.DEMAND_ZONE
            if bias == TrendBias.BULLISH
            else SMCPattern.SUPPLY_ZONE
        )
        f5_strength = 0.0
        f5_tf       = ""
        for tf in _CANONICAL_TFS:
            if tf not in mtf.timeframes:
                continue
            for sd in mtf.timeframes[tf].supply_demand:
                if sd.pattern != target_pattern or not sd.validated:
                    continue
                zone_h  = sd.price_high - sd.price_low
                margin  = 2.0 * zone_h if zone_h > 0.0 else float("inf")
                if bias == TrendBias.BULLISH:
                    near = current_price <= sd.price_high + margin
                else:
                    near = current_price >= sd.price_low - margin
                if near and sd.strength > f5_strength:
                    f5_strength = sd.strength
                    f5_tf       = tf

        if f5_strength > 0.0:
            f5_score  = round(15.0 * f5_strength, 2)
            f5_reason = (
                f"Active {target_pattern.value.replace('_', ' ')} on {f5_tf} "
                f"aligns with {bias.value} bias "
                f"(strength {f5_strength:.2f})."
            )
            f5_confirmed = True
        else:
            f5_score     = 0.0
            f5_confirmed = False
            f5_reason    = (
                f"No active {target_pattern.value.replace('_', ' ')} "
                "near current price."
            )
        factors.append(ConfluenceFactor(
            name="supply_demand_alignment",
            score=f5_score,
            max_score=15.0,
            confirmed=f5_confirmed,
            reason=f5_reason,
        ))

        # ── Factor 6: Premium/Discount zone alignment (max 10) ────────────────
        # Bullish bias: buying at a Discount (ideal) → 10 pts; Equilibrium → 5 pts.
        # Bearish bias: selling at a Premium (ideal) → 10 pts; Equilibrium → 5 pts.
        try:
            price_zone = self.classify_price_zone("confluence", current_price, ohlcv)
        except Exception:
            price_zone = Zone.EQUILIBRIUM

        if bias == TrendBias.BULLISH:
            if price_zone == Zone.DISCOUNT:
                f6_score  = 10.0
                f6_reason = "Price in Discount zone — buying at institutional value."
            elif price_zone == Zone.EQUILIBRIUM:
                f6_score  = 5.0
                f6_reason = "Price at Equilibrium — moderate premium/discount alignment."
            else:
                f6_score  = 0.0
                f6_reason = "Price in Premium zone — elevated risk for bullish entry."
        elif bias == TrendBias.BEARISH:
            if price_zone == Zone.PREMIUM:
                f6_score  = 10.0
                f6_reason = "Price in Premium zone — selling at institutional value."
            elif price_zone == Zone.EQUILIBRIUM:
                f6_score  = 5.0
                f6_reason = "Price at Equilibrium — moderate premium/discount alignment."
            else:
                f6_score  = 0.0
                f6_reason = "Price in Discount zone — elevated risk for bearish entry."
        else:
            f6_score  = 0.0
            f6_reason = "No bias — premium/discount alignment skipped."
        factors.append(ConfluenceFactor(
            name="premium_discount_alignment",
            score=f6_score,
            max_score=10.0,
            confirmed=f6_score > 0.0,
            reason=f6_reason,
        ))

        # ── Factor 7: RSI-14 confirmation (max 5) ─────────────────────────────
        # Bullish: RSI < 70 (room to run upward, not overbought).
        # Bearish: RSI > 30 (room to fall, not oversold).
        # Delegates to calc_rsi from the existing Indicator Engine.
        f7_score  = 0.0
        f7_reason = "RSI-14 unavailable (insufficient bars or data error)."
        if closes_arr is not None:
            try:
                rsi_arr = calc_rsi(closes_arr, period=14)
                rsi_val = float(rsi_arr[-1]) if not np.isnan(rsi_arr[-1]) else None
                if rsi_val is not None:
                    if bias == TrendBias.BULLISH:
                        if rsi_val < 70.0:
                            f7_score  = 5.0
                            f7_reason = (
                                f"RSI-14 {rsi_val:.1f} — not overbought; "
                                "bullish momentum has room to extend."
                            )
                        else:
                            f7_reason = (
                                f"RSI-14 {rsi_val:.1f} — overbought; "
                                "bullish entry risk elevated."
                            )
                    elif bias == TrendBias.BEARISH:
                        if rsi_val > 30.0:
                            f7_score  = 5.0
                            f7_reason = (
                                f"RSI-14 {rsi_val:.1f} — not oversold; "
                                "bearish momentum has room to extend."
                            )
                        else:
                            f7_reason = (
                                f"RSI-14 {rsi_val:.1f} — oversold; "
                                "bearish entry risk elevated."
                            )
                    else:
                        f7_reason = (
                            f"RSI-14 {rsi_val:.1f} — no bias; "
                            "RSI confirmation skipped."
                        )
            except Exception as exc:
                logger.debug("score_confluence: RSI-14 failed — %s", exc)
        factors.append(ConfluenceFactor(
            name="rsi_confirmation",
            score=f7_score,
            max_score=5.0,
            confirmed=f7_score > 0.0,
            reason=f7_reason,
        ))

        # ── Factor 8: EMA-20 confirmation (max 5) ─────────────────────────────
        # Bullish: current_price above EMA-20 confirms upward trend.
        # Bearish: current_price below EMA-20 confirms downward trend.
        # Delegates to calc_ema from the existing Indicator Engine.
        f8_score  = 0.0
        f8_reason = "EMA-20 unavailable (insufficient bars or data error)."
        if closes_arr is not None:
            try:
                ema_arr = calc_ema(closes_arr, period=20)
                ema_val = float(ema_arr[-1]) if not np.isnan(ema_arr[-1]) else None
                if ema_val is not None:
                    if bias == TrendBias.BULLISH:
                        if current_price > ema_val:
                            f8_score  = 5.0
                            f8_reason = (
                                f"Price {current_price:.5f} above "
                                f"EMA-20 ({ema_val:.5f}) — bullish trend confirmed."
                            )
                        else:
                            f8_reason = (
                                f"Price {current_price:.5f} below "
                                f"EMA-20 ({ema_val:.5f}) — bullish trend unconfirmed."
                            )
                    elif bias == TrendBias.BEARISH:
                        if current_price < ema_val:
                            f8_score  = 5.0
                            f8_reason = (
                                f"Price {current_price:.5f} below "
                                f"EMA-20 ({ema_val:.5f}) — bearish trend confirmed."
                            )
                        else:
                            f8_reason = (
                                f"Price {current_price:.5f} above "
                                f"EMA-20 ({ema_val:.5f}) — bearish trend unconfirmed."
                            )
                    else:
                        f8_reason = (
                            f"EMA-20 {ema_val:.5f} — no bias; "
                            "EMA confirmation skipped."
                        )
            except Exception as exc:
                logger.debug("score_confluence: EMA-20 failed — %s", exc)
        factors.append(ConfluenceFactor(
            name="ema_confirmation",
            score=f8_score,
            max_score=5.0,
            confirmed=f8_score > 0.0,
            reason=f8_reason,
        ))

        # ── Totals ────────────────────────────────────────────────────────────
        # Factor max scores sum to 100 exactly; clamp only against float drift.
        raw_total       = sum(f.score for f in factors)
        score           = min(100, round(raw_total))
        confirmed_count = sum(1 for f in factors if f.confirmed)

        logger.debug(
            "score_confluence: bias=%s score=%d confirmed=%d/%d",
            bias.value, score, confirmed_count, len(factors),
        )

        return ConfluenceResult(
            score=score,
            bias=bias,
            factors=factors,
            confirmed_count=confirmed_count,
            total_factors=len(factors),
        )
