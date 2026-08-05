"""
Market Data Service — MT5/Exness implementation of IMarketDataProvider.

Fetches OHLCV and derives tick data exclusively from the MT5/Exness connector
(RealMT5Connector).  No external data source is used.  No simulation or demo
connector is permitted.

Bar format contract (RealMT5Connector must honour this when implemented):
  Each bar dict must contain the keys:
    "time"   — ISO-8601 datetime string or Unix timestamp (int/float)
    "open"   — float
    "high"   — float
    "low"    — float
    "close"  — float
    "volume" — float  (tick volume or real volume)
    "spread" — float, optional  (price units; used by get_tick if present)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.modules.market_scanner.interfaces import IMarketDataProvider
from app.modules.mt5_integration.interfaces import IMT5Connector
from app.modules.mt5_integration.base import RealMT5Connector

logger = logging.getLogger(__name__)

# ── MT5 timeframe integer constants ──────────────────────────────────────────
# Values match the MetaTrader5 Python package (TIMEFRAME_* enum).
# Defined here to avoid importing the package, which requires Windows.

_MT5_TIMEFRAMES: Dict[str, int] = {
    "M1":  1,
    "M5":  5,
    "M15": 15,
    "H1":  16385,
    "H4":  16388,
}

# Pairs priced in JPY have a 2-decimal pip (0.01); all others use 0.0001
_JPY_PAIRS = {"USDJPY", "EURJPY", "GBPJPY"}


def _pip(pair: str) -> float:
    return 0.01 if pair in _JPY_PAIRS else 0.0001


def _close(bar: Dict[str, Any]) -> float:
    """Extract close price tolerating either lowercase or title-case keys."""
    v = bar.get("close") if bar.get("close") is not None else bar.get("Close")
    if v is None:
        raise KeyError(f"Bar dict has no 'close' key: {list(bar.keys())}")
    return float(v)


# ── MarketDataService ─────────────────────────────────────────────────────────

class MarketDataService(IMarketDataProvider):
    """
    IMarketDataProvider backed by the MT5/Exness connector.

    All connector methods are already declared async; no executor wrapping is
    needed here.  When RealMT5Connector delegates to the blocking MT5 C-API,
    it is responsible for running those calls in a thread-pool executor.
    """

    def __init__(self, connector: Optional[IMT5Connector] = None) -> None:
        self._connector: IMT5Connector = connector if connector is not None else RealMT5Connector()
        self._connected = False

    # ── Connection management ─────────────────────────────────────────────────

    async def _ensure_connected(self) -> None:
        """Lazily connect on first use; raise if the connector refuses."""
        if not self._connected:
            ok = await self._connector.connect()
            if not ok:
                raise RuntimeError(
                    "MT5 connector failed to establish a connection. "
                    "Check MT5_ACCOUNT, MT5_PASSWORD, and MT5_SERVER in settings."
                )
            self._connected = True

    # ── IMarketDataProvider ───────────────────────────────────────────────────

    async def get_ohlcv(
        self,
        pair: str,
        timeframe: str,
        count: int,
    ) -> List[Dict[str, Any]]:
        """
        Fetch the last `count` OHLCV bars for `pair` on `timeframe` from MT5.

        Raises:
            ValueError   — unsupported timeframe string.
            RuntimeError — MT5 returned no data for this pair/timeframe.
        """
        if timeframe not in _MT5_TIMEFRAMES:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. "
                f"Supported: {list(_MT5_TIMEFRAMES.keys())}"
            )

        await self._ensure_connected()

        mt5_tf = _MT5_TIMEFRAMES[timeframe]
        bars = await self._connector.get_ohlcv(pair, mt5_tf, count)

        if not bars:
            raise RuntimeError(
                f"MT5 returned no OHLCV data for {pair}/{timeframe}."
            )
        return bars

    async def get_tick(self, pair: str) -> Dict[str, Any]:
        """
        Fetch real-time tick data from MT5 via IMT5Connector.get_tick().

        bid/ask/spread/last/tick_time come directly from mt5.symbol_info_tick()
        (no OHLCV derivation).  24h price change is computed from H1 bars
        fetched concurrently alongside the tick query.

        Raises:
            RuntimeError — connector refused connection or MT5 returned no data.
        """
        await self._ensure_connected()

        # Fetch real tick and H1 bars concurrently.
        # tick_data → real-time bid/ask/spread from mt5.symbol_info_tick()
        # bars      → 24h change calculation only (26 bars = ~25h window)
        mt5_tf = _MT5_TIMEFRAMES["H1"]
        tick_data, bars = await asyncio.gather(
            self._connector.get_tick(pair),
            self._connector.get_ohlcv(pair, mt5_tf, 26),
        )

        bid = tick_data["bid"]

        # 24h change: compare current bid against close ~24 H1 bars ago
        if len(bars) >= 25:
            prev = _close(bars[-25])
            change_pct = ((bid - prev) / prev * 100.0) if prev > 0.0 else 0.0
        else:
            change_pct = 0.0

        return {
            "pair":       pair,
            "bid":        bid,
            "ask":        tick_data["ask"],
            "spread":     tick_data["spread"],
            "last":       tick_data["last"],
            "tick_time":  tick_data["tick_time"],
            "change_24h": change_pct,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
