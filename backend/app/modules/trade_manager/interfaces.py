"""
Trade Manager — abstract interface contracts.

The Trade Manager owns the full order lifecycle:
  signal approved → order placed → position monitored → position closed.
It delegates broker communication to the MT5 Integration module and
pre-flight checks to the Risk Manager.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.modules.risk_manager.types import RiskApproval


@dataclass
class OrderRequest:
    """
    A risk-approved trade request ready to be sent to the broker.

    ``risk_approval`` must be populated by a RuleBasedRiskManager.approve_trade()
    call before open_trade() is invoked.  Trade Manager validates the approval
    against all execution parameters before placing any order — bypassing the
    Risk Manager is structurally impossible through this interface.
    """
    pair: str
    direction: str                       # "buy" | "sell"
    entry_price: float
    stop_loss: float
    take_profit: float
    lot_size: float
    risk_approval: Optional["RiskApproval"] = None   # REQUIRED before execution
    signal_id: Optional[str] = None
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False


@dataclass
class OrderResult:
    """Result of sending an order to the broker."""
    success: bool
    broker_order_id: Optional[str] = None
    fill_price: Optional[float] = None
    fill_time: Optional[datetime] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ITradeManager(ABC):
    """Orchestrates the full trade lifecycle."""

    @abstractmethod
    async def open_trade(self, request: OrderRequest, dry_run: bool = False) -> OrderResult:
        """
        Risk-check → send order to broker → persist trade record.
        Returns OrderResult indicating success or failure.
        """
        ...

    @abstractmethod
    async def close_trade(self, trade_id: str, reason: str) -> OrderResult:
        """
        Close an open position at market price.
        `reason` is logged for audit purposes (e.g. "take_profit", "manual", "stop_loss").
        """
        ...

    @abstractmethod
    async def modify_trade(
        self,
        trade_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        """Move SL or TP on an open position. Returns True on broker ACK."""
        ...

    @abstractmethod
    async def sync_open_positions(self) -> List[Dict[str, Any]]:
        """
        Reconcile local database state with broker's open positions.
        Closes positions locally that are no longer open on the broker.
        """
        ...
