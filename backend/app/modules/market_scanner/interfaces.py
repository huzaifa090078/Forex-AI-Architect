"""
Market Scanner — abstract interface contracts.

The scanner monitors all configured pairs across multiple timeframes,
detects setup conditions, and hands promising pairs to the AI Engine.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class PriorityLevel(str, Enum):
    """Scanner opportunity priority, derived from composite score."""
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"


@dataclass
class ScanResult:
    """A single market opportunity identified by the scanner."""

    # ── Required fields (no defaults) ────────────────────────────────────────
    pair:              str    # e.g. "EURUSD"
    direction:         str    # "buy" | "sell" | "ranging"
    score:             float  # 0.0 – 1.0 composite opportunity score
    smc_pattern:       str    # e.g. "EMA Bullish Structure + RSI Momentum"
    timeframe:         str    # e.g. "H4", "H1", "M15"
    trend_status:      str    # "bullish" | "bearish" | "ranging"
    volatility_status: str    # "High" | "Normal" | "Low"
    volume_status:     str    # "High Volume" | "Normal Volume" | "Low Volume"
    current_price:     float  # last close price at scan time
    priority_level:    str    # PriorityLevel value: "HIGH" | "MEDIUM" | "LOW"

    # ── Optional / defaulted fields ───────────────────────────────────────────
    spread:             Optional[float]   = None          # live bid/ask spread
    session:            str               = "Unknown"     # active trading session
    confluence_factors: List[str]         = field(default_factory=list)
    detected_at:        datetime          = field(default_factory=datetime.utcnow)
    metadata:           Dict[str, Any]    = field(default_factory=dict)


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
