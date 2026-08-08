"""
Section 8 — Risk Manager unit tests.

All tests run without a real MT5 connection.  Dependency injection via mock
IMT5Connector and INewsFilter implementations that return deterministic fixture
data.  Tests cover all 8.1–8.20 requirements plus Trade Manager bypass guard.

Run:
    cd backend && python -m pytest tests/test_risk_manager.py -v
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from app.core.config import settings
from app.modules.mt5_integration.interfaces import AccountInfo, BrokerPosition, IMT5Connector, BrokerOrder
from app.modules.news_filter.interfaces import INewsFilter, NewsEvent
from app.modules.risk_manager.manager import RuleBasedRiskManager, _normalize_volume
from app.modules.risk_manager.types import DailyStats, RiskApproval, SymbolSpec
from app.modules.trade_manager.interfaces import OrderRequest
from app.modules.trade_manager.base import BaseTradeManager


# ===========================================================================
# Fixtures / Mocks
# ===========================================================================

# Default EURUSD 5-digit spec
EURUSD_SPEC: Dict[str, Any] = {
    "tick_size":     0.00001,
    "tick_value":    1.0,        # 1 USD per tick per lot (for USD account)
    "contract_size": 100_000.0,
    "volume_min":    0.01,
    "volume_max":    100.0,
    "volume_step":   0.01,
    "digits":        5,
    "point":         0.00001,
}


class MockMT5Connector(IMT5Connector):
    """Configurable mock connector that returns deterministic fixture data."""

    def __init__(
        self,
        balance:            float = 10_000.0,
        equity:             float = 10_000.0,
        positions:          Optional[List[BrokerPosition]] = None,
        symbol_spec:        Optional[Dict[str, Any]] = None,
        bid:                float = 1.10000,
        ask:                float = 1.10010,
        account_raises:     bool = False,
        symbol_raises:      bool = False,
        tick_raises:        bool = False,
        positions_raises:   bool = False,
    ) -> None:
        self._balance          = balance
        self._equity           = equity
        self._positions        = positions if positions is not None else []
        self._symbol_spec      = symbol_spec if symbol_spec is not None else dict(EURUSD_SPEC)
        self._bid              = bid
        self._ask              = ask
        self._account_raises   = account_raises
        self._symbol_raises    = symbol_raises
        self._tick_raises      = tick_raises
        self._positions_raises = positions_raises

    async def get_account_info(self) -> AccountInfo:
        if self._account_raises:
            raise RuntimeError("MT5 not available in test — account_raises=True")
        return AccountInfo(
            login=12345678, server="Exness-MT5Trial",
            balance=self._balance, equity=self._equity,
            margin=100.0, free_margin=self._equity - 100.0,
            leverage=500, currency="USD", connected=True,
        )

    async def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        if self._symbol_raises:
            raise RuntimeError(f"Symbol spec unavailable for {symbol}")
        return dict(self._symbol_spec)

    async def get_tick(self, symbol: str) -> Dict[str, Any]:
        if self._tick_raises:
            raise RuntimeError(f"Tick unavailable for {symbol}")
        spread = self._ask - self._bid
        return {
            "bid":       self._bid,
            "ask":       self._ask,
            "spread":    spread,
            "last":      self._bid,
            "volume":    100,
            "tick_time": datetime.now(timezone.utc),
        }

    async def get_positions(self) -> List[BrokerPosition]:
        if self._positions_raises:
            raise RuntimeError("Positions unavailable")
        return list(self._positions)

    # ── not used in risk manager tests ──────────────────────────────────────
    async def connect(self) -> bool:                              return True
    async def disconnect(self) -> None:                           return
    async def get_orders(self) -> List[BrokerOrder]:              return []
    async def send_market_order(self, *a, **kw) -> Dict:          raise NotImplementedError
    async def close_position(self, ticket: int) -> Dict:          raise NotImplementedError
    async def modify_position(self, *a, **kw) -> bool:           raise NotImplementedError
    async def get_ohlcv(self, *a, **kw) -> List[Dict]:            raise NotImplementedError


class MockNewsFilter(INewsFilter):
    """Mock news filter with configurable allow/deny and raise behaviour."""

    def __init__(self, allowed: bool = True, raises: bool = False) -> None:
        self._allowed = allowed
        self._raises  = raises

    async def is_trading_allowed(self, pair: str) -> bool:
        if self._raises:
            raise RuntimeError("News provider unreachable")
        return self._allowed

    async def get_upcoming_high_impact(self) -> List[NewsEvent]:
        return []

    # ── New Section 10 abstract methods (minimal stubs for test isolation) ──

    def evaluate_pair(self, pair, now):
        from app.modules.news_filter.interfaces import NewsBlockReason, PairNewsStatus
        return PairNewsStatus(
            pair=pair, affected=False, blocked=not self._allowed,
            reason=NewsBlockReason.NO_RELEVANT_NEWS, provider_ok=True,
        )

    def get_affected_pairs(self, event, all_pairs=None):
        return []

    @property
    def provider_available(self) -> bool:
        return not self._raises

    @property
    def last_refresh(self):
        return None


def make_manager(news_filter=None) -> RuleBasedRiskManager:
    return RuleBasedRiskManager(news_filter=news_filter)


def make_connector(**kwargs) -> MockMT5Connector:
    return MockMT5Connector(**kwargs)


async def approve(
    manager:     Optional[RuleBasedRiskManager] = None,
    connector:   Optional[MockMT5Connector] = None,
    pair:        str = "EURUSD",
    direction:   str = "buy",
    entry:       float = 1.10000,
    stop_loss:   float = 1.0990,     # 10 pip SL
    take_profit: float = 1.1020,     # 20 pip TP → 1:2 RR
    news_filter = None,
    _now:        Optional[datetime] = None,
    **connector_kwargs,
) -> RiskApproval:
    """Convenience helper for calling approve_trade with sensible defaults."""
    mgr  = manager or make_manager(news_filter=news_filter)
    conn = connector or make_connector(**connector_kwargs)
    return await mgr.approve_trade(
        pair=pair, direction=direction,
        entry=entry, stop_loss=stop_loss, take_profit=take_profit,
        connector=conn,
        news_filter=news_filter,
        _now=_now,
    )


# UTC datetime helpers for session tests
def _utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2024, 6, 3, hour, minute, 0, tzinfo=timezone.utc)


# ===========================================================================
# 1. Risk % validation
# ===========================================================================

def test_01_risk_pct_validation_zero(monkeypatch):
    """Zero equity means zero monetary_risk → lot_size=0 → rejected."""
    result = asyncio.run(
        approve(equity=0.0, balance=0.0)
    )
    assert not result.approved
    assert result.rejection_reasons


def test_02_risk_pct_produces_positive_monetary_risk():
    """Standard 1% risk on $10,000 equity → monetary_risk = $100."""
    mgr = make_manager()
    lot, risk = mgr._compute_lot_and_risk(
        equity    = 10_000.0,
        risk_pct  = 1.0,
        entry     = 1.10000,
        stop_loss = 1.0990,
        spec      = SymbolSpec(symbol="EURUSD", **EURUSD_SPEC),
    )
    assert lot > 0
    assert risk > 0
    assert risk <= 100.0 * 1.02   # no more than 1% of $10,000 (+2% rounding tolerance)


# ===========================================================================
# 2–4. Lot size calculation and normalisation
# ===========================================================================

def test_03_lot_size_normal_calculation():
    """
    $10,000 equity, 1% risk, 10-pip SL on EURUSD:
    monetary_risk = $100
    sl_ticks ≈ 100
    lot_raw  ≈ 1.00

    Due to floating-point representation of 0.001 / 0.00001 the raw lot may
    be marginally below 1.00 (e.g. 0.9999999...), which floors to 0.99 at
    step=0.01.  Both 0.99 and 1.00 are acceptable — what matters is that
    lot > 0 and actual_risk ≤ budget.
    """
    mgr  = make_manager()
    spec = SymbolSpec(symbol="EURUSD", **EURUSD_SPEC)
    lot, risk = mgr._compute_lot_and_risk(
        equity=10_000.0, risk_pct=1.0,
        entry=1.10000, stop_loss=1.0990,
        spec=spec,
    )
    assert lot > 0
    assert lot <= 1.01            # never more than 1.01 lots (no risk overrun)
    assert lot >= 0.98            # never less than 0.98 lots (within 2% of target)
    assert risk <= 100.0 * 1.02  # actual risk ≤ budget + 2% rounding tolerance


def test_04_lot_size_min_normalization():
    """Very small risk → raw lot below volume_min → clamped to volume_min."""
    mgr  = make_manager()
    spec = SymbolSpec(
        symbol="EURUSD", tick_size=0.00001, tick_value=1.0,
        contract_size=100_000.0, volume_min=0.01, volume_max=100.0,
        volume_step=0.01, digits=5,
    )
    # $100 equity, 1% = $1 risk, 100-pip SL → lot_raw ≈ 0.001 < volume_min=0.01
    lot, risk = mgr._compute_lot_and_risk(
        equity=100.0, risk_pct=1.0,
        entry=1.10000, stop_loss=1.0900,
        spec=spec,
    )
    # volume_min kicks in
    assert lot == pytest.approx(0.01, abs=1e-9)


def test_05_lot_size_max_normalization():
    """Enormous equity → raw lot above volume_max → clamped to volume_max."""
    mgr  = make_manager()
    spec = SymbolSpec(
        symbol="EURUSD", tick_size=0.00001, tick_value=1.0,
        contract_size=100_000.0, volume_min=0.01, volume_max=10.0,
        volume_step=0.01, digits=5,
    )
    # $10M equity, 1%, 1-pip SL → lot_raw = 100_000 >> 10.0
    lot, _ = mgr._compute_lot_and_risk(
        equity=10_000_000.0, risk_pct=1.0,
        entry=1.10000, stop_loss=1.09990,
        spec=spec,
    )
    assert lot == pytest.approx(10.0, abs=1e-9)


def test_06_lot_size_step_normalization():
    """Non-step-aligned raw lot is floored to the nearest step."""
    # volume_step=0.05; raw lot = 0.07 → floor → 0.05
    lots = _normalize_volume(0.07, volume_min=0.01, volume_max=100.0, volume_step=0.05)
    assert lots == pytest.approx(0.05, abs=1e-9)


# ===========================================================================
# 5. Risk cap after normalization
# ===========================================================================

def test_07_risk_cap_enforcement(monkeypatch):
    """
    If volume_min forces actual_risk above budget * 1.02, trade is rejected.
    """
    # Set very low budget but high volume_min
    monkeypatch.setattr(settings, "RISK_PER_TRADE_PERCENT", 0.001)  # 0.001% of $10k = $0.10
    # volume_min=0.01, SL=10 pips → actual_risk=0.01*100*1.0=$1.00 >> $0.10
    result = asyncio.run(
        approve(
            equity=10_000.0, balance=10_000.0,
            stop_loss=1.0990,
        )
    )
    assert not result.approved
    monkeypatch.setattr(settings, "RISK_PER_TRADE_PERCENT", 1.0)  # restore


# ===========================================================================
# 6. Invalid symbol specifications
# ===========================================================================

def test_08_invalid_symbol_spec_connector_raises():
    """When get_symbol_info() raises, approve_trade() must fail closed."""
    result = asyncio.run(
        approve(symbol_raises=True)
    )
    assert not result.approved
    assert any("symbol" in r.lower() or "spec" in r.lower() for r in result.rejection_reasons)


def test_09_zero_tick_size_rejected():
    """Zero tick_size in spec → lot calculation invalid → rejected."""
    bad_spec = dict(EURUSD_SPEC)
    bad_spec["tick_size"] = 0.0
    result = asyncio.run(
        approve(symbol_spec=bad_spec)
    )
    assert not result.approved


# ===========================================================================
# 7. SL validation
# ===========================================================================

def test_10_invalid_sl_buy_wrong_side():
    """BUY: SL above entry must be rejected."""
    result = asyncio.run(
        approve(direction="buy", entry=1.10000, stop_loss=1.10100, take_profit=1.1020)
    )
    assert not result.approved
    assert any("stop loss" in r.lower() for r in result.rejection_reasons)


def test_11_invalid_sl_sell_wrong_side():
    """SELL: SL below entry must be rejected."""
    result = asyncio.run(
        approve(direction="sell", entry=1.10000, stop_loss=1.0990, take_profit=1.0970)
    )
    assert not result.approved
    assert any("stop loss" in r.lower() for r in result.rejection_reasons)


# ===========================================================================
# 8. TP validation
# ===========================================================================

def test_12_invalid_tp_buy_wrong_side():
    """BUY: TP below entry must be rejected."""
    result = asyncio.run(
        approve(direction="buy", entry=1.10000, stop_loss=1.0990, take_profit=1.0980)
    )
    assert not result.approved
    assert any("take profit" in r.lower() for r in result.rejection_reasons)


def test_13_invalid_tp_sell_wrong_side():
    """SELL: TP above entry must be rejected."""
    result = asyncio.run(
        approve(direction="sell", entry=1.10000, stop_loss=1.10100, take_profit=1.10200)
    )
    assert not result.approved
    assert any("take profit" in r.lower() or "stop loss" in r.lower() for r in result.rejection_reasons)


# ===========================================================================
# 9–10. R:R
# ===========================================================================

def test_14_rr_rejection(monkeypatch):
    """R:R below minimum (default 2.0) must be rejected."""
    monkeypatch.setattr(settings, "RISK_MIN_RR", 2.0)
    # SL=10 pips, TP=10 pips → RR = 1.0 < 2.0
    result = asyncio.run(
        approve(entry=1.10000, stop_loss=1.0990, take_profit=1.1010)
    )
    assert not result.approved
    assert any("r:r" in r.lower() or "rr" in r.lower() or "reward" in r.lower()
               for r in result.rejection_reasons)


def test_15_rr_approval(monkeypatch):
    """R:R at or above minimum must not add an RR rejection reason."""
    monkeypatch.setattr(settings, "RISK_MIN_RR", 2.0)
    monkeypatch.setattr(settings, "NEWS_FILTER_ENABLED", False)
    monkeypatch.setattr(settings, "RISK_ALLOWED_SESSIONS", [])
    # SL=10 pips, TP=20 pips → RR = 2.0 ≥ 2.0
    result = asyncio.run(
        approve(entry=1.10000, stop_loss=1.0990, take_profit=1.1020)
    )
    rr_reasons = [r for r in result.rejection_reasons if "r:r" in r.lower() or "rr" in r.lower()]
    assert len(rr_reasons) == 0, f"Unexpected RR rejection: {result.rejection_reasons}"
    assert result.rr_ratio == pytest.approx(2.0, abs=0.01)


# ===========================================================================
# 11. Maximum open trades
# ===========================================================================

def test_16_max_open_trades(monkeypatch):
    """When MAX_OPEN_TRADES positions already open, new trade must be rejected."""
    monkeypatch.setattr(settings, "MAX_OPEN_TRADES", 2)
    positions = [
        BrokerPosition(ticket=1, symbol="EURUSD", type="buy", volume=0.1,
                       open_price=1.0990, current_price=1.1000, sl=1.0980,
                       tp=1.1020, profit=10.0, open_time=datetime.now(timezone.utc)),
        BrokerPosition(ticket=2, symbol="GBPUSD", type="sell", volume=0.1,
                       open_price=1.2700, current_price=1.2690, sl=1.2710,
                       tp=1.2670, profit=5.0, open_time=datetime.now(timezone.utc)),
    ]
    result = asyncio.run(
        approve(positions=positions)
    )
    assert not result.approved
    assert any("open trades" in r.lower() for r in result.rejection_reasons)


# ===========================================================================
# 12. Daily loss protection
# ===========================================================================

def test_17_daily_loss_protection(monkeypatch):
    """Daily loss limit reached → new trade rejected."""
    monkeypatch.setattr(settings, "MAX_DAILY_LOSS_PERCENT", 5.0)
    # $10,000 starting balance; equity dropped to $9,400 = 6% loss
    mgr = make_manager()
    today = datetime.now(timezone.utc).date()
    mgr._daily_stats = DailyStats(
        trading_date     = today,
        starting_balance = 10_000.0,
        realized_pnl     = -600.0,   # 6% loss already realized
    )
    result = asyncio.run(
        approve(manager=mgr, equity=9_400.0, balance=9_400.0)
    )
    assert not result.approved
    assert any("daily loss" in r.lower() for r in result.rejection_reasons)


# ===========================================================================
# 13. Daily profit protection
# ===========================================================================

def test_18_daily_profit_protection(monkeypatch):
    """Daily profit target reached → new trade rejected."""
    monkeypatch.setattr(settings, "RISK_MAX_DAILY_PROFIT_PERCENT", 3.0)
    monkeypatch.setattr(settings, "NEWS_FILTER_ENABLED", False)
    # Started at $10,000; equity grew to $10,350 = 3.5% profit
    mgr = make_manager()
    today = datetime.now(timezone.utc).date()
    mgr._daily_stats = DailyStats(
        trading_date     = today,
        starting_balance = 10_000.0,
        realized_pnl     = 350.0,
    )
    result = asyncio.run(
        approve(manager=mgr, equity=10_350.0, balance=10_350.0)
    )
    assert not result.approved
    assert any("profit" in r.lower() for r in result.rejection_reasons)
    monkeypatch.setattr(settings, "RISK_MAX_DAILY_PROFIT_PERCENT", 0.0)


# ===========================================================================
# 14. Drawdown protection
# ===========================================================================

def test_19_drawdown_protection(monkeypatch):
    """Max drawdown exceeded → new trade rejected."""
    monkeypatch.setattr(settings, "RISK_MAX_DRAWDOWN_PERCENT", 10.0)
    # Started at $10,000; equity is $8,900 = 11% drawdown
    mgr = make_manager()
    today = datetime.now(timezone.utc).date()
    mgr._daily_stats = DailyStats(
        trading_date     = today,
        starting_balance = 10_000.0,
    )
    result = asyncio.run(
        approve(manager=mgr, equity=8_900.0, balance=8_900.0)
    )
    assert not result.approved
    assert any("drawdown" in r.lower() for r in result.rejection_reasons)


# ===========================================================================
# 15. Consecutive loss protection
# ===========================================================================

def test_20_consecutive_loss_protection(monkeypatch):
    """Consecutive-loss limit reached → new trade rejected."""
    monkeypatch.setattr(settings, "RISK_MAX_CONSECUTIVE_LOSSES", 3)
    mgr   = make_manager()
    today = datetime.now(timezone.utc).date()
    mgr._daily_stats = DailyStats(
        trading_date       = today,
        starting_balance   = 10_000.0,
        consecutive_losses = 3,
    )
    result = asyncio.run(
        approve(manager=mgr)
    )
    assert not result.approved
    assert any("consecutive" in r.lower() for r in result.rejection_reasons)


# ===========================================================================
# 16. Spread protection
# ===========================================================================

def test_21_spread_protection(monkeypatch):
    """Spread > RISK_MAX_SPREAD_PIPS → rejected."""
    monkeypatch.setattr(settings, "RISK_MAX_SPREAD_PIPS", 2.0)
    # bid=1.10000, ask=1.10040 → spread=0.00040 → 4 pips > 2.0
    result = asyncio.run(
        approve(bid=1.10000, ask=1.10040)
    )
    assert not result.approved
    assert any("spread" in r.lower() for r in result.rejection_reasons)
    monkeypatch.setattr(settings, "RISK_MAX_SPREAD_PIPS", 3.0)


# ===========================================================================
# 17. Session protection
# ===========================================================================

def test_22_session_protection(monkeypatch):
    """Session not in allowed list → rejected."""
    monkeypatch.setattr(settings, "RISK_ALLOWED_SESSIONS", ["London", "London/NY Overlap"])
    monkeypatch.setattr(settings, "NEWS_FILTER_ENABLED", False)
    # 22:00 UTC = Off Hours (not London or Overlap)
    result = asyncio.run(
        approve(_now=_utc(22, 0))
    )
    assert not result.approved
    assert any("session" in r.lower() for r in result.rejection_reasons)
    monkeypatch.setattr(settings, "RISK_ALLOWED_SESSIONS", [])


def test_22b_session_allowed(monkeypatch):
    """Session in allowed list → session check passes."""
    monkeypatch.setattr(settings, "RISK_ALLOWED_SESSIONS", ["London"])
    monkeypatch.setattr(settings, "NEWS_FILTER_ENABLED", False)
    # 10:00 UTC = London session
    result = asyncio.run(
        approve(_now=_utc(10, 0))
    )
    session_reasons = [r for r in result.rejection_reasons if "session" in r.lower()]
    assert len(session_reasons) == 0
    monkeypatch.setattr(settings, "RISK_ALLOWED_SESSIONS", [])


# ===========================================================================
# 18. News protection
# ===========================================================================

def test_23_news_protection_blocks(monkeypatch):
    """News filter returning False → trade rejected."""
    monkeypatch.setattr(settings, "NEWS_FILTER_ENABLED", True)
    news = MockNewsFilter(allowed=False)
    result = asyncio.run(
        approve(news_filter=news)
    )
    assert not result.approved
    assert any("news" in r.lower() for r in result.rejection_reasons)


def test_24_news_filter_unavailable_fails_closed(monkeypatch):
    """News filter raises → fail closed when NEWS_FILTER_ENABLED=True."""
    monkeypatch.setattr(settings, "NEWS_FILTER_ENABLED", True)
    news = MockNewsFilter(raises=True)
    result = asyncio.run(
        approve(news_filter=news)
    )
    assert not result.approved
    assert any("news" in r.lower() for r in result.rejection_reasons)


def test_25_no_news_filter_configured_fails_closed(monkeypatch):
    """NEWS_FILTER_ENABLED=True but no filter injected → fail closed."""
    monkeypatch.setattr(settings, "NEWS_FILTER_ENABLED", True)
    mgr = RuleBasedRiskManager(news_filter=None)
    result = asyncio.run(
        approve(manager=mgr, news_filter=None)
    )
    assert not result.approved
    assert any("news" in r.lower() for r in result.rejection_reasons)


def test_25b_news_disabled_with_no_filter(monkeypatch):
    """NEWS_FILTER_ENABLED=False → news check skipped, no news rejection."""
    monkeypatch.setattr(settings, "NEWS_FILTER_ENABLED", False)
    monkeypatch.setattr(settings, "RISK_ALLOWED_SESSIONS", [])
    monkeypatch.setattr(settings, "RISK_MIN_RR", 2.0)
    mgr = RuleBasedRiskManager(news_filter=None)
    result = asyncio.run(
        approve(manager=mgr, news_filter=None)
    )
    news_reasons = [r for r in result.rejection_reasons if "news" in r.lower()]
    assert len(news_reasons) == 0


# ===========================================================================
# 19. Exposure protection
# ===========================================================================

def test_26_currency_exposure_blocked(monkeypatch):
    """EUR exposure already at limit → new EURUSD trade rejected."""
    monkeypatch.setattr(settings, "RISK_MAX_CURRENCY_EXPOSURE_LOTS", 0.2)
    # Two existing EUR positions totalling 0.2 lots
    positions = [
        BrokerPosition(ticket=1, symbol="EURUSD", type="buy", volume=0.1,
                       open_price=1.09, current_price=1.10, sl=1.08,
                       tp=1.11, profit=100.0, open_time=datetime.now(timezone.utc)),
        BrokerPosition(ticket=2, symbol="EURGBP", type="buy", volume=0.1,
                       open_price=0.85, current_price=0.85, sl=0.84,
                       tp=0.86, profit=0.0, open_time=datetime.now(timezone.utc)),
    ]
    result = asyncio.run(
        approve(pair="EURUSD", positions=positions)
    )
    assert not result.approved
    assert any("exposure" in r.lower() for r in result.rejection_reasons)
    monkeypatch.setattr(settings, "RISK_MAX_CURRENCY_EXPOSURE_LOTS", 2.0)


# ===========================================================================
# 20. Full approval path
# ===========================================================================

def test_27_full_approval_path(monkeypatch):
    """All checks pass → approved=True, lot_size > 0, rr_ratio >= min_rr."""
    monkeypatch.setattr(settings, "NEWS_FILTER_ENABLED", False)
    monkeypatch.setattr(settings, "RISK_ALLOWED_SESSIONS", [])
    monkeypatch.setattr(settings, "RISK_MIN_RR", 2.0)
    monkeypatch.setattr(settings, "RISK_MAX_SPREAD_PIPS", 3.0)
    monkeypatch.setattr(settings, "MAX_OPEN_TRADES", 5)
    monkeypatch.setattr(settings, "MAX_DAILY_LOSS_PERCENT", 5.0)
    monkeypatch.setattr(settings, "RISK_MAX_DRAWDOWN_PERCENT", 10.0)
    monkeypatch.setattr(settings, "RISK_MAX_CONSECUTIVE_LOSSES", 3)
    monkeypatch.setattr(settings, "RISK_MAX_DAILY_PROFIT_PERCENT", 0.0)

    # SL=10 pips, TP=20 pips → RR=2.0, spread=1 pip, no positions
    result = asyncio.run(
        approve(
            entry=1.10000, stop_loss=1.0990, take_profit=1.1020,
            bid=1.10000, ask=1.10010,
        )
    )
    assert result.approved, f"Expected approved; reasons: {result.rejection_reasons}"
    assert result.lot_size > 0
    assert result.rr_ratio == pytest.approx(2.0, abs=0.01)
    assert result.risk_amount > 0
    assert len(result.rejection_reasons) == 0


# ===========================================================================
# 21. Full rejection with multiple reasons
# ===========================================================================

def test_28_full_rejection_multiple_reasons(monkeypatch):
    """Multiple failing checks all appear in rejection_reasons."""
    monkeypatch.setattr(settings, "MAX_OPEN_TRADES", 0)   # instant fail
    monkeypatch.setattr(settings, "RISK_MAX_SPREAD_PIPS", 0.1)  # 1-pip spread fails
    # Also wrong-side SL for BUY
    result = asyncio.run(
        approve(
            direction="buy", entry=1.10000,
            stop_loss=1.10100,   # wrong side
            take_profit=1.1020,
            bid=1.10000, ask=1.10010,
        )
    )
    assert not result.approved
    assert len(result.rejection_reasons) >= 2


# ===========================================================================
# 22. Fail-closed — account unavailable
# ===========================================================================

def test_29_fail_closed_account_unavailable():
    """When get_account_info() raises, approve_trade() returns rejected."""
    result = asyncio.run(
        approve(account_raises=True)
    )
    assert not result.approved
    assert any("account" in r.lower() for r in result.rejection_reasons)


def test_30_fail_closed_tick_unavailable():
    """When get_tick() raises, approve_trade() returns rejected."""
    result = asyncio.run(
        approve(tick_raises=True)
    )
    assert not result.approved
    assert any("tick" in r.lower() for r in result.rejection_reasons)


def test_31_fail_closed_positions_unavailable():
    """When get_positions() raises, approve_trade() returns rejected."""
    result = asyncio.run(
        approve(positions_raises=True)
    )
    assert not result.approved
    assert any("position" in r.lower() for r in result.rejection_reasons)


# ===========================================================================
# 23. Trade Manager cannot bypass Risk Manager
# ===========================================================================

class ConcreteTradeManager(BaseTradeManager):
    """Minimal subclass so we can call open_trade() in tests."""
    async def close_trade(self, trade_id, reason): raise NotImplementedError
    async def modify_trade(self, trade_id, stop_loss=None, take_profit=None): raise NotImplementedError
    async def sync_open_positions(self): raise NotImplementedError


def test_32_trade_manager_bypass_no_approval():
    """open_trade() without risk_approval raises ValueError."""
    tm = ConcreteTradeManager()
    req = OrderRequest(
        pair="EURUSD", direction="buy",
        entry_price=1.1000, stop_loss=1.0990,
        take_profit=1.1020, lot_size=0.10,
        risk_approval=None,
    )
    with pytest.raises(ValueError, match="risk_approval"):
        asyncio.run(tm.open_trade(req))


def test_33_trade_manager_bypass_rejected_approval(monkeypatch):
    """open_trade() with rejected approval raises ValueError."""
    approval = RiskApproval(
        approved=False, pair="EURUSD", direction="buy",
        entry=1.1000, stop_loss=1.0990, take_profit=1.1020,
        lot_size=0.0, risk_amount=0.0, risk_pct=1.0, rr_ratio=0.0,
        rejection_reasons=("Test rejection",), protection_flags=(),
        approved_at=datetime.now(timezone.utc),
    )
    tm  = ConcreteTradeManager()
    req = OrderRequest(
        pair="EURUSD", direction="buy",
        entry_price=1.1000, stop_loss=1.0990, take_profit=1.1020,
        lot_size=0.10, risk_approval=approval,
    )
    with pytest.raises(ValueError, match="rejected"):
        asyncio.run(tm.open_trade(req))


def test_34_trade_manager_bypass_wrong_lot_size(monkeypatch):
    """open_trade() with tampered lot_size raises ValueError."""
    approval = RiskApproval(
        approved=True, pair="EURUSD", direction="buy",
        entry=1.1000, stop_loss=1.0990, take_profit=1.1020,
        lot_size=0.10,  # approved for 0.10
        risk_amount=100.0, risk_pct=1.0, rr_ratio=2.0,
        rejection_reasons=(), protection_flags=(),
        approved_at=datetime.now(timezone.utc),
    )
    tm  = ConcreteTradeManager()
    req = OrderRequest(
        pair="EURUSD", direction="buy",
        entry_price=1.1000, stop_loss=1.0990, take_profit=1.1020,
        lot_size=1.00,   # tampered to 1.00
        risk_approval=approval,
    )
    with pytest.raises(ValueError, match="match"):
        asyncio.run(tm.open_trade(req))


# ===========================================================================
# 24. No duplicate closed-trade counting
# ===========================================================================

def test_35_no_duplicate_trade_counting():
    """Recording the same trade_id twice only counts once."""
    mgr = make_manager()
    asyncio.run(mgr.record_closed_trade("trade-001", -100.0))
    asyncio.run(mgr.record_closed_trade("trade-001", -100.0))  # duplicate

    assert mgr._daily_stats is not None
    assert mgr._daily_stats.realized_pnl == pytest.approx(-100.0, abs=0.01)
    assert mgr._daily_stats.consecutive_losses == 1   # only counted once


def test_36_consecutive_loss_resets_on_win():
    """A winning trade resets the consecutive-loss counter to 0."""
    mgr = make_manager()
    asyncio.run(mgr.record_closed_trade("trade-001", -50.0))
    asyncio.run(mgr.record_closed_trade("trade-002", -50.0))
    assert mgr._daily_stats.consecutive_losses == 2

    asyncio.run(mgr.record_closed_trade("trade-003", +100.0))
    assert mgr._daily_stats.consecutive_losses == 0


# ===========================================================================
# 25. Daily reset behaviour
# ===========================================================================

def test_37_daily_reset_new_day():
    """When the date changes, daily stats are reset with the new balance."""
    mgr   = make_manager()
    yesterday = datetime(2024, 6, 2, 12, 0, tzinfo=timezone.utc)
    today_dt  = datetime(2024, 6, 3, 12, 0, tzinfo=timezone.utc)

    # Initialise with yesterday's date and some loss
    mgr._daily_stats = DailyStats(
        trading_date     = yesterday.date(),
        starting_balance = 10_000.0,
        realized_pnl     = -300.0,
        consecutive_losses = 2,
    )

    # _get_or_init_daily with today's date should reset
    daily = mgr._get_or_init_daily(9_700.0, today_dt.date())
    assert daily.trading_date == today_dt.date()
    assert daily.starting_balance == pytest.approx(9_700.0)
    assert daily.realized_pnl == pytest.approx(0.0)
    assert daily.consecutive_losses == 0


# ===========================================================================
# 26. RiskApproval.matches_order
# ===========================================================================

def test_38_risk_approval_matches_order():
    """matches_order() returns True only for exact parameter match."""
    approval = RiskApproval(
        approved=True, pair="EURUSD", direction="buy",
        entry=1.1000, stop_loss=1.0990, take_profit=1.1020,
        lot_size=0.10, risk_amount=100.0, risk_pct=1.0, rr_ratio=2.0,
        rejection_reasons=(), protection_flags=(),
        approved_at=datetime.now(timezone.utc),
    )
    # Exact match
    assert approval.matches_order("EURUSD", "buy", 1.1000, 1.0990, 1.1020, 0.10)
    # Wrong lot size
    assert not approval.matches_order("EURUSD", "buy", 1.1000, 1.0990, 1.1020, 0.20)
    # Wrong direction
    assert not approval.matches_order("EURUSD", "sell", 1.1000, 1.0990, 1.1020, 0.10)
    # Wrong pair
    assert not approval.matches_order("GBPUSD", "buy", 1.1000, 1.0990, 1.1020, 0.10)
    # Rejected approval
    rejected = RiskApproval(
        approved=False, pair="EURUSD", direction="buy",
        entry=1.1000, stop_loss=1.0990, take_profit=1.1020,
        lot_size=0.10, risk_amount=0.0, risk_pct=1.0, rr_ratio=0.0,
        rejection_reasons=("Rejected",), protection_flags=(),
        approved_at=datetime.now(timezone.utc),
    )
    assert not rejected.matches_order("EURUSD", "buy", 1.1000, 1.0990, 1.1020, 0.10)


# ===========================================================================
# 27. _normalize_volume edge cases
# ===========================================================================

def test_39_normalize_volume_nan_returns_zero():
    assert _normalize_volume(math.nan, 0.01, 100.0, 0.01) == 0.0

def test_40_normalize_volume_inf_returns_zero():
    assert _normalize_volume(math.inf, 0.01, 100.0, 0.01) == 0.0

def test_41_normalize_volume_negative_returns_zero():
    assert _normalize_volume(-0.5, 0.01, 100.0, 0.01) == 0.0
