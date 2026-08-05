"""
MT5 / Exness Integration — abstract interface contracts.

This module is the ONLY place in the codebase that communicates with
MetaTrader 5. All other modules interact with it through these interfaces,
keeping broker-specific logic isolated.

Note: The MetaTrader5 Python package only works on Windows (or via Wine
on Linux). On Replit, use the stub/simulation implementation for development.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class AccountInfo:
    """Snapshot of the connected MT5 account."""
    login: int
    server: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    leverage: int
    currency: str
    connected: bool = False


@dataclass
class BrokerPosition:
    """An open position as reported by the broker."""
    ticket: int
    symbol: str
    type: str                          # "buy" | "sell"
    volume: float
    open_price: float
    current_price: float
    sl: float
    tp: float
    profit: float
    open_time: datetime
    comment: str = ""


@dataclass
class BrokerOrder:
    """A pending limit/stop order on the broker."""
    ticket: int
    symbol: str
    type: str
    volume: float
    price: float
    sl: float
    tp: float
    expiry: Optional[datetime] = None


class IMT5Connector(ABC):
    """Low-level MT5 terminal adapter."""

    @abstractmethod
    async def connect(self) -> bool:
        """Initialize and authenticate with the MT5 terminal. Returns True on success."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully disconnect from MT5."""
        ...

    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        """Return current account snapshot."""
        ...

    @abstractmethod
    async def get_positions(self) -> List[BrokerPosition]:
        """Return all currently open positions."""
        ...

    @abstractmethod
    async def get_orders(self) -> List[BrokerOrder]:
        """Return all pending orders."""
        ...

    @abstractmethod
    async def send_market_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        sl: float,
        tp: float,
        comment: str = "",
    ) -> Dict[str, Any]:
        """Send a market execution order. Returns broker response dict."""
        ...

    @abstractmethod
    async def close_position(self, ticket: int) -> Dict[str, Any]:
        """Close an open position by ticket number."""
        ...

    @abstractmethod
    async def modify_position(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> bool:
        """Modify SL/TP on an open position. Returns True on ACK."""
        ...

    @abstractmethod
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: int,
        count: int,
    ) -> List[Dict[str, Any]]:
        """Fetch OHLCV bars from MT5 history."""
        ...

    @abstractmethod
    async def get_tick(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch real-time tick data for `symbol` via mt5.symbol_info_tick().

        Returns a dict with keys:
            "bid"       — float    (best bid price)
            "ask"       — float    (best ask price)
            "spread"    — float    (ask − bid, in price units)
            "last"      — float    (last trade price; 0.0 if unavailable)
            "volume"    — int      (tick volume at last price)
            "tick_time" — datetime (UTC timestamp of the tick)
        """
        ...
