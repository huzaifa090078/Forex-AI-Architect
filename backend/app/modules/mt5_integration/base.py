"""
MT5 Integration — RealMT5Connector.

RealMT5Connector: production implementation using the MetaTrader5 package.
Only functional on Windows (or Linux with Wine + MT5 terminal installed).
This is the only permitted connector — no simulation or demo connector exists.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.modules.mt5_integration.interfaces import (
    AccountInfo,
    BrokerOrder,
    BrokerPosition,
    IMT5Connector,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safe import — MetaTrader5 is only available on Windows (or Wine on Linux).
# If the package is absent the rest of the backend can still start; a clear
# RuntimeError is raised at connect() time rather than at module import time.
# ---------------------------------------------------------------------------
try:
    import MetaTrader5 as mt5  # type: ignore[import]

    _MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore[assignment]
    _MT5_AVAILABLE = False
    logger.warning(
        "MetaTrader5 Python package could not be imported. "
        "RealMT5Connector will raise RuntimeError on use. "
        "The package requires Windows (or Linux + Wine + a running MT5 terminal)."
    )


def _require_mt5() -> None:
    """Raise a descriptive RuntimeError if the MetaTrader5 package is unavailable."""
    if not _MT5_AVAILABLE:
        raise RuntimeError(
            "MetaTrader5 Python package is not available on this platform. "
            "The package requires Windows (or Linux with Wine and a running MT5 terminal). "
            "Install it with: pip install MetaTrader5"
        )


def _mask_account(account: int) -> str:
    """
    Return a masked representation of an MT5 account number for safe logging.

    Shows only the last 4 digits to aid debugging without exposing the full
    account number in log files.  Treats accounts with fewer than 4 digits as
    fully masked so short identifiers are never unintentionally leaked.

    Examples:
        12345678  →  "****5678"
        123       →  "****"
    """
    s = str(account)
    if len(s) <= 4:
        return "****"
    return f"****{s[-4:]}"


# MT5 position-type integer → canonical direction string
_POSITION_TYPE: Dict[int, str] = {
    0: "buy",   # POSITION_TYPE_BUY
    1: "sell",  # POSITION_TYPE_SELL
}

# MT5 pending-order-type integer → canonical string
_ORDER_TYPE: Dict[int, str] = {
    0: "buy",
    1: "sell",
    2: "buy_limit",
    3: "sell_limit",
    4: "buy_stop",
    5: "sell_stop",
    6: "buy_stop_limit",
    7: "sell_stop_limit",
}


class RealMT5Connector(IMT5Connector):
    """
    Production MT5 connector using the MetaTrader5 Python package.

    All credentials are read exclusively from environment-backed application
    settings (MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER, MT5_TERMINAL_PATH).
    No credentials are hard-coded or defaulted here.

    Because the MetaTrader5 package exposes a blocking C-extension API, every
    call is dispatched to a thread-pool executor so it does not block the
    asyncio event loop.
    """

    def __init__(self) -> None:
        # Deferred import avoids circular imports at module load time.
        from app.core.config import settings as _settings

        self._settings = _settings

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _run(self, fn, *args, **kwargs):
        """Offload a blocking MT5 call to the default thread-pool executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    # ------------------------------------------------------------------
    # IMT5Connector — lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Initialize the MT5 terminal and authenticate with the trading account."""
        _require_mt5()

        cfg = self._settings

        # mt5.initialize() optionally accepts the terminal executable path.
        # Passing an empty string causes errors, so map it to None.
        terminal_path = cfg.MT5_TERMINAL_PATH if cfg.MT5_TERMINAL_PATH else None
        init_kwargs: Dict[str, Any] = {}
        if terminal_path:
            init_kwargs["path"] = terminal_path

        initialized: bool = await self._run(mt5.initialize, **init_kwargs)
        if not initialized:
            error = await self._run(mt5.last_error)
            logger.error("mt5.initialize() failed: %s", error)
            return False

        logged_in: bool = await self._run(
            mt5.login,
            cfg.MT5_ACCOUNT,
            password=cfg.MT5_PASSWORD,
            server=cfg.MT5_SERVER,
        )
        if not logged_in:
            error = await self._run(mt5.last_error)
            logger.error(
                "mt5.login() failed — account: %s, server: %s, error: %s",
                _mask_account(cfg.MT5_ACCOUNT),
                cfg.MT5_SERVER,
                error,
            )
            await self._run(mt5.shutdown)
            return False

        logger.info(
            "MT5 connected — account: %s, server: %s",
            _mask_account(cfg.MT5_ACCOUNT),
            cfg.MT5_SERVER,
        )
        return True

    async def disconnect(self) -> None:
        """Shut down the MT5 terminal connection gracefully."""
        _require_mt5()
        await self._run(mt5.shutdown)
        logger.info("MT5 connection closed.")

    # ------------------------------------------------------------------
    # IMT5Connector — account / portfolio data
    # ------------------------------------------------------------------

    async def get_account_info(self) -> AccountInfo:
        """Return a current snapshot of the connected trading account."""
        _require_mt5()

        raw = await self._run(mt5.account_info)
        if raw is None:
            error = await self._run(mt5.last_error)
            raise RuntimeError(f"mt5.account_info() returned None: {error}")

        return AccountInfo(
            login=raw.login,
            server=raw.server,
            balance=raw.balance,
            equity=raw.equity,
            margin=raw.margin,
            free_margin=raw.margin_free,
            leverage=raw.leverage,
            currency=raw.currency,
            connected=True,
        )

    async def get_positions(self) -> List[BrokerPosition]:
        """Return all currently open positions."""
        _require_mt5()

        raw_positions = await self._run(mt5.positions_get)
        if raw_positions is None:
            error = await self._run(mt5.last_error)
            raise RuntimeError(f"mt5.positions_get() returned None: {error}")

        result: List[BrokerPosition] = []
        for p in raw_positions:
            result.append(
                BrokerPosition(
                    ticket=p.ticket,
                    symbol=p.symbol,
                    type=_POSITION_TYPE.get(p.type, str(p.type)),
                    volume=p.volume,
                    open_price=p.price_open,
                    current_price=p.price_current,
                    sl=p.sl,
                    tp=p.tp,
                    profit=p.profit,
                    open_time=datetime.fromtimestamp(p.time, tz=timezone.utc),
                    comment=p.comment,
                )
            )
        return result

    async def get_orders(self) -> List[BrokerOrder]:
        """Return all pending (not yet filled) orders."""
        _require_mt5()

        raw_orders = await self._run(mt5.orders_get)
        if raw_orders is None:
            error = await self._run(mt5.last_error)
            raise RuntimeError(f"mt5.orders_get() returned None: {error}")

        result: List[BrokerOrder] = []
        for o in raw_orders:
            expiry: Optional[datetime] = (
                datetime.fromtimestamp(o.time_expiration, tz=timezone.utc)
                if o.time_expiration
                else None
            )
            result.append(
                BrokerOrder(
                    ticket=o.ticket,
                    symbol=o.symbol,
                    type=_ORDER_TYPE.get(o.type, str(o.type)),
                    volume=o.volume_initial,
                    price=o.price_open,
                    sl=o.sl,
                    tp=o.tp,
                    expiry=expiry,
                )
            )
        return result

    # ------------------------------------------------------------------
    # IMT5Connector — order execution
    # ------------------------------------------------------------------

    async def send_market_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        sl: float,
        tp: float,
        comment: str = "",
    ) -> Dict[str, Any]:
        """
        Send a market-execution order.

        direction must be "buy" or "sell" (case-insensitive).
        Returns the full broker response as a plain dict.
        """
        _require_mt5()

        direction_lower = direction.lower()
        if direction_lower == "buy":
            order_type = mt5.ORDER_TYPE_BUY
            tick = await self._run(mt5.symbol_info_tick, symbol)
            if tick is None:
                raise RuntimeError(
                    f"mt5.symbol_info_tick('{symbol}') returned None — "
                    "symbol may be unavailable or the terminal is disconnected."
                )
            price = tick.ask
        elif direction_lower == "sell":
            order_type = mt5.ORDER_TYPE_SELL
            tick = await self._run(mt5.symbol_info_tick, symbol)
            if tick is None:
                raise RuntimeError(
                    f"mt5.symbol_info_tick('{symbol}') returned None — "
                    "symbol may be unavailable or the terminal is disconnected."
                )
            price = tick.bid
        else:
            raise ValueError(
                f"Unknown direction '{direction}'. Expected 'buy' or 'sell'."
            )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "sl": float(sl),
            "tp": float(tp),
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = await self._run(mt5.order_send, request)
        if result is None:
            error = await self._run(mt5.last_error)
            raise RuntimeError(f"mt5.order_send() returned None: {error}")

        return result._asdict()

    async def close_position(self, ticket: int) -> Dict[str, Any]:
        """
        Close an open position by ticket number.

        Looks up the live position to obtain its symbol, volume, and direction,
        then sends a counter-direction TRADE_ACTION_DEAL at the current market price.
        Returns the full broker response as a plain dict.
        """
        _require_mt5()

        positions = await self._run(mt5.positions_get, ticket=ticket)
        if not positions:
            raise RuntimeError(
                f"No open position found with ticket {ticket}. "
                "It may already be closed or the ticket is invalid."
            )

        pos = positions[0]
        symbol = pos.symbol
        volume = float(pos.volume)

        # Counter-direction: long→sell to close, short→buy to close.
        if pos.type == mt5.POSITION_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            tick = await self._run(mt5.symbol_info_tick, symbol)
            if tick is None:
                raise RuntimeError(
                    f"mt5.symbol_info_tick('{symbol}') returned None."
                )
            price = tick.bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            tick = await self._run(mt5.symbol_info_tick, symbol)
            if tick is None:
                raise RuntimeError(
                    f"mt5.symbol_info_tick('{symbol}') returned None."
                )
            price = tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "comment": f"close #{ticket}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = await self._run(mt5.order_send, request)
        if result is None:
            error = await self._run(mt5.last_error)
            raise RuntimeError(
                f"mt5.order_send() (close position #{ticket}) returned None: {error}"
            )

        return result._asdict()

    async def modify_position(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> bool:
        """
        Modify the SL and/or TP on an open position.

        Values not supplied (None) are preserved from the live position.
        Returns True when the terminal acknowledges success (TRADE_RETCODE_DONE).
        """
        _require_mt5()

        positions = await self._run(mt5.positions_get, ticket=ticket)
        if not positions:
            raise RuntimeError(
                f"No open position found with ticket {ticket}."
            )

        pos = positions[0]
        new_sl = float(sl) if sl is not None else pos.sl
        new_tp = float(tp) if tp is not None else pos.tp

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": new_sl,
            "tp": new_tp,
        }

        result = await self._run(mt5.order_send, request)
        if result is None:
            error = await self._run(mt5.last_error)
            raise RuntimeError(
                f"mt5.order_send() (SLTP #{ticket}) returned None: {error}"
            )

        # TRADE_RETCODE_DONE = 10009
        return result.retcode == mt5.TRADE_RETCODE_DONE

    # ------------------------------------------------------------------
    # IMT5Connector — market data
    # ------------------------------------------------------------------

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: int,
        count: int,
    ) -> List[Dict[str, Any]]:
        """
        Fetch the most recent `count` completed OHLCV bars.

        `timeframe` must be one of the mt5.TIMEFRAME_* integer constants
        (e.g. mt5.TIMEFRAME_M1, mt5.TIMEFRAME_H1, mt5.TIMEFRAME_D1).

        Returns bars in ascending time order (oldest first), matching the
        order returned by mt5.copy_rates_from_pos with start_pos=0.

        Bar format contract (required by market_data_service and indicators):
            "time"        — datetime (UTC)
            "open"        — float
            "high"        — float
            "low"         — float
            "close"       — float
            "volume"      — float  (tick volume; required by indicators/calculations.py)
            "spread"      — float  (price units, not MT5 points; required by market_data_service.get_tick)
            "tick_volume" — int    (raw MT5 value, kept for completeness)
            "real_volume" — int    (raw MT5 value, kept for completeness)
        """
        _require_mt5()

        # Fetch symbol point size once to convert spread from MT5 integer points
        # to price units (e.g. 10 points × 0.00001 = 0.0001 for EURUSD).
        # market_data_service.get_tick() uses spread as a price-unit offset for
        # the ask price — passing raw MT5 points would produce ask = bid + 10.0,
        # which is completely wrong for forex.
        symbol_info = await self._run(mt5.symbol_info, symbol)
        if symbol_info is not None:
            point: float = symbol_info.point
        else:
            # symbol_info unavailable — spread will fall back to 0.0, which
            # causes market_data_service to use its own 2-pip estimate instead.
            logger.warning(
                "mt5.symbol_info('%s') returned None; spread will be 0.0 "
                "(market_data_service will apply its 2-pip fallback).",
                symbol,
            )
            point = 0.0

        # start_pos=0 means the most recent bar; the result is oldest-first.
        rates = await self._run(
            mt5.copy_rates_from_pos, symbol, timeframe, 0, count
        )
        if rates is None:
            error = await self._run(mt5.last_error)
            raise RuntimeError(
                f"mt5.copy_rates_from_pos('{symbol}', {timeframe}, 0, {count}) "
                f"returned None: {error}"
            )

        result: List[Dict[str, Any]] = []
        for bar in rates:
            # "volume" is required by indicators/calculations.py extract_arrays().
            # Absence causes silent 0.0 fallback, breaking VWAP and OBV for all bars.
            tick_vol = int(bar["tick_volume"])
            real_vol = int(bar["real_volume"])
            spread_pts = int(bar["spread"])

            result.append(
                {
                    "time":        datetime.fromtimestamp(int(bar["time"]), tz=timezone.utc),
                    "open":        float(bar["open"]),
                    "high":        float(bar["high"]),
                    "low":         float(bar["low"]),
                    "close":       float(bar["close"]),
                    # Required by bar format contract — tick volume as canonical "volume".
                    "volume":      float(tick_vol),
                    # Spread in price units (market_data_service contract).
                    "spread":      float(spread_pts) * point,
                    # Raw MT5 fields preserved for callers that want them explicitly.
                    "tick_volume": tick_vol,
                    "real_volume": real_vol,
                }
            )
        return result

    async def get_tick(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch real-time tick data via mt5.symbol_info_tick().

        Returns bid, ask, spread (ask − bid), last trade price, tick volume,
        and the UTC timestamp of the tick as reported by the MT5 terminal.
        No OHLCV bars are used; this is a direct terminal query.
        """
        _require_mt5()

        tick = await self._run(mt5.symbol_info_tick, symbol)
        if tick is None:
            error = await self._run(mt5.last_error)
            raise RuntimeError(
                f"mt5.symbol_info_tick('{symbol}') returned None: {error}. "
                "The symbol may be unavailable or the terminal is disconnected."
            )

        return {
            "bid":       float(tick.bid),
            "ask":       float(tick.ask),
            "spread":    float(tick.ask - tick.bid),
            "last":      float(tick.last),
            "volume":    int(tick.volume),
            "tick_time": datetime.fromtimestamp(tick.time, tz=timezone.utc),
        }

    # ------------------------------------------------------------------
    # RealMT5Connector — infrastructure / health
    # ------------------------------------------------------------------

    async def check_symbols(self, symbols: List[str]) -> Dict[str, bool]:
        """
        Check whether each symbol in `symbols` is available in the MT5 terminal.

        Calls mt5.symbol_info(symbol) for every symbol concurrently and returns
        a dict mapping each symbol to True (available) or False (not found /
        not visible in Market Watch).

        This method is intentionally NOT part of IMT5Connector — it is an
        infrastructure / health-check operation specific to RealMT5Connector.
        Callers that need symbol availability should downcast or hold a concrete
        reference to RealMT5Connector.

        Must be called after a successful connect(); raises RuntimeError when
        MT5 is not available (non-Windows) or the package is absent.
        """
        _require_mt5()

        # Fetch symbol_info for all symbols concurrently via the thread-pool
        # executor so the async event loop is never blocked.
        results: List[Any] = await asyncio.gather(
            *[self._run(mt5.symbol_info, sym) for sym in symbols],
            return_exceptions=True,
        )

        availability: Dict[str, bool] = {}
        for sym, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.warning(
                    "check_symbols: mt5.symbol_info('%s') raised %s", sym, result
                )
                availability[sym] = False
            else:
                # mt5.symbol_info returns None when the symbol is unknown.
                availability[sym] = result is not None

        return availability
