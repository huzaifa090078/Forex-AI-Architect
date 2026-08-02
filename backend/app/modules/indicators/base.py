"""
Technical Indicators — base suite with registration and dispatch.

Built-in indicator stubs to implement:
  Trend   : EMA (20, 50, 200), SMA, VWAP, Ichimoku
  Momentum: RSI, MACD, Stochastic, CCI
  Volume  : OBV, Volume Profile
  Volatility: ATR, Bollinger Bands, Keltner Channels
  Structure : Pivot Points, Support/Resistance (auto)
"""

import logging
from typing import Any, Dict, List, Optional

from app.modules.indicators.interfaces import IIndicator, IIndicatorSuite, IndicatorResult

logger = logging.getLogger(__name__)


class IndicatorSuite(IIndicatorSuite):
    """Registry and batch runner for all registered indicators."""

    def __init__(self) -> None:
        self._registry: Dict[str, IIndicator] = {}

    def register(self, indicator: IIndicator) -> None:
        self._registry[indicator.name] = indicator
        logger.debug("Registered indicator: %s", indicator.name)

    def compute_all(
        self,
        ohlcv: List[Dict[str, Any]],
        indicators: Optional[List[str]] = None,
    ) -> Dict[str, IndicatorResult]:
        targets = indicators or list(self._registry.keys())
        results: Dict[str, IndicatorResult] = {}
        for name in targets:
            ind = self._registry.get(name)
            if ind is None:
                logger.warning("Indicator '%s' not registered; skipping", name)
                continue
            try:
                results[name] = ind.compute(ohlcv)
            except Exception as exc:
                logger.error("Indicator '%s' failed: %s", name, exc)
        return results


class BaseIndicator(IIndicator):
    """Convenience base for individual indicator implementations."""

    def __init__(self, name_: str) -> None:
        self._name = name_

    @property
    def name(self) -> str:
        return self._name

    def compute(self, ohlcv: List[Dict[str, Any]]) -> IndicatorResult:
        raise NotImplementedError(f"Implement compute() in {self.__class__.__name__}")
