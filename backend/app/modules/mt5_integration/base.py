"""
MT5 Integration — RealMT5Connector.

RealMT5Connector: production implementation using the MetaTrader5 package.
Only functional on Windows (or Linux with Wine + MT5 terminal installed).
This is the only permitted connector — no simulation or demo connector exists.
"""

import logging
from typing import Any, Dict, List, Optional

from app.modules.mt5_integration.interfaces import (
    IMT5Connector,
    AccountInfo,
    BrokerPosition,
    BrokerOrder,
)

logger = logging.getLogger(__name__)


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
