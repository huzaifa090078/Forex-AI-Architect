"""
Backtesting Engine — base implementation scaffold.
"""

import logging

from app.modules.backtesting.interfaces import IBacktestEngine, IDataLoader, BacktestConfig, BacktestResult

logger = logging.getLogger(__name__)


class CSVDataLoader(IDataLoader):
    """
    Loads OHLCV data from CSV files stored in BACKTEST_DATA_PATH.
    Expected file naming: <PAIR>_<TIMEFRAME>.csv (e.g. EURUSD_H1.csv)
    Expected columns: timestamp, open, high, low, close, volume
    """

    def load(self, pair, timeframe, from_date, to_date):
        raise NotImplementedError(
            "Implement CSV loading with pandas. "
            "Filter rows to [from_date, to_date] inclusive. "
            "Return list of OHLCV dicts."
        )


class BaseBacktestEngine(IBacktestEngine):
    """
    Bar-by-bar simulation loop.

    Implementation guide:
      1. Load data via IDataLoader
      2. For each bar: run SMC + Indicator + AI Engine pipeline
      3. Check for signal → risk check → simulate fill
      4. Track open positions, apply SL/TP on subsequent bars
      5. Accumulate equity curve and trade log
      6. Compute BacktestResult metrics at the end
    """

    def __init__(self, data_loader: IDataLoader) -> None:
        self._loader = data_loader

    async def run(self, config: BacktestConfig) -> BacktestResult:
        raise NotImplementedError(
            "Implement the bar-by-bar simulation loop. "
            "Use vectorized pandas operations where possible for performance."
        )
