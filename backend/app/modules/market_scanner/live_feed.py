"""
Market Data Engine — Section 3 Live Update Infrastructure.

MarketDataFeed runs as a background service that:
1. Polls tick data for all 10 configured pairs every MARKET_TICK_INTERVAL_SECONDS.
2. Checks for new completed candles on all pairs × 7 timeframes every
   MARKET_SCAN_INTERVAL_SECONDS.
3. Fires registered async callbacks when new ticks or candles arrive.
4. Never blocks the FastAPI event loop — uses APScheduler AsyncIOScheduler.
5. Does NOT create a second scheduler if one already exists; call start() /
   stop() from the FastAPI lifespan hooks.

Usage (from main.py):
    from app.modules.market_scanner.live_feed import market_data_feed
    ...
    @app.on_event("startup")
    async def on_startup():
        await market_data_feed.start()

    @app.on_event("shutdown")
    async def on_shutdown():
        await market_data_feed.stop()

Downstream consumers subscribe via:
    market_data_feed.subscribe_ticks(async_callback)
    market_data_feed.subscribe_candles(async_callback)

Tick callback signature:    async def on_tick(pair: str, tick: dict) -> None
Candle callback signature:  async def on_candle(pair: str, timeframe: str, bar: dict) -> None

NOTE: The MetaTrader5 Python package requires Windows (or Linux + Wine + a
running MT5 terminal).  On non-Windows platforms the RealMT5Connector will
raise RuntimeError on every call.  The live feed catches those errors, logs
them as warnings, and keeps running — it will resume delivering data
automatically once an MT5 terminal becomes reachable.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

from app.modules.market_scanner.market_data_service import MarketDataService
from app.modules.market_scanner.scanner import FOREX_PAIRS, TIMEFRAMES

logger = logging.getLogger(__name__)

# Type aliases
_TickCallback   = Callable[[str, Dict[str, Any]], Coroutine]
_CandleCallback = Callable[[str, str, Dict[str, Any]], Coroutine]


class MarketDataFeed:
    """
    Background live-data feed for the Market Data Engine.

    Responsibilities:
    - Continuously poll tick data for all configured pairs.
    - Detect new completed candles across all pairs × timeframes.
    - Notify subscribers of new ticks and candles.
    - Handle MT5 disconnects gracefully (the underlying MarketDataService
      performs reconnect; the feed simply retries on the next interval).
    """

    def __init__(self, data_service: Optional[MarketDataService] = None) -> None:
        from app.core.config import settings as _settings

        self._data_service: MarketDataService = (
            data_service if data_service is not None else MarketDataService()
        )
        self._tick_interval: int   = _settings.MARKET_TICK_INTERVAL_SECONDS
        self._candle_interval: int = _settings.MARKET_SCAN_INTERVAL_SECONDS

        # Last seen candle timestamp per (pair, timeframe) — dedup guard
        self._last_candle: Dict[Tuple[str, str], datetime] = {}

        # Subscriber callbacks
        self._tick_callbacks:   List[_TickCallback]   = []
        self._candle_callbacks: List[_CandleCallback] = []

        # Background task handles
        self._tick_task:   Optional[asyncio.Task] = None
        self._candle_task: Optional[asyncio.Task] = None
        self._running = False

    # ── Public API ────────────────────────────────────────────────────────────

    def subscribe_ticks(self, callback: _TickCallback) -> None:
        """
        Register an async callback to be called when a new tick arrives.
        Signature: async def handler(pair: str, tick: dict) -> None
        """
        if callback not in self._tick_callbacks:
            self._tick_callbacks.append(callback)
            logger.debug("MarketDataFeed: tick subscriber registered (%s)", callback)

    def subscribe_candles(self, callback: _CandleCallback) -> None:
        """
        Register an async callback to be called when a new candle is detected.
        Signature: async def handler(pair: str, timeframe: str, bar: dict) -> None
        """
        if callback not in self._candle_callbacks:
            self._candle_callbacks.append(callback)
            logger.debug("MarketDataFeed: candle subscriber registered (%s)", callback)

    def unsubscribe_ticks(self, callback: _TickCallback) -> None:
        self._tick_callbacks = [c for c in self._tick_callbacks if c is not callback]

    def unsubscribe_candles(self, callback: _CandleCallback) -> None:
        self._candle_callbacks = [c for c in self._candle_callbacks if c is not callback]

    async def start(self) -> None:
        """
        Start the live-data background loops.
        Safe to call multiple times — subsequent calls are no-ops.
        """
        if self._running:
            logger.debug("MarketDataFeed.start() called but feed is already running.")
            return

        self._running = True
        self._tick_task   = asyncio.create_task(self._tick_loop(),   name="market_data_feed:ticks")
        self._candle_task = asyncio.create_task(self._candle_loop(), name="market_data_feed:candles")
        logger.info(
            "MarketDataFeed started — tick interval: %ds, candle interval: %ds, "
            "pairs: %d, timeframes: %d.",
            self._tick_interval,
            self._candle_interval,
            len(FOREX_PAIRS),
            len(TIMEFRAMES),
        )

    async def stop(self) -> None:
        """
        Stop the live-data background loops gracefully, then disconnect MT5.

        1. Sets _running = False so loops exit on their next iteration.
        2. Cancels the asyncio Tasks and waits up to 5 s each for them to
           acknowledge the cancellation.
        3. Calls MarketDataService.shutdown() to close the MT5 connection
           cleanly.  On non-Windows platforms the disconnect is a no-op.
        """
        self._running = False
        for task in (self._tick_task, self._candle_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
        self._tick_task = None
        self._candle_task = None
        # Disconnect MT5 after loops have stopped so no in-flight request
        # races with the shutdown call.
        await self._data_service.shutdown()
        logger.info("MarketDataFeed stopped.")

    @property
    def is_running(self) -> bool:
        return self._running

    def get_last_candle_time(self, pair: str, timeframe: str) -> Optional[datetime]:
        """Return the timestamp of the most recently seen completed candle, or None."""
        return self._last_candle.get((pair, timeframe))

    # ── Background loops ──────────────────────────────────────────────────────

    async def _tick_loop(self) -> None:
        """
        Continuously poll tick data for all pairs.
        Runs every self._tick_interval seconds.
        Errors on individual pairs are logged as warnings and do not abort the loop.
        """
        logger.debug("MarketDataFeed tick loop started.")
        while self._running:
            try:
                await self._poll_all_ticks()
            except Exception as exc:
                # Outer catch — should never happen because _poll_all_ticks
                # shields individual pair errors, but guard anyway.
                logger.error("MarketDataFeed tick loop unexpected error: %s", exc)
            await asyncio.sleep(self._tick_interval)

    async def _candle_loop(self) -> None:
        """
        Continuously check for new completed candles on all pairs × timeframes.
        Runs every self._candle_interval seconds.
        """
        logger.debug("MarketDataFeed candle loop started.")
        while self._running:
            try:
                await self._check_all_candles()
            except Exception as exc:
                logger.error("MarketDataFeed candle loop unexpected error: %s", exc)
            await asyncio.sleep(self._candle_interval)

    # ── Poll helpers ──────────────────────────────────────────────────────────

    async def _poll_all_ticks(self) -> None:
        """Fetch ticks for all pairs concurrently; fire callbacks for each."""
        results = await asyncio.gather(
            *[self._poll_tick(pair) for pair in FOREX_PAIRS],
            return_exceptions=True,
        )
        for pair, result in zip(FOREX_PAIRS, results):
            if isinstance(result, Exception):
                logger.warning(
                    "MarketDataFeed: tick poll failed for %s — %s", pair, result
                )

    async def _poll_tick(self, pair: str) -> None:
        """
        Fetch a single tick and fire registered tick callbacks.
        Errors are re-raised so _poll_all_ticks can log them per-pair.
        """
        tick = await self._data_service.get_tick(pair)
        await self._fire_tick_callbacks(pair, tick)

    async def _check_all_candles(self) -> None:
        """
        Check for new candles on all pairs × timeframes concurrently.
        Each check fetches only the 2 most recent bars (minimal data transfer).
        """
        tasks = [
            self._check_candle(pair, tf)
            for pair in FOREX_PAIRS
            for tf in TIMEFRAMES
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = sum(1 for r in results if isinstance(r, Exception))
        if errors:
            logger.debug(
                "MarketDataFeed: candle check completed with %d/%d errors.",
                errors, len(tasks),
            )

    async def _check_candle(self, pair: str, timeframe: str) -> None:
        """
        Fetch the latest 2 bars for pair/timeframe and fire candle callbacks
        if the most recent bar's timestamp is newer than the last seen one.

        Fetching 2 bars instead of 1 ensures the returned bar is completed
        (bar index 0 from the connector = most recent, which may still be
        forming; bar[-2] is the last completed bar).
        """
        try:
            bars = await self._data_service.get_ohlcv(pair, timeframe, 2)
        except Exception as exc:
            # Surface as debug — individual timeframe failures are expected on
            # illiquid pairs/timeframes outside market hours.
            logger.debug(
                "MarketDataFeed._check_candle(%s/%s): %s", pair, timeframe, exc
            )
            raise

        if not bars:
            return

        # Use the last bar returned (oldest-first ordering from the connector).
        # With count=2 the penultimate bar is the last completed candle.
        latest = bars[-1] if len(bars) == 1 else bars[-2]
        ts: datetime = latest["time"]

        key = (pair, timeframe)
        if self._last_candle.get(key) == ts:
            # No new candle since the last check
            return

        is_first_seen = key not in self._last_candle
        self._last_candle[key] = ts

        if not is_first_seen:
            # Only fire callbacks after the initial seed — on startup we just
            # record the current state without broadcasting stale candles.
            logger.debug(
                "MarketDataFeed: new candle detected — %s/%s @ %s",
                pair, timeframe, ts.isoformat(),
            )
            await self._fire_candle_callbacks(pair, timeframe, latest)

    # ── Callback dispatchers ──────────────────────────────────────────────────

    async def _fire_tick_callbacks(self, pair: str, tick: Dict[str, Any]) -> None:
        for cb in list(self._tick_callbacks):
            try:
                await cb(pair, tick)
            except Exception as exc:
                logger.error(
                    "MarketDataFeed: tick callback %s raised: %s", cb, exc
                )

    async def _fire_candle_callbacks(
        self, pair: str, timeframe: str, bar: Dict[str, Any]
    ) -> None:
        for cb in list(self._candle_callbacks):
            try:
                await cb(pair, timeframe, bar)
            except Exception as exc:
                logger.error(
                    "MarketDataFeed: candle callback %s raised: %s", cb, exc
                )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

#: Shared MarketDataFeed instance — import and use this throughout the app.
#: Start/stop is managed by main.py lifespan hooks.
market_data_feed: MarketDataFeed = MarketDataFeed()
