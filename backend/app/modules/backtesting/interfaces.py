"""
Backtesting — abstract interface contracts.

The backtester replays historical OHLCV data through the full signal pipeline
(SMC + Indicators + AI Engine + Risk Manager) in a controlled simulation
to produce performance metrics without risking real capital.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional


@dataclass
class BacktestConfig:
    """Parameters for a single backtest run."""
    strategy_id: str
    pair: str
    from_date: date
    to_date: date
    initial_balance: float
    lot_size: float
    risk_per_trade_pct: float = 1.0
    timeframe: str = "H1"
    slippage_pips: float = 1.0
    spread_pips: float = 1.5
    commission_per_lot: float = 0.0


@dataclass
class BacktestTrade:
    """A single simulated trade within a backtest run."""
    open_time: Any
    close_time: Any
    pair: str
    direction: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    lot_size: float
    pnl: float
    exit_reason: str                   # "take_profit" | "stop_loss" | "manual"


@dataclass
class BacktestResult:
    """Aggregate metrics from a completed backtest run."""
    run_id: str
    config: BacktestConfig
    initial_balance: float
    final_balance: float
    net_pnl: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    avg_win: float
    avg_loss: float
    avg_rr: float
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class IDataLoader(ABC):
    """Load and provide historical OHLCV data for backtesting."""

    @abstractmethod
    def load(self, pair: str, timeframe: str, from_date: date, to_date: date) -> List[Dict[str, Any]]:
        """Return a list of OHLCV dicts covering the specified date range."""
        ...


class IBacktestEngine(ABC):
    """Simulate a strategy over historical data and return performance metrics."""

    @abstractmethod
    async def run(self, config: BacktestConfig) -> BacktestResult:
        """
        Execute a full backtest:
          1. Load historical OHLCV
          2. Iterate bar-by-bar through the signal pipeline
          3. Simulate order fills with slippage and spread
          4. Apply risk management rules
          5. Compute and return BacktestResult
        """
        ...
