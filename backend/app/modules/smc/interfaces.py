"""
Smart Money Concepts (SMC) — abstract interface contracts.

SMC analysis detects institutional order-flow structures on price charts:
Order Blocks, Fair Value Gaps, Breaker Blocks, Change of Character,
Break of Structure, and Premium/Discount zones.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List


class SMCPattern(str, Enum):
    ORDER_BLOCK = "order_block"
    BREAKER_BLOCK = "breaker_block"
    FAIR_VALUE_GAP = "fair_value_gap"
    IMBALANCE = "imbalance"
    CHANGE_OF_CHARACTER = "change_of_character"
    BREAK_OF_STRUCTURE = "break_of_structure"
    LIQUIDITY_SWEEP = "liquidity_sweep"
    MITIGATION_BLOCK = "mitigation_block"
    INDUCEMENT = "inducement"
    SUPPLY_ZONE = "supply_zone"
    DEMAND_ZONE = "demand_zone"


class Zone(str, Enum):
    PREMIUM = "premium"
    EQUILIBRIUM = "equilibrium"
    DISCOUNT = "discount"


class TrendBias(str, Enum):
    """
    Directional bias derived from SMC market structure events.

    Used consistently across TimeframeAnalysis and MTFAnalysis to avoid
    raw string literals for direction/bias fields.

    Values intentionally mirror the 'direction' strings used in
    SMCStructure so equality comparisons work across both types.
    """
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class SMCStructure:
    """A detected SMC structure on a specific pair/timeframe."""
    pattern: SMCPattern
    pair: str
    timeframe: str
    zone: Zone
    price_low: float
    price_high: float
    direction: str                       # "bullish" | "bearish"
    strength: float                      # 0.0 – 1.0
    validated: bool = False              # True after price confirms the level
    detected_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TimeframeAnalysis:
    """
    All SMC detection results for a single timeframe.

    Replaces parallel per-category dicts with a single owned container
    so every timeframe is fully self-contained. The caller (e.g. the
    market scanner) correlates results across timeframes via MTFAnalysis.

    bias:
        Derived from the most recent market structure event (BOS/CHoCH)
        on this timeframe. NEUTRAL when no structure events are present.
    """
    timeframe:    str                  # "H4" | "H1" | "M15" | "M5"
    structures:   List[SMCStructure]   # BOS and CHoCH events
    order_blocks: List[SMCStructure]   # Order Blocks and Breaker Blocks
    fvgs:         List[SMCStructure]   # Fair Value Gaps and Imbalances
    liquidity:    List[SMCStructure]   # Liquidity pools, sweeps, swing levels
    supply_demand: List[SMCStructure]  # Supply/Demand Zones and Mitigation Blocks
    bias:         TrendBias            # Direction bias for this timeframe


@dataclass
class MTFAnalysis:
    """
    Aggregated multi-timeframe SMC analysis result.

    Roadmap hierarchy (Section 6.12):
      H4  — higher-timeframe bias source
      H1  — primary market structure
      M15 — confirmation layer
      M5  — entry context

    Alignment score weighting (H1 highest, M5 lowest):
      H1  = 0.50
      M15 = 0.30
      M5  = 0.20
    Weights sum to 1.0 across all three lower timeframes. When one or
    more lower timeframes are absent, the score is computed using only
    the available weights, re-normalised to the available weight sum.

    pair:
        Left as "" (the _PAIR_UNSET sentinel) by the SMC engine.
        Caller enriches this field after receiving the result.

    dominant_timeframe:
        The highest timeframe with a non-neutral bias and at least one
        confirmed structure event. "" when none qualify.

    conflicting_timeframes:
        Lower timeframes (H1/M15/M5) whose bias actively contradicts
        the overall bias. Neutral timeframes are excluded — absence of
        signal is not a conflict.
    """
    bias:                   TrendBias
    aligned:                bool
    alignment_score:        float
    dominant_timeframe:     str
    conflicting_timeframes: List[str]
    available_timeframes:   List[str]
    missing_timeframes:     List[str]
    timeframes:             Dict[str, TimeframeAnalysis]
    dominant_zones:         List[SMCStructure]
    analysed_at:            datetime = field(default_factory=datetime.utcnow)
    pair:                   str = ""


@dataclass
class ConfluenceFactor:
    """
    Individual scored component within a ConfluenceResult.

    name      — machine-readable factor identifier (e.g. "order_block_alignment")
    score     — points this factor contributed (0 – max_score)
    max_score — maximum possible contribution from this factor
    confirmed — True when score > 0 (factor fired in the expected direction)
    reason    — one-sentence human-readable explanation of the result
    """
    name:      str
    score:     float
    max_score: float
    confirmed: bool
    reason:    str


@dataclass
class ConfluenceResult:
    """
    Normalized 0–100 confluence score for a pair/price at a point in time.

    Eight independent factors are evaluated and their scores summed.
    The total is already on a 0–100 scale (factor max scores sum to 100).

    score           — 0–100 composite score (integer, rounded)
    bias            — overall directional bias inherited from the MTFAnalysis
    factors         — ordered list of individual ConfluenceFactor breakdowns
    confirmed_count — number of factors where score > 0
    total_factors   — total factor count (always 8 when all inputs are valid)
    analysed_at     — UTC computation time
    """
    score:           int
    bias:            TrendBias
    factors:         List[ConfluenceFactor]
    confirmed_count: int
    total_factors:   int
    analysed_at:     datetime = field(default_factory=datetime.utcnow)


class ISMCAnalyzer(ABC):
    """Detect and classify SMC structures from raw OHLCV data."""

    @abstractmethod
    def detect_order_blocks(
        self, ohlcv: List[Dict[str, Any]], timeframe: str
    ) -> List[SMCStructure]:
        """Identify unmitigated Order Blocks and Breaker Blocks."""
        ...

    @abstractmethod
    def detect_fair_value_gaps(
        self, ohlcv: List[Dict[str, Any]], timeframe: str
    ) -> List[SMCStructure]:
        """Detect Fair Value Gaps and price imbalances."""
        ...

    @abstractmethod
    def detect_liquidity_levels(
        self, ohlcv: List[Dict[str, Any]], timeframe: str
    ) -> List[SMCStructure]:
        """Map equal highs/lows, swing points, and stop-hunt levels."""
        ...

    @abstractmethod
    def detect_market_structure(
        self, ohlcv: List[Dict[str, Any]], timeframe: str
    ) -> List[SMCStructure]:
        """Identify CHoCH and BOS events for trend direction."""
        ...

    @abstractmethod
    def classify_price_zone(self, pair: str, current_price: float) -> Zone:
        """Return whether price is in a Premium, Equilibrium, or Discount zone."""
        ...

    @abstractmethod
    def detect_supply_demand(
        self, ohlcv: List[Dict[str, Any]], timeframe: str
    ) -> List[SMCStructure]:
        """
        Detect Supply and Demand zones from consolidation bases.

        Supply Zone — base area preceding a strong bearish impulse.
        Demand Zone — base area preceding a strong bullish impulse.
        Mitigated zones are returned as MITIGATION_BLOCK.
        """
        ...

    @abstractmethod
    def analyze_multi_timeframe(
        self,
        ohlcv_per_timeframe: Dict[str, List[Dict[str, Any]]],
    ) -> MTFAnalysis:
        """
        Aggregate SMC analysis across multiple timeframes.

        Accepts any subset of {"H4", "H1", "M15", "M5"} as keys.
        The caller is responsible for pair association;
        MTFAnalysis.pair is always "" on return (the _PAIR_UNSET sentinel).
        """
        ...

    @abstractmethod
    def score_confluence(
        self,
        mtf: MTFAnalysis,
        ohlcv: List[Dict[str, Any]],
        current_price: float,
    ) -> ConfluenceResult:
        """
        Compute a normalized 0–100 confluence score from pre-computed SMC data.

        Evaluates eight independent factors (max pts each):
          1. BOS/CHoCH multi-timeframe alignment  (20)
          2. Order Block at current price          (15)
          3. Fair Value Gap at current price       (15)
          4. Liquidity Sweep confirmation          (15)
          5. Supply/Demand zone alignment          (15)
          6. Premium/Discount zone alignment       (10)
          7. RSI-14 confirmation                    (5)
          8. EMA-20 confirmation                    (5)

        All SMC inputs are taken from the pre-computed MTFAnalysis; ohlcv is
        used only for RSI-14 and EMA-20 calculations. No detect_* methods are
        called inside this method. Analysis-only — no trade decisions.
        """
        ...
