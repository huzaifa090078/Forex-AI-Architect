"""
Trade Manager — position monitoring background task (Section 9).

TradeMonitor runs a periodic async loop that calls
ConcreteTradeManager.sync_open_positions() at a configurable interval.
It detects positions closed by the broker (SL/TP hit, manual MT5 terminal
close) and updates the local database accordingly.

Lifecycle:
  start() → creates an asyncio.Task (non-blocking).
  stop()  → cancels the task and awaits clean cancellation.

The task is registered under the name "trade-monitor" so it appears in
asyncio debug output.  Cancellation is handled correctly — CancelledError
is re-raised inside the loop and propagates to the awaiter in stop().
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class TradeMonitor:
    """Async monitoring loop for open broker positions."""

    def __init__(self, interval_seconds: Optional[float] = None) -> None:
        # Import here to avoid circular imports at module load time
        from app.modules.trade_manager.manager import trade_manager
        self._manager = trade_manager
        self._interval: float = interval_seconds or float(settings.TRADE_MONITOR_INTERVAL_SECONDS)
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """
        Start the monitoring loop as a background asyncio Task.
        Idempotent — calling start() when already running is a no-op.
        """
        if self._task is not None and not self._task.done():
            logger.warning("TradeMonitor: already running — skipping duplicate start")
            return
        logger.info("TradeMonitor: starting (interval=%.0fs)", self._interval)
        self._task = asyncio.create_task(self._loop(), name="trade-monitor")

    async def stop(self) -> None:
        """
        Cancel the monitoring loop and wait for it to finish cleanly.
        Safe to call even if start() was never called.
        """
        if self._task is None or self._task.done():
            return
        logger.info("TradeMonitor: stopping")
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("TradeMonitor: stopped")

    async def _loop(self) -> None:
        """Inner monitoring loop — runs until cancelled."""
        while True:
            try:
                positions = await self._manager.sync_open_positions()
                if positions:
                    logger.debug(
                        "TradeMonitor: sync complete — %d open broker position(s)",
                        len(positions),
                    )
            except asyncio.CancelledError:
                # Propagate so stop() can await cleanly
                raise
            except Exception as exc:
                logger.error("TradeMonitor: sync error: %s", exc)
            await asyncio.sleep(self._interval)


# Module-level singleton — wired into application lifecycle via main.py
trade_monitor = TradeMonitor()
