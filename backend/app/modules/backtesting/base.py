"""
Backtesting Engine — base implementation and exports.
"""

from app.modules.backtesting.engine import (
    ConcreteBacktestEngine,
    HistoricalDataLoader,
)
from app.modules.backtesting.interfaces import (
    BacktestConfig,
    BacktestResult,
    BacktestTrade,
    IBacktestEngine,
    IDataLoader,
)

# Aliases for backward compatibility
CSVDataLoader = HistoricalDataLoader
BaseBacktestEngine = ConcreteBacktestEngine

__all__ = [
    "IBacktestEngine",
    "IDataLoader",
    "BacktestConfig",
    "BacktestResult",
    "BacktestTrade",
    "CSVDataLoader",
    "HistoricalDataLoader",
    "BaseBacktestEngine",
    "ConcreteBacktestEngine",
]
