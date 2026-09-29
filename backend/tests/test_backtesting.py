"""
Unit tests for the Backtesting Engine (Section 15).
"""

from datetime import date
import pytest

from app.modules.backtesting.engine import ConcreteBacktestEngine, HistoricalDataLoader
from app.modules.backtesting.interfaces import BacktestConfig


@pytest.mark.asyncio
async def test_historical_data_loader():
    loader = HistoricalDataLoader()
    bars = loader.load(
        pair="EURUSD",
        timeframe="H1",
        from_date=date(2024, 1, 1),
        to_date=date(2024, 1, 10),
    )
    assert len(bars) > 0
    first_bar = bars[0]
    assert "time" in first_bar
    assert "open" in first_bar
    assert "high" in first_bar
    assert "low" in first_bar
    assert "close" in first_bar
    assert first_bar["high"] >= first_bar["low"]


@pytest.mark.asyncio
async def test_backtest_engine_simulation():
    engine = ConcreteBacktestEngine()
    config = BacktestConfig(
        strategy_id="SMC_V1",
        pair="EURUSD",
        from_date=date(2024, 1, 1),
        to_date=date(2024, 1, 31),
        initial_balance=10000.0,
        lot_size=0.1,
        risk_per_trade_pct=1.0,
        timeframe="H1",
    )

    result = await engine.run(config)
    assert result.run_id is not None
    assert result.initial_balance == 10000.0
    assert result.final_balance > 0
    assert result.total_trades >= 0
    assert len(result.equity_curve) > 0
    assert result.max_drawdown >= 0.0
    assert 0.0 <= result.win_rate <= 1.0
