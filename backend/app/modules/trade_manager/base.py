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

    Bypass protection (Section 8.17):
      open_trade() validates risk_approval before delegating to any concrete
      implementation.  A missing, rejected, or mismatched approval raises
      ValueError — the broker order path is never reached without a valid token.
    """

    @staticmethod
    def _validate_risk_approval(request: OrderRequest) -> None:
        """
        Enforce Risk Manager gate before any trade execution path.

        Raises ValueError when:
          - risk_approval is None (Risk Manager was not called)
          - risk_approval.approved is False (trade was rejected)
          - approval parameters don't match the request (stale / tampered)
        """
        approval = request.risk_approval
        if approval is None:
            raise ValueError(
                "OrderRequest.risk_approval is None — "
                "Risk Manager must approve every trade before execution. "
                "Call RuleBasedRiskManager.approve_trade() first."
            )
        if not approval.approved:
            reasons = "; ".join(approval.rejection_reasons)
            raise ValueError(
                f"Risk Manager rejected this trade: {reasons}"
            )
        if not approval.matches_order(
            pair        = request.pair,
            direction   = request.direction,
            entry       = request.entry_price,
            stop_loss   = request.stop_loss,
            take_profit = request.take_profit,
            lot_size    = request.lot_size,
        ):
            raise ValueError(
                "OrderRequest parameters do not match the Risk Manager approval — "
                "possible stale approval, tampered lot size, or wrong symbol/direction. "
                "Re-run approve_trade() with the current parameters."
            )

    async def open_trade(self, request: OrderRequest, dry_run: bool = False) -> OrderResult:
        # Enforce Risk Manager gate — raises ValueError on any violation.
        self._validate_risk_approval(request)
        raise NotImplementedError("Implement: risk check → MT5 order → DB insert")

    async def close_trade(self, trade_id: str, reason: str) -> OrderResult:
        raise NotImplementedError("Implement: MT5 close order → compute PnL → DB update")

    async def modify_trade(self, trade_id, stop_loss=None, take_profit=None):
        raise NotImplementedError("Implement: MT5 modify order → DB update")

    async def sync_open_positions(self) -> List[Dict[str, Any]]:
        raise NotImplementedError("Implement: fetch MT5 positions → reconcile with DB")
