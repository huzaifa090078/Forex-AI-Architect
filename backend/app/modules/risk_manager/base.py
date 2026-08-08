"""
Risk Manager — base implementation scaffold.

RuleBasedRiskManager in manager.py is the production implementation.
This scaffold exists for interface stability and future extension points.
"""

import logging
from typing import Any, Dict, Optional

from app.modules.risk_manager.interfaces import IRiskManager, RiskCheckResult, PositionSize
from app.modules.risk_manager.types import RiskApproval, ProtectionState
from app.core.config import settings

logger = logging.getLogger(__name__)


class BaseRiskManager(IRiskManager):
    """
    Validates trades against configured risk limits.

    Concrete implementation: RuleBasedRiskManager (manager.py).

    Implementation checklist (all done in RuleBasedRiskManager):
      - Per-trade risk %         → approve_trade → lot size computation
      - Max open trades          → approve_trade → open position check
      - Daily loss kill-switch   → approve_trade → is_daily_loss_exceeded
      - Daily profit target      → approve_trade → is_daily_profit_reached
      - Max drawdown             → approve_trade → is_drawdown_exceeded
      - Consecutive losses       → approve_trade → consecutive_loss check
      - Spread protection        → approve_trade → spread check
      - Session protection       → approve_trade → session check
      - News protection          → approve_trade → INewsFilter delegation
      - Exposure control         → approve_trade → exposure check
      - Correlation protection   → DEFERRED (Section 8.15 — no engine exists)
    """

    async def approve_trade(self, pair, direction, entry, stop_loss, take_profit,
                            connector, *, news_filter=None, metadata=None,
                            _now=None) -> RiskApproval:
        raise NotImplementedError("Use RuleBasedRiskManager.approve_trade()")

    async def record_closed_trade(self, trade_id: str, pnl: float) -> None:
        raise NotImplementedError("Use RuleBasedRiskManager.record_closed_trade()")

    async def get_protection_state(self, connector) -> ProtectionState:
        raise NotImplementedError("Use RuleBasedRiskManager.get_protection_state()")

    async def check_trade(self, pair, direction, entry, stop_loss, take_profit, account_balance):
        raise NotImplementedError("Implement trade risk validation pipeline")

    async def compute_position_size(self, pair, entry, stop_loss, account_balance, risk_pct):
        raise NotImplementedError("Implement lot-size calculation (tick value × SL distance)")

    async def is_daily_loss_exceeded(self, account_balance: float) -> bool:
        raise NotImplementedError("Implement daily P&L check against MAX_DAILY_LOSS_PERCENT")

    async def open_trade_count(self) -> int:
        raise NotImplementedError("Query MT5 positions for count of open trades")
