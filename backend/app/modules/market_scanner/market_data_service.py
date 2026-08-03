"""
Market Data Service — yfinance implementation of IMarketDataProvider.

Fetches real OHLCV and tick data from Yahoo Finance.
No mock data. No fallback stubs. Raises explicitly on data errors.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.modules.market_scanner.interfaces import IMarketDataProvider

logger = logging.getLogger(__name__)

# ── Timeframe mapping ────────────────────────────────────────────────────────
# Internal code → yfinance interval.  H4 is not natively supported by
# yfinance, so it is fetched as 1h and then resampled.

_SUPPORTED_TIMEFRAMES = {"M1", "M5", "M15", "H1", "H4"}

_YF_INTERVAL: Dict[str, str] = {
    "M1":  "1m",
    "M5":  "5m",
    "M15": "15m",
    "H1":  "1h",
    # H4 handled separately — resampled from 1h
}

_YF_PERIOD: Dict[str, str] = {
    "M1":  "1d",
    "M5":  "5d",
    "M15": "5d",
    "H1":  "1mo",
    "H4":  "60d",   # fetched as 1h, resampled to 4h
}

# Pip size per pair — used to estimate spread in tick data
_JPY_PAIRS = {"USDJPY", "EURJPY", "GBPJPY"}


def _pip(pair: str) -> float:
    return 0.01 if pair in _JPY_PAIRS else 0.0001


def _to_yf_symbol(pair: str) -> str:
    """Convert internal forex symbol to yfinance ticker (e.g. EURUSD → EURUSD=X)."""
    return f"{pair}=X"


def _flatten_columns(df: "pd.DataFrame") -> "pd.DataFrame":
    """
    Newer yfinance versions may return a MultiIndex column frame when a
    single symbol is downloaded.  Flatten to a plain Index using the first
    level (field names: Open, High, Low, Close, Volume).
    """
    import pandas as pd
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def _resample_4h(df: "pd.DataFrame") -> "pd.DataFrame":
    """Resample a 1h OHLCV DataFrame to 4h bars."""
    df = df.sort_index()
    resampled = df.resample("4h").agg({
        "Open":   "first",
        "High":   "max",
        "Low":    "min",
        "Close":  "last",
        "Volume": "sum",
    }).dropna(subset=["Open", "Close"])
    return resampled


# ── MarketDataService ─────────────────────────────────────────────────────────

class MarketDataService(IMarketDataProvider):
    """
    IMarketDataProvider backed by Yahoo Finance (yfinance ≥ 0.2).

    All yfinance I/O is synchronous; every method runs blocking calls
    inside a thread-pool executor so the asyncio event loop is never blocked.

    Supported timeframes: M1, M5, M15, H1, H4.
    """

    # ------------------------------------------------------------------
    # IMarketDataProvider — public async interface
    # ------------------------------------------------------------------

    async def get_ohlcv(
        self,
        pair: str,
        timeframe: str,
        count: int,
    ) -> List[Dict[str, Any]]:
        """
        Fetch the last `count` OHLCV bars for `pair` on `timeframe`.

        Raises:
            ValueError  — unsupported timeframe.
            RuntimeError — yfinance returned no data.
        """
        if timeframe not in _SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. "
                f"Supported: {sorted(_SUPPORTED_TIMEFRAMES)}"
            )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._fetch_ohlcv_sync, pair, timeframe, count
        )

    async def get_tick(self, pair: str) -> Dict[str, Any]:
        """
        Return current bid/ask/spread/change for `pair`.

        yfinance does not expose a real order book, so:
          - bid  = last price
          - ask  = last price + 2-pip typical spread
          - spread is estimated from pip size (not broker-specific)

        Raises:
            RuntimeError — yfinance returned no price data.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fetch_tick_sync, pair)

    # ------------------------------------------------------------------
    # Synchronous helpers (run in executor)
    # ------------------------------------------------------------------

    def _fetch_ohlcv_sync(
        self, pair: str, timeframe: str, count: int
    ) -> List[Dict[str, Any]]:
        import pandas as pd
        import yfinance as yf

        yf_symbol = _to_yf_symbol(pair)

        if timeframe == "H4":
            # yfinance has no native 4h interval — resample from 1h
            raw = yf.download(
                yf_symbol,
                period=_YF_PERIOD["H4"],
                interval="1h",
                progress=False,
                auto_adjust=True,
            )
            if raw.empty:
                raise RuntimeError(
                    f"yfinance returned no data for {pair} (1h → H4 resample)"
                )
            raw = _flatten_columns(raw)
            df = _resample_4h(raw)
        else:
            interval = _YF_INTERVAL[timeframe]
            raw = yf.download(
                yf_symbol,
                period=_YF_PERIOD[timeframe],
                interval=interval,
                progress=False,
                auto_adjust=True,
            )
            if raw.empty:
                raise RuntimeError(
                    f"yfinance returned no data for {pair} ({interval})"
                )
            df = _flatten_columns(raw)
            df = df.dropna(subset=["Open", "High", "Low", "Close"])

        df = df.tail(count)

        bars: List[Dict[str, Any]] = []
        for ts, row in df.iterrows():
            # Normalise timestamp to an aware UTC datetime
            if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
                dt = ts.to_pydatetime()
            else:
                dt = pd.Timestamp(ts).tz_localize("UTC").to_pydatetime()

            bars.append({
                "time":   dt.isoformat(),
                "open":   float(row["Open"]),
                "high":   float(row["High"]),
                "low":    float(row["Low"]),
                "close":  float(row["Close"]),
                "volume": float(row.get("Volume", 0.0)),
            })
        return bars

    def _fetch_tick_sync(self, pair: str) -> Dict[str, Any]:
        import yfinance as yf

        yf_symbol = _to_yf_symbol(pair)
        ticker = yf.Ticker(yf_symbol)
        info = ticker.fast_info

        price = getattr(info, "last_price", None)
        if price is None or price != price:   # None or NaN
            raise RuntimeError(
                f"yfinance returned no price for {pair}"
            )
        price = float(price)

        prev_close = getattr(info, "previous_close", None)
        if prev_close is not None and prev_close == prev_close and prev_close > 0:
            change_pct = (price - float(prev_close)) / float(prev_close) * 100.0
        else:
            change_pct = 0.0

        pip_size = _pip(pair)
        typical_spread = pip_size * 2          # 2-pip estimate
        bid = price
        ask = price + typical_spread

        return {
            "pair":       pair,
            "bid":        bid,
            "ask":        ask,
            "spread":     typical_spread,
            "change_24h": change_pct,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
