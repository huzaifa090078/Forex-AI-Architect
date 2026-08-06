"""
Smart Money Concepts — base implementation scaffold.
"""

import logging
from typing import Any, Dict, List

from app.modules.smc.interfaces import ISMCAnalyzer, MTFAnalysis, SMCStructure, Zone

logger = logging.getLogger(__name__)


class BaseSMCAnalyzer(ISMCAnalyzer):
    """
    Skeleton SMC analyzer — all detection methods raise NotImplementedError.
    Implement each method with price-action algorithms operating on OHLCV lists.

    Recommended implementation order:
      1. detect_market_structure  (BOS/CHoCH — establishes directional bias)
      2. detect_order_blocks      (key supply/demand levels)
      3. detect_fair_value_gaps   (imbalances for entry refinement)
      4. detect_liquidity_levels  (stop-hunt targets)
      5. classify_price_zone      (premium / equilibrium / discount)
    """

    def detect_order_blocks(
        self, ohlcv: List[Dict[str, Any]], timeframe: str
    ) -> List[SMCStructure]:
        raise NotImplementedError("Implement order-block detection logic")

    def detect_fair_value_gaps(
        self, ohlcv: List[Dict[str, Any]], timeframe: str
    ) -> List[SMCStructure]:
        raise NotImplementedError("Implement FVG detection logic")

    def detect_liquidity_levels(
        self, ohlcv: List[Dict[str, Any]], timeframe: str
    ) -> List[SMCStructure]:
        raise NotImplementedError("Implement liquidity level mapping")

    def detect_market_structure(
        self, ohlcv: List[Dict[str, Any]], timeframe: str
    ) -> List[SMCStructure]:
        raise NotImplementedError("Implement BOS / CHoCH detection")

    def classify_price_zone(self, pair: str, current_price: float) -> Zone:
        raise NotImplementedError("Implement premium / discount zone classification")

    def detect_supply_demand(
        self, ohlcv: List[Dict[str, Any]], timeframe: str
    ) -> List[SMCStructure]:
        raise NotImplementedError("Implement supply and demand zone detection")

    def analyze_multi_timeframe(
        self,
        ohlcv_per_timeframe: Dict[str, List[Dict[str, Any]]],
    ) -> MTFAnalysis:
        raise NotImplementedError("Implement multi-timeframe SMC aggregation")
