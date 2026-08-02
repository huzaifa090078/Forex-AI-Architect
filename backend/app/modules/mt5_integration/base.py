"""
MT5 Integration — base / stub implementations.

SimulatedMT5Connector: returns realistic-looking stub data so the rest
of the platform can be developed and tested without a live MT5 terminal.

RealMT5Connector: real implementation using the MetaTrader5 package.
Only functional on Windows (or Linux with Wine + MT5).
"""

import logging
from typing import Any, Dict, List, Optional

from app.modules.mt5_integration.interfaces import (
    IMT5Connector,
    AccountInfo,
    BrokerPosition,
    BrokerOrder,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class SimulatedMT5Connector(IMT5Connector):
    """
    Development stub — no real broker connection.
    All methods return empty or sensible default data so the rest of the
    platform can be developed and tested in isolation.
    """

    async def connect(self) -> bool:
        logger.info("[SimMT5] Connected (simulation mode)")
        return True

    async def disconnect(self) -> None:
        logger.info("[SimMT5] Disconnected")

    async def get_account_info(self) -> AccountInfo:
        return AccountInfo(
            login=settings.MT5_ACCOUNT,
            server=settings.MT5_SERVER or "SimServer",
            balance=10_000.0,
            equity=10_250.0,
            margin=125.0,
            free_margin=10_125.0,
            leverage=500,
            currency="USD",
            connected=True,
        )

    async def get_positions(self) -> List[BrokerPosition]:
        return []

    async def get_orders(self) -> List[BrokerOrder]:
        return []

    async def send_market_order(self, symbol, direction, volume, sl, tp, comment=""):
        logger.info("[SimMT5] Order sent: %s %s %.2f lots", direction, symbol, volume)
        return {"retcode": 10009, "order": 0, "comment": "simulation"}

    async def close_position(self, ticket: int) -> Dict[str, Any]:
        logger.info("[SimMT5] Position %d closed", ticket)
        return {"retcode": 10009, "comment": "simulation"}

    async def modify_position(self, ticket, sl=None, tp=None) -> bool:
        logger.info("[SimMT5] Position %d modified", ticket)
        return True

    async def get_ohlcv(self, symbol, timeframe, count) -> List[Dict[str, Any]]:
        return []


class RealMT5Connector(IMT5Connector):
    """
    Production MT5 connector using the MetaTrader5 Python package.
    Requires Windows or Linux with Wine + MT5 terminal installed.
    Import MetaTrader5 here (not at module level) to avoid import errors
    on non-Windows platforms.
    """

    async def connect(self) -> bool:
        raise NotImplementedError(
            "Import MetaTrader5 and implement: mt5.initialize(), mt5.login()"
        )

    async def disconnect(self) -> None:
        raise NotImplementedError("Implement: mt5.shutdown()")

    async def get_account_info(self) -> AccountInfo:
        raise NotImplementedError("Implement: mt5.account_info()")

    async def get_positions(self) -> List[BrokerPosition]:
        raise NotImplementedError("Implement: mt5.positions_get()")

    async def get_orders(self) -> List[BrokerOrder]:
        raise NotImplementedError("Implement: mt5.orders_get()")

    async def send_market_order(self, symbol, direction, volume, sl, tp, comment=""):
        raise NotImplementedError("Implement: mt5.order_send() with MqlTradeRequest")

    async def close_position(self, ticket: int) -> Dict[str, Any]:
        raise NotImplementedError("Implement: mt5.order_send() with TRADE_ACTION_DEAL close")

    async def modify_position(self, ticket, sl=None, tp=None) -> bool:
        raise NotImplementedError("Implement: mt5.order_send() with TRADE_ACTION_SLTP")

    async def get_ohlcv(self, symbol, timeframe, count) -> List[Dict[str, Any]]:
        raise NotImplementedError("Implement: mt5.copy_rates_from_pos()")
