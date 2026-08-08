"""
Risk Manager — abstract interface contracts.

The Risk Manager is the account-protection gatekeeper between the AI Decision
Engine and the Trade Manager.  Every proposed trade must pass approve_trade()
before the Trade Manager is permitted to send an order to the broker.

Section 8 extension: approve_trade() is the single authoritative entry point.
The legacy check_trade() / compute_position_size() stubs are retained for
backward compatibility but are superseded by approve_trade().
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from app.modules.risk_manager.types import RiskApproval, ProtectionState

if TYPE_CHECKING:
    from app.modules.mt5_integration.interfaces import IMT5Connector
    from app.modules.news_filter.interfaces import INewsFilter


# ---------------------------------------------------------------------------
# Legacy types — kept for backward compatibility
# ---------------------------------------------------------------------------

@dataclass
class RiskParameters:
    """Current risk configuration snapshot."""
    risk_per_trade_pct: float
    max_open_trades:    int
    max_daily_loss_pct: float
    default_lot_size:   float
    allowed_pairs:      List[str] = field(default_factory=list)


@dataclass
class PositionSize:
    """Computed position size for a proposed trade."""
    lot_size:          float
    risk_amount:       float        # in account currency
    pip_value:         float
    stop_loss_pips:    float
    risk_reward_ratio: float


@dataclass
class RiskCheckResult:
    """Result of the pre-trade risk check (legacy)."""
    approved:       bool
    reason:         Optional[str]      = None
    position_size:  Optional[PositionSize] = None
    metadata:       Dict[str, Any]     = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class IRiskManager(ABC):
    """
    Single-source-of-truth for trade risk approval.

    approve_trade() is the authoritative Section 8 entry point.
    All other abstract methods (check_trade, compute_position_size,
    is_daily_loss_exceeded, open_trade_count) are retained for interface
    stability and are called internally by approve_trade().
    """

    # ── Section 8 — primary approval path ───────────────────────────────────

    @abstractmethod
    async def approve_trade(
        self,
        pair:        str,
        direction:   str,        # "buy" | "sell"
        entry:       float,
        stop_loss:   float,
        take_profit: float,
        connector:   "IMT5Connector",
        *,
        news_filter: Optional["INewsFilter"] = None,
        metadata:    Optional[Dict[str, Any]] = None,
    ) -> RiskApproval:
        """
        Run every mandatory Section 8 risk check for the proposed trade.

        Checks (in order):
          account availability, symbol spec, tick/spread, open positions,
          SL validity, TP validity, R:R, lot sizing, risk cap,
          max open trades, spread, daily loss, daily profit (if enabled),
          drawdown, consecutive losses, session, news, exposure.

        Fails CLOSED on any unavailable required data — returns an approved=False
        RiskApproval with a populated rejection_reasons tuple rather than raising.

        Returns RiskApproval with approved=True and a valid lot_size when all
        checks pass, or approved=False with populated rejection_reasons otherwise.
        """
        ...

    @abstractmethod
    async def record_closed_trade(
        self,
        trade_id: str,
        pnl:      float,
    ) -> None:
        """
        Notify the Risk Manager that a trade has been closed with the given P&L.

        Updates daily P&L and consecutive-loss tracking.  Idempotent — the same
        trade_id recorded twice has no additional effect.
        """
        ...

    @abstractmethod
    async def get_protection_state(
        self,
        connector: "IMT5Connector",
    ) -> ProtectionState:
        """
        Return the current protection/limit state for the dashboard.

        Called by the API endpoint; never blocks a trade by itself.
        Fails safely — returns a default ProtectionState on any error
        rather than raising.
        """
        ...

    # ── Legacy stubs — retained for interface stability ─────────────────────

    @abstractmethod
    async def check_trade(
        self,
        pair:            str,
        direction:       str,
        entry:           float,
        stop_loss:       float,
        take_profit:     float,
        account_balance: float,
    ) -> RiskCheckResult:
        """Legacy trade check (superseded by approve_trade in Section 8)."""
        ...

    @abstractmethod
    async def compute_position_size(
        self,
        pair:            str,
        entry:           float,
        stop_loss:       float,
        account_balance: float,
        risk_pct:        float,
    ) -> PositionSize:
        """Legacy position-size computation (superseded by approve_trade)."""
        ...

    @abstractmethod
    async def is_daily_loss_exceeded(self, account_balance: float) -> bool:
        """Return True when the daily drawdown kill-switch should be triggered."""
        ...

    @abstractmethod
    async def open_trade_count(self) -> int:
        """Return the number of currently open trades (legacy)."""
        ...
