"""
Technical Indicators — abstract interface contracts.

All indicator implementations are stateless: they receive an OHLCV list
and return a result dict. This makes them trivially testable and composable.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class IndicatorResult:
    """Uniform output wrapper for any indicator."""
    name: str
    value: Any                          # scalar, list, or dict depending on indicator
    signal: Optional[str] = None       # "buy" | "sell" | "neutral" | None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class IIndicator(ABC):
    """
    Single-indicator interface.
    Each indicator is a stateless transformer: OHLCV list → IndicatorResult.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable indicator name (e.g. 'EMA_50', 'RSI_14')."""
        ...

    @abstractmethod
    def compute(self, ohlcv: List[Dict[str, Any]]) -> IndicatorResult:
        """Compute the indicator over the supplied OHLCV series."""
        ...


class IIndicatorSuite(ABC):
    """
    Composite — runs multiple indicators and returns all results.
    Used by the Feature Extractor to build the full feature vector.
    """

    @abstractmethod
    def compute_all(
        self,
        ohlcv: List[Dict[str, Any]],
        indicators: Optional[List[str]] = None,
    ) -> Dict[str, IndicatorResult]:
        """
        Compute all registered indicators (or a subset by name).
        Returns a dict keyed by indicator name.
        """
        ...

    @abstractmethod
    def register(self, indicator: IIndicator) -> None:
        """Register an indicator with the suite."""
        ...
