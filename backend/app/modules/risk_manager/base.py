"""
Risk Manager — base implementation scaffold.
"""

import logging

from app.modules.risk_manager.interfaces import IRiskManager, RiskCheckResult, PositionSize
from app.core.config import settings

logger = logging.getLogger(__name__)


class BaseRiskManager(IRiskManager):
    """
    Validates trades against configured risk limits.
    Inject this into the Trade Manager to enforce all risk rules centrally.

    Implementation checklist:
      - Per-trade risk %         → compute_position_size
      - Max open trades          → open_trade_count check
      - Daily drawdown kill-switch → is_daily_loss_exceeded
      - Correlation / hedging limits (advanced — add later)
      - News filter gate (delegate to NewsFilter module)
    """

    async def check_trade(self, pair, direction, entry, stop_loss, take_profit, account_balance):
        raise NotImplementedError("Implement trade risk validation pipeline")

    async def compute_position_size(self, pair, entry, stop_loss, account_balance, risk_pct):
        raise NotImplementedError("Implement lot-size calculation (pip value × SL distance)")

    async def is_daily_loss_exceeded(self, account_balance: float) -> bool:
        raise NotImplementedError("Implement daily P&L check against max_daily_loss_pct")

    async def open_trade_count(self) -> int:
        raise NotImplementedError("Query database for count of open trades")
