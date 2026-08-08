"""
Risk Manager — shared data types.
Pure dataclasses and frozen immutable objects; no business logic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, FrozenSet, Optional, Tuple


# ---------------------------------------------------------------------------
# Symbol specification — sourced from MT5 symbol_info()
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SymbolSpec:
    """
    MT5 symbol specification required for accurate lot sizing.

    All values come directly from mt5.symbol_info(); no hardcoded defaults
    are permitted — the Risk Manager rejects the trade if this is unavailable.
    """
    symbol:        str
    tick_size:     float   # minimum price movement (e.g. 0.00001 for EURUSD 5-digit)
    tick_value:    float   # monetary value of one tick for 1 lot (in account currency)
    contract_size: float   # units per lot (e.g. 100_000 for standard forex)
    volume_min:    float   # minimum allowed lot size
    volume_max:    float   # maximum allowed lot size
    volume_step:   float   # lot size increment step
    digits:        int     # decimal places in price quotes
    point:         float = 0.0  # point size (= tick_size for most forex pairs)


# ---------------------------------------------------------------------------
# Approval token — passed to Trade Manager before execution
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RiskApproval:
    """
    Immutable approval token produced by RuleBasedRiskManager.

    Trade Manager must call matches_order() with the exact execution
    parameters before sending any order to the broker.  Any mismatch
    → execution is blocked.  Prevents:
      - bypassing Risk Manager
      - stale approval reuse
      - approval for different symbol / side / entry / SL / TP
      - changed lot size after approval
    """
    approved:          bool
    pair:              str
    direction:         str            # "buy" | "sell"
    entry:             float
    stop_loss:         float
    take_profit:       float
    lot_size:          float          # 0.0 when rejected
    risk_amount:       float          # monetary risk in account currency
    risk_pct:          float          # configured risk %
    rr_ratio:          float          # actual R:R (0.0 when rejected)
    rejection_reasons: Tuple[str, ...]   # non-empty when approved=False
    protection_flags:  Tuple[str, ...]   # active protection labels
    approved_at:       datetime

    def matches_order(
        self,
        pair:       str,
        direction:  str,
        entry:      float,
        stop_loss:  float,
        take_profit: float,
        lot_size:   float,
        tolerance:  float = 1e-8,
    ) -> bool:
        """
        Return True iff this approval is valid and all execution parameters
        match exactly within floating-point tolerance.

        A False return means the Trade Manager must block execution.
        """
        if not self.approved:
            return False
        if self.pair.upper() != pair.upper():
            return False
        if self.direction.lower() != direction.lower():
            return False
        if abs(self.lot_size - lot_size) > tolerance:
            return False
        if abs(self.entry - entry) > tolerance:
            return False
        if abs(self.stop_loss - stop_loss) > tolerance:
            return False
        if abs(self.take_profit - take_profit) > tolerance:
            return False
        return True


# ---------------------------------------------------------------------------
# Daily statistics — in-memory, date-keyed, reset at UTC midnight
# ---------------------------------------------------------------------------

@dataclass
class DailyStats:
    """
    Per-trading-day P&L and protection state.

    Immutable update pattern: record_closed_trade() returns a new DailyStats
    so callers can replace the reference atomically.  counted_trade_ids
    prevents the same closed trade from being counted more than once even if
    the sync loop fires multiple times.

    Design note: this is intentionally persistence-compatible — all state
    fits in a single flat record that can be stored in the database or Redis
    in a future section.
    """
    trading_date:      date
    starting_balance:  float                     # equity at day-open
    realized_pnl:      float       = 0.0         # sum of all closed trade P&L
    realized_profit:   float       = 0.0         # sum of winning trade P&L only
    consecutive_losses: int        = 0           # current run of losing trades
    counted_trade_ids: FrozenSet[str] = field(default_factory=frozenset)

    def record_closed_trade(self, trade_id: str, pnl: float) -> "DailyStats":
        """
        Return a new DailyStats that includes the given closed trade.

        Idempotent — if trade_id already recorded, returns self unchanged.
        A positive pnl resets the consecutive-loss counter to 0.
        """
        if trade_id in self.counted_trade_ids:
            return self  # already counted — no double-counting

        new_ids     = self.counted_trade_ids | {trade_id}
        new_pnl     = self.realized_pnl + pnl
        new_profit  = self.realized_profit + (pnl if pnl > 0 else 0.0)
        new_consec  = 0 if pnl >= 0 else self.consecutive_losses + 1

        return DailyStats(
            trading_date      = self.trading_date,
            starting_balance  = self.starting_balance,
            realized_pnl      = new_pnl,
            realized_profit   = new_profit,
            consecutive_losses= new_consec,
            counted_trade_ids = frozenset(new_ids),
        )


# ---------------------------------------------------------------------------
# Protection state snapshot — for dashboard / API
# ---------------------------------------------------------------------------

@dataclass
class ProtectionState:
    """
    Current active protection states exposed through the dashboard API.

    Any flag being True means new trades are currently blocked by that rule.
    """
    daily_loss_active:        bool  = False
    daily_profit_active:      bool  = False
    drawdown_active:          bool  = False
    consecutive_loss_active:  bool  = False
    max_open_trades_active:   bool  = False
    session_blocked:          bool  = False
    news_blocked:             bool  = False
    spread_blocked:           bool  = False
    exposure_blocked:         bool  = False

    # Numeric context for the dashboard
    daily_pnl:               float = 0.0
    daily_pnl_pct:           float = 0.0
    drawdown_pct:            float = 0.0
    consecutive_losses:      int   = 0
    open_trades:             int   = 0

    def any_active(self) -> bool:
        return any([
            self.daily_loss_active,
            self.daily_profit_active,
            self.drawdown_active,
            self.consecutive_loss_active,
            self.max_open_trades_active,
            self.session_blocked,
            self.news_blocked,
            self.spread_blocked,
            self.exposure_blocked,
        ])
