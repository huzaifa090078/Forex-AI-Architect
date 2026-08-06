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
