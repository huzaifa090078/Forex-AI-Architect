"""
Risk Manager — abstract interface contracts.

The Risk Manager is a gatekeeper: every trade proposed by the AI Engine
must pass through it before being forwarded to the Trade Manager.
It enforces per-trade risk, daily loss limits, and portfolio exposure rules.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RiskParameters:
    """Current risk configuration snapshot."""
    risk_per_trade_pct: float          # % of balance risked per trade
    max_open_trades: int
    max_daily_loss_pct: float
    default_lot_size: float
    allowed_pairs: List[str] = field(default_factory=list)


@dataclass
class PositionSize:
    """Computed position size for a proposed trade."""
    lot_size: float
    risk_amount: float                  # in account currency
    pip_value: float
    stop_loss_pips: float
    risk_reward_ratio: float


@dataclass
class RiskCheckResult:
    """Result of the pre-trade risk check."""
    approved: bool
    reason: Optional[str] = None       # populated when approved=False
    position_size: Optional[PositionSize] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class IRiskManager(ABC):
    """
    Evaluate whether a proposed trade is permissible given current risk parameters
    and portfolio state. Compute the correct position size if approved.
    """

    @abstractmethod
    async def check_trade(
        self,
        pair: str,
        direction: str,
        entry: float,
        stop_loss: float,
        take_profit: float,
        account_balance: float,
    ) -> RiskCheckResult:
        """
        Run all risk checks for a proposed trade.
        Returns RiskCheckResult with approved=True and a PositionSize, or
        approved=False with a human-readable reason string.
        """
        ...

    @abstractmethod
    async def compute_position_size(
        self,
        pair: str,
        entry: float,
        stop_loss: float,
        account_balance: float,
        risk_pct: float,
    ) -> PositionSize:
        """
        Compute lot size based on account balance, risk %, and pip distance to SL.
        """
        ...

    @abstractmethod
    async def is_daily_loss_exceeded(self, account_balance: float) -> bool:
        """Return True if the daily drawdown kill-switch should be triggered."""
        ...

    @abstractmethod
    async def open_trade_count(self) -> int:
        """Return the number of currently open trades."""
        ...
