"""
Trade Manager — base implementation scaffold.
"""

import logging
from typing import Any, Dict, List, Optional

from app.modules.trade_manager.interfaces import ITradeManager, OrderRequest, OrderResult

logger = logging.getLogger(__name__)


class BaseTradeManager(ITradeManager):
    """
    Wires Risk Manager → MT5 Integration → Database persistence.

    Implementation order:
      1. open_trade: risk check → broker order → DB insert
      2. close_trade: broker close → DB update with P&L
      3. modify_trade: broker modify → DB update
      4. sync_open_positions: reconciliation loop (run on startup + periodic)
    """

    async def open_trade(self, request: OrderRequest) -> OrderResult:
        raise NotImplementedError("Implement: risk check → MT5 order → DB insert")

    async def close_trade(self, trade_id: str, reason: str) -> OrderResult:
        raise NotImplementedError("Implement: MT5 close order → compute PnL → DB update")

    async def modify_trade(self, trade_id, stop_loss=None, take_profit=None):
        raise NotImplementedError("Implement: MT5 modify order → DB update")

    async def sync_open_positions(self) -> List[Dict[str, Any]]:
        raise NotImplementedError("Implement: fetch MT5 positions → reconcile with DB")
