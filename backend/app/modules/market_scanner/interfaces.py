"""
Market Scanner — abstract interface contracts.

The scanner monitors all configured pairs across multiple timeframes,
detects setup conditions, and hands promising pairs to the AI Engine.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ScanResult:
    """A single market opportunity identified by the scanner."""
    pair: str
    direction: str                     # "buy" | "sell"
    score: float                       # 0.0 – 1.0 composite opportunity score
    smc_pattern: str                   # e.g. "OB+BOS", "FVG+CHoCH"
    timeframe: str                     # e.g. "H4", "H1", "M15"
    confluence_factors: List[str] = field(default_factory=list)
    detected_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


class IMarketDataProvider(ABC):
    """Abstraction over a live or simulated market data source."""

    @abstractmethod
    async def get_ohlcv(
        self,
        pair: str,
        timeframe: str,
        count: int,
    ) -> List[Dict[str, Any]]:
        """Fetch the last `count` OHLCV bars for `pair` on `timeframe`."""
        ...

    @abstractmethod
    async def get_tick(self, pair: str) -> Dict[str, Any]:
        """Return the current bid/ask/spread for `pair`."""
        ...


class IMarketScanner(ABC):
    """Orchestrates multi-pair, multi-timeframe opportunity scanning."""

    @abstractmethod
    async def scan_all(self, pairs: List[str]) -> List[ScanResult]:
        """
        Run a full scan across all `pairs` and return ranked opportunities.
        Called on a scheduled interval and on-demand via the /market/scan endpoint.
        """
        ...

    @abstractmethod
    async def scan_pair(self, pair: str) -> Optional[ScanResult]:
        """
        Scan a single pair and return an opportunity if conditions are met,
        or None if no setup is detected.
        """
        ...
