"""
Market Data Service — MT5/Exness implementation of IMarketDataProvider.

Fetches OHLCV and tick data exclusively from the MT5/Exness connector
(RealMT5Connector).  No external data source is used.  No simulation or
demo connector is permitted.

Changes in Section 3 implementation:
- Data validation integrated via validation.py before any data leaves this
  service.
- Reconnect logic with bounded retries and exponential back-off so a
  temporary MT5 disconnect does not permanently break the service.
- Standardised bar format: every bar now carries 'symbol' and 'timeframe'
  fields so downstream modules can identify records without external context.
- connection_status property for dashboard / live-feed consumers.

Bar format contract (RealMT5Connector must honour these keys):
    "time"      — datetime (UTC)
    "open"      — float
    "high"      — float
    "low"       — float
    "close"     — float
    "volume"    — float  (tick volume)
    "spread"    — float, optional  (price units)

Additional keys injected by MarketDataService (Section 3 standardisation):
    "symbol"    — str   e.g. "EURUSD"
    "timeframe" — str   e.g. "H1"
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.modules.market_scanner.interfaces import IMarketDataProvider
from app.modules.market_scanner.validation import (
    validate_bars,
    validate_tick,
    TickValidationError,
)
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
    "M30": 30,
    "H1":  16385,
    "H4":  16388,
    "D1":  16408,
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

    Section 3 additions:
    - All returned bars pass through validate_bars() before being returned.
    - All returned ticks pass through validate_tick() before being returned.
    - Every bar dict is enriched with 'symbol' and 'timeframe' keys.
    - Reconnect logic: if a data call fails with RuntimeError the service
      attempts to reconnect (bounded retries, exponential back-off) and
      retries the call once before propagating the error.
    - connection_status property exposes the current MT5 connection state.
    """

    def __init__(self, connector: Optional[IMT5Connector] = None) -> None:
        from app.core.config import settings as _settings

        self._connector: IMT5Connector = (
            connector if connector is not None else RealMT5Connector()
        )
        self._connected = False
        self._reconnect_attempts: int = _settings.MT5_RECONNECT_ATTEMPTS
        self._reconnect_delay: float = _settings.MT5_RECONNECT_DELAY_SECONDS

    # ── Connection state ──────────────────────────────────────────────────────

    @property
    def connection_status(self) -> Dict[str, Any]:
        """
        Returns a snapshot of the MT5 connection state suitable for the
        dashboard or live-feed health checks.

        Keys:
            connected  — bool
            checked_at — datetime (UTC)
        """
        return {
            "connected": self._connected,
            "checked_at": datetime.now(timezone.utc),
        }

    # ── Internal: connection management ──────────────────────────────────────

    async def _ensure_connected(self) -> None:
        """Lazily connect on first use; raise RuntimeError if the connector refuses."""
        if not self._connected:
            ok = await self._connector.connect()
            if not ok:
                raise RuntimeError(
                    "MT5 connector failed to establish a connection. "
                    "Check MT5_ACCOUNT, MT5_PASSWORD, and MT5_SERVER in settings."
                )
            self._connected = True
            logger.info("MarketDataService: MT5 connection established.")

    async def _reconnect(self) -> bool:
        """
        Attempt to reconnect after a mid-session MT5 disconnect.

        Uses exponential back-off starting at self._reconnect_delay seconds.
        Makes at most self._reconnect_attempts attempts.
        Sets self._connected = True on success, leaves it False on failure.
        Never raises — returns True/False so callers can decide what to do.
        """
        self._connected = False
        for attempt in range(1, self._reconnect_attempts + 1):
            delay = self._reconnect_delay * (2.0 ** (attempt - 1))
            logger.warning(
                "MarketDataService: MT5 reconnect attempt %d/%d — waiting %.1fs…",
                attempt,
                self._reconnect_attempts,
                delay,
            )
            await asyncio.sleep(delay)
            try:
                ok = await self._connector.connect()
            except Exception as exc:
                logger.warning(
                    "MarketDataService: reconnect attempt %d raised: %s",
                    attempt,
                    exc,
                )
                ok = False

            if ok:
                self._connected = True
                logger.info(
                    "MarketDataService: MT5 reconnected successfully (attempt %d).",
                    attempt,
                )
                return True

        logger.error(
            "MarketDataService: MT5 reconnect failed after %d attempts — "
            "service will remain disconnected until the next successful call.",
            self._reconnect_attempts,
        )
        return False

    async def _call_with_reconnect(self, coro_factory, label: str):
        """
        Execute an async call produced by coro_factory().
        On RuntimeError, mark disconnected and attempt one reconnect cycle,
        then retry the call once.  Propagates the error if reconnect fails.
        """
        try:
            return await coro_factory()
        except RuntimeError as exc:
            logger.warning(
                "MarketDataService: %s failed (%s) — attempting reconnect.",
                label,
                exc,
            )
            reconnected = await self._reconnect()
            if not reconnected:
                raise
            # One retry after successful reconnect
            return await coro_factory()

    # ── Shutdown ──────────────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        """
        Gracefully disconnect from MT5.

        Called by MarketDataFeed.stop() after background loops have been
        cancelled so the MT5 terminal receives a clean shutdown signal.

        On non-Windows platforms the MetaTrader5 package is unavailable and
        disconnect() will raise RuntimeError; that is caught and logged at
        DEBUG level so shutdown is never blocked by a platform limitation.
        """
        if not self._connected:
            return
        try:
            await self._connector.disconnect()
            self._connected = False
            logger.info("MarketDataService: MT5 disconnected cleanly.")
        except RuntimeError as exc:
            # Expected on non-Windows — MT5 package not available.
            logger.debug("MarketDataService: disconnect skipped — %s", exc)
        except Exception as exc:
            logger.warning("MarketDataService: disconnect raised unexpected error: %s", exc)

    # ── IMarketDataProvider ───────────────────────────────────────────────────

    async def get_ohlcv(
        self,
        pair: str,
        timeframe: str,
        count: int,
    ) -> List[Dict[str, Any]]:
        """
        Fetch the last `count` OHLCV bars for `pair` on `timeframe` from MT5.

        Returned bars are:
        - Validated (invalid/corrupted bars are dropped with a warning).
        - Deduplicated by timestamp.
        - Enriched with 'symbol' and 'timeframe' keys for downstream consumers.

        Raises:
            ValueError   — unsupported timeframe string.
            RuntimeError — MT5 returned no data after reconnect attempt.
        """
        if timeframe not in _MT5_TIMEFRAMES:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. "
                f"Supported: {list(_MT5_TIMEFRAMES.keys())}"
            )

        await self._ensure_connected()

        mt5_tf = _MT5_TIMEFRAMES[timeframe]

        bars = await self._call_with_reconnect(
            lambda: self._connector.get_ohlcv(pair, mt5_tf, count),
            label=f"get_ohlcv({pair}/{timeframe})",
        )

        if not bars:
            raise RuntimeError(
                f"MT5 returned no OHLCV data for {pair}/{timeframe}."
            )

        # Validate and clean
        bars = validate_bars(bars, symbol=pair, timeframe=timeframe)

        if not bars:
            raise RuntimeError(
                f"All bars for {pair}/{timeframe} were rejected by validation."
            )

        # Standardise: inject symbol + timeframe into every bar so downstream
        # modules can identify records without carrying external context.
        for bar in bars:
            bar["symbol"] = pair
            bar["timeframe"] = timeframe

        return bars

    async def get_tick(self, pair: str) -> Dict[str, Any]:
        """
        Fetch real-time tick data from MT5 via IMT5Connector.get_tick().

        bid/ask/spread/last/tick_time come directly from mt5.symbol_info_tick()
        (no OHLCV derivation).  24h price change is computed from H1 bars
        fetched concurrently alongside the tick query.

        Returned tick is validated before being returned.

        Raises:
            RuntimeError — connector refused connection or MT5 returned no data.
            TickValidationError — MT5 returned structurally invalid tick data.
        """
        await self._ensure_connected()

        # Fetch real tick and H1 bars concurrently.
        mt5_tf = _MT5_TIMEFRAMES["H1"]

        tick_data, bars = await self._call_with_reconnect(
            lambda: asyncio.gather(
                self._connector.get_tick(pair),
                self._connector.get_ohlcv(pair, mt5_tf, 26),
            ),
            label=f"get_tick({pair})",
        )

        # Validate tick
        try:
            validate_tick(tick_data, symbol=pair)
        except TickValidationError as exc:
            raise RuntimeError(
                f"MT5 returned invalid tick data for {pair}: {exc}"
            ) from exc

        bid = tick_data["bid"]

        # 24h change: compare current bid against close ~24 H1 bars ago.
        # Use validated bars for the calculation.
        bars = validate_bars(bars, symbol=pair, timeframe="H1")
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
            "last":       tick_data.get("last", 0.0),
            "tick_time":  tick_data["tick_time"],
            "change_24h": change_pct,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
