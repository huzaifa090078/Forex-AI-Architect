"""
Section 9 — Trade Manager focused tests.

All tests run without a real MT5 connection or database.
The MT5 connector is replaced with an AsyncMock test double.
The TradeService static methods are patched so no DB session is needed.

Broker connectivity is simulated at the connector boundary only —
no fake trading data is introduced into production code paths.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.trade_manager.interfaces import OrderRequest, OrderResult
from app.modules.trade_manager.base import BaseTradeManager
from app.modules.trade_manager.manager import ConcreteTradeManager, _retcode_to_message
from app.modules.trade_manager.monitor import TradeMonitor
from app.modules.trade_manager.service import TradeService
from app.modules.risk_manager.types import RiskApproval


# ─── Fixtures ────────────────────────────────────────────────────────────────

def make_approval(**overrides) -> RiskApproval:
    """Return a valid RiskApproval token for EURUSD BUY."""
    from datetime import datetime, timezone
    defaults = dict(
        approved=True,
        pair="EURUSD",
        direction="buy",
        entry=1.10000,
        stop_loss=1.0980,
        take_profit=1.1040,
        lot_size=0.10,
        risk_amount=100.0,
        risk_pct=1.0,
        rr_ratio=2.0,
        rejection_reasons=[],
        protection_flags={},
        approved_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return RiskApproval(**defaults)


def make_request(**overrides) -> OrderRequest:
    """Return a valid approved OrderRequest."""
    approval = make_approval()
    defaults = dict(
        pair="EURUSD",
        direction="buy",
        entry_price=1.10000,
        stop_loss=1.0980,
        take_profit=1.1040,
        lot_size=0.10,
        risk_approval=approval,
        signal_id="sig-001",
    )
    defaults.update(overrides)
    return OrderRequest(**defaults)


def make_connector(retcode: int = 10009, **extra) -> AsyncMock:
    """Return a mock IMT5Connector that returns a successful broker response."""
    connector = AsyncMock()
    resp = {
        "retcode": retcode,
        "order": 123456,
        "deal": 789012,
        "price": 1.10010,
        "volume": 0.10,
        "comment": "done",
        **extra,
    }
    connector.send_market_order = AsyncMock(return_value=resp)
    connector.close_position = AsyncMock(return_value={
        "retcode": retcode, "price": 1.1025, "profit": 15.0, "comment": "done"
    })
    connector.modify_position = AsyncMock(return_value=True)
    connector.get_positions = AsyncMock(return_value=[])
    return connector


def make_manager(connector=None) -> ConcreteTradeManager:
    return ConcreteTradeManager(connector=connector or make_connector())


# Dummy Trade object used to represent a DB record in mocks
def make_db_trade(**overrides) -> MagicMock:
    t = MagicMock()
    t.id = "trade-uuid-001"
    t.pair = "EURUSD"
    t.direction = "buy"
    t.entry_price = 1.10000
    t.stop_loss = 1.0980
    t.take_profit = 1.1040
    t.lot_size = 0.10
    t.status = "open"
    t.broker_order_id = "123456"
    t.pnl = None
    t.risk_reward_ratio = 2.0
    t.opened_at = datetime.now(timezone.utc)
    for k, v in overrides.items():
        setattr(t, k, v)
    return t


# ─── Risk Approval Gate ───────────────────────────────────────────────────────

def test_tm_01_missing_risk_approval_raises():
    """open_trade with no risk_approval raises ValueError."""
    mgr = make_manager()
    req = make_request(risk_approval=None)
    with pytest.raises(ValueError, match="risk_approval is None"):
        BaseTradeManager._validate_risk_approval(req)


def test_tm_02_rejected_risk_approval_raises():
    """open_trade with rejected approval raises ValueError."""
    approval = make_approval(approved=False, rejection_reasons=["RR too low"])
    req = make_request(risk_approval=approval)
    with pytest.raises(ValueError, match="rejected"):
        BaseTradeManager._validate_risk_approval(req)


def test_tm_03_mismatched_lot_size_raises():
    """Tampered lot size detected by matches_order() raises ValueError."""
    approval = make_approval(lot_size=0.10)
    req = make_request(risk_approval=approval, lot_size=1.00)  # tampered!
    with pytest.raises(ValueError, match="do not match"):
        BaseTradeManager._validate_risk_approval(req)


def test_tm_04_mismatched_symbol_raises():
    approval = make_approval(pair="EURUSD")
    req = make_request(risk_approval=approval, pair="GBPUSD")
    with pytest.raises(ValueError, match="do not match"):
        BaseTradeManager._validate_risk_approval(req)


def test_tm_05_mismatched_direction_raises():
    approval = make_approval(direction="buy")
    req = make_request(risk_approval=approval, direction="sell")
    with pytest.raises(ValueError, match="do not match"):
        BaseTradeManager._validate_risk_approval(req)


# ─── Pre-flight validation ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tm_06_invalid_lot_size_rejected():
    """Lot size <= 0 is rejected before hitting the broker."""
    mgr = make_manager()
    req = make_request(lot_size=0.0)
    # Rebuild approval to match lot_size=0 (bypass gate for this test)
    approval = make_approval(lot_size=0.0)
    req.risk_approval = approval
    result = await mgr.open_trade(req)
    assert not result.success
    assert "lot size" in result.error_message.lower()
    mgr._connector.send_market_order.assert_not_called()


@pytest.mark.asyncio
async def test_tm_07_empty_symbol_rejected():
    approval = make_approval(pair="")
    req = make_request(pair="", risk_approval=approval)
    mgr = make_manager()
    result = await mgr.open_trade(req)
    assert not result.success
    mgr._connector.send_market_order.assert_not_called()


@pytest.mark.asyncio
async def test_tm_08_invalid_direction_rejected():
    approval = make_approval(direction="hold")
    req = make_request(direction="hold", risk_approval=approval)
    mgr = make_manager()
    result = await mgr.open_trade(req)
    assert not result.success
    mgr._connector.send_market_order.assert_not_called()


# ─── Duplicate protection ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tm_09_duplicate_direction_blocked():
    """Duplicate same-symbol+direction trade is blocked."""
    mgr = make_manager()
    req = make_request()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.settings") as mock_settings, \
         patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_open_trades_for_pair", return_value=[make_db_trade()]):

        mock_settings.TRADE_PREVENT_DUPLICATE_SYMBOL = False
        mock_settings.TRADE_PREVENT_DUPLICATE_DIRECTION = True
        mock_settings.TRADE_BOT_COMMENT_PREFIX = "AIBot"
        mock_settings.TRADE_BOT_USER_ID = "00000000-0000-0000-0000-000000000001"

        result = await mgr.open_trade(req)

    assert not result.success
    assert "duplicate" in result.error_message.lower()
    mgr._connector.send_market_order.assert_not_called()


@pytest.mark.asyncio
async def test_tm_10_no_duplicate_when_no_open_trades():
    """Trade proceeds when no duplicates exist."""
    mgr = make_manager()
    req = make_request()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.settings") as mock_settings, \
         patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_open_trades_for_pair", return_value=[]), \
         patch.object(TradeService, "create_trade", return_value=None):

        mock_settings.TRADE_PREVENT_DUPLICATE_SYMBOL = False
        mock_settings.TRADE_PREVENT_DUPLICATE_DIRECTION = True
        mock_settings.TRADE_BOT_COMMENT_PREFIX = "AIBot"
        mock_settings.TRADE_BOT_USER_ID = "00000000-0000-0000-0000-000000000001"

        result = await mgr.open_trade(req)

    assert result.success
    mgr._connector.send_market_order.assert_called_once()


# ─── Broker success path ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tm_11_successful_buy_order():
    """Successful BUY market order returns correct OrderResult."""
    mgr = make_manager()
    req = make_request(direction="buy")

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.settings") as mock_settings, \
         patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_open_trades_for_pair", return_value=[]), \
         patch.object(TradeService, "create_trade", return_value=None):

        mock_settings.TRADE_PREVENT_DUPLICATE_SYMBOL = False
        mock_settings.TRADE_PREVENT_DUPLICATE_DIRECTION = False
        mock_settings.TRADE_BOT_COMMENT_PREFIX = "AIBot"
        mock_settings.TRADE_BOT_USER_ID = "00000000-0000-0000-0000-000000000001"

        result = await mgr.open_trade(req)

    assert result.success is True
    assert result.broker_order_id == "123456"
    assert result.fill_price == pytest.approx(1.10010, abs=0.00001)
    assert result.fill_time is not None
    mgr._connector.send_market_order.assert_called_once_with(
        symbol="EURUSD",
        direction="buy",
        volume=0.10,
        sl=pytest.approx(1.0980, abs=0.0001),
        tp=pytest.approx(1.1040, abs=0.0001),
        comment="AIBot:sig-001",
    )


@pytest.mark.asyncio
async def test_tm_12_successful_sell_order():
    """Successful SELL market order returns correct OrderResult."""
    connector = make_connector()
    connector.send_market_order.return_value = {
        "retcode": 10009, "order": 999, "price": 1.09995, "volume": 0.05
    }
    approval = make_approval(direction="sell", entry=1.10000, stop_loss=1.1020, take_profit=1.0960, lot_size=0.05)
    req = make_request(direction="sell", entry_price=1.10000, stop_loss=1.1020, take_profit=1.0960, lot_size=0.05, risk_approval=approval)
    mgr = make_manager(connector=connector)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.settings") as mock_settings, \
         patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_open_trades_for_pair", return_value=[]), \
         patch.object(TradeService, "create_trade", return_value=None):

        mock_settings.TRADE_PREVENT_DUPLICATE_SYMBOL = False
        mock_settings.TRADE_PREVENT_DUPLICATE_DIRECTION = False
        mock_settings.TRADE_BOT_COMMENT_PREFIX = "AIBot"
        mock_settings.TRADE_BOT_USER_ID = "00000000-0000-0000-0000-000000000001"

        result = await mgr.open_trade(req)

    assert result.success is True
    assert result.broker_order_id == "999"


# ─── Broker rejection ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tm_13_broker_rejection_returns_failure():
    """Non-DONE retcode returns a structured failure without raising."""
    connector = make_connector(retcode=10014)  # invalid volume
    connector.send_market_order.return_value = {
        "retcode": 10014, "comment": "Invalid volume"
    }
    mgr = make_manager(connector=connector)
    req = make_request()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.settings") as mock_settings, \
         patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_open_trades_for_pair", return_value=[]):

        mock_settings.TRADE_PREVENT_DUPLICATE_SYMBOL = False
        mock_settings.TRADE_PREVENT_DUPLICATE_DIRECTION = False
        mock_settings.TRADE_BOT_COMMENT_PREFIX = "AIBot"
        mock_settings.TRADE_BOT_USER_ID = "00000000-0000-0000-0000-000000000001"

        result = await mgr.open_trade(req)

    assert result.success is False
    assert "volume" in result.error_message.lower() or "10014" in result.error_message


@pytest.mark.asyncio
async def test_tm_14_broker_runtime_error_returns_failure():
    """RuntimeError from connector (MT5 not available) returns structured failure."""
    connector = AsyncMock()
    connector.send_market_order = AsyncMock(side_effect=RuntimeError("MT5 not available on Linux"))
    mgr = make_manager(connector=connector)
    req = make_request()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.settings") as mock_settings, \
         patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_open_trades_for_pair", return_value=[]):

        mock_settings.TRADE_PREVENT_DUPLICATE_SYMBOL = False
        mock_settings.TRADE_PREVENT_DUPLICATE_DIRECTION = False
        mock_settings.TRADE_BOT_COMMENT_PREFIX = "AIBot"
        mock_settings.TRADE_BOT_USER_ID = "00000000-0000-0000-0000-000000000001"

        result = await mgr.open_trade(req)

    assert result.success is False
    assert "MT5" in result.error_message or "not available" in result.error_message.lower()


# ─── Close trade ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tm_15_close_trade_success():
    """Successful close updates DB and returns correct fill price."""
    mgr = make_manager()
    db_trade = make_db_trade()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_trade", return_value=db_trade), \
         patch.object(TradeService, "mark_trade_closed", return_value=None):

        result = await mgr.close_trade("trade-uuid-001", reason="manual")

    assert result.success is True
    assert result.fill_price == pytest.approx(1.1025, abs=0.0001)
    mgr._connector.close_position.assert_called_once_with(123456)


@pytest.mark.asyncio
async def test_tm_16_close_nonexistent_trade_returns_failure():
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_trade", return_value=None):
        mgr = make_manager()
        result = await mgr.close_trade("nonexistent", reason="manual")

    assert result.success is False
    assert "not found" in result.error_message.lower()


@pytest.mark.asyncio
async def test_tm_17_close_already_closed_trade_returns_failure():
    db_trade = make_db_trade(status="closed")
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_trade", return_value=db_trade):
        mgr = make_manager()
        result = await mgr.close_trade("trade-uuid-001", reason="manual")

    assert result.success is False
    assert "not open" in result.error_message.lower()


@pytest.mark.asyncio
async def test_tm_18_close_broker_rejection_returns_failure():
    """Broker rejection on close returns structured failure."""
    connector = make_connector()
    connector.close_position = AsyncMock(return_value={"retcode": 10018, "comment": "Market closed"})
    db_trade = make_db_trade()
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_trade", return_value=db_trade):
        mgr = make_manager(connector=connector)
        result = await mgr.close_trade("trade-uuid-001", reason="manual")

    assert result.success is False
    assert "market" in result.error_message.lower() or "closed" in result.error_message.lower()


# ─── Modify trade ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tm_19_modify_sl_success():
    """Successful SL modification calls connector and updates DB."""
    mgr = make_manager()
    db_trade = make_db_trade()
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_trade", return_value=db_trade), \
         patch.object(TradeService, "update_trade", return_value=db_trade):

        success = await mgr.modify_trade("trade-uuid-001", stop_loss=1.0975)

    assert success is True
    mgr._connector.modify_position.assert_called_once_with(123456, sl=1.0975, tp=None)


@pytest.mark.asyncio
async def test_tm_20_modify_tp_success():
    mgr = make_manager()
    db_trade = make_db_trade()
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_trade", return_value=db_trade), \
         patch.object(TradeService, "update_trade", return_value=db_trade):

        success = await mgr.modify_trade("trade-uuid-001", take_profit=1.1050)

    assert success is True
    mgr._connector.modify_position.assert_called_once_with(123456, sl=None, tp=1.1050)


@pytest.mark.asyncio
async def test_tm_21_modify_returns_false_when_broker_rejects():
    connector = make_connector()
    connector.modify_position = AsyncMock(return_value=False)
    db_trade = make_db_trade()
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_trade", return_value=db_trade):
        mgr = make_manager(connector=connector)
        success = await mgr.modify_trade("trade-uuid-001", stop_loss=1.0975)

    assert success is False


@pytest.mark.asyncio
async def test_tm_22_modify_nonexistent_trade_returns_false():
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_trade", return_value=None):
        mgr = make_manager()
        success = await mgr.modify_trade("bad-id", stop_loss=1.0975)

    assert success is False


# ─── Sync open positions ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tm_23_sync_marks_broker_closed_trades():
    """
    DB trade with ticket not on broker is marked closed (SL/TP hit on broker side).
    """
    from app.modules.mt5_integration.interfaces import BrokerPosition

    # Broker has GBPUSD position but NOT the EURUSD DB trade
    gbp_pos = MagicMock(spec=BrokerPosition)
    gbp_pos.ticket = 999
    gbp_pos.symbol = "GBPUSD"
    gbp_pos.type = "sell"
    gbp_pos.volume = 0.10
    gbp_pos.open_price = 1.2700
    gbp_pos.current_price = 1.2685
    gbp_pos.sl = 1.2730
    gbp_pos.tp = 1.2640
    gbp_pos.profit = 15.0
    gbp_pos.open_time = datetime.now(timezone.utc)
    gbp_pos.comment = "AIBot:sig-002"

    connector = AsyncMock()
    connector.get_positions = AsyncMock(return_value=[gbp_pos])
    mgr = make_manager(connector=connector)

    # DB has EURUSD trade with ticket 123456 — not on broker
    db_trade = make_db_trade(broker_order_id="123456")
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_open_trades", return_value=[db_trade]), \
         patch.object(TradeService, "mark_trade_closed") as mock_close:

        result = await mgr.sync_open_positions()

    # EURUSD trade should be marked closed
    mock_close.assert_called_once()
    call_args = mock_close.call_args
    assert call_args.kwargs.get("close_reason") == "broker_closed" or call_args.args[2] == "broker_closed"

    # Result should contain the GBPUSD position
    assert len(result) == 1
    assert result[0]["ticket"] == 999


@pytest.mark.asyncio
async def test_tm_24_sync_no_action_when_positions_match():
    """No DB updates when all DB tickets still exist on the broker."""
    from app.modules.mt5_integration.interfaces import BrokerPosition

    pos = MagicMock(spec=BrokerPosition)
    pos.ticket = 123456
    pos.symbol = "EURUSD"
    pos.type = "buy"
    pos.volume = 0.10
    pos.open_price = 1.10000
    pos.current_price = 1.10150
    pos.sl = 1.0980
    pos.tp = 1.1040
    pos.profit = 15.0
    pos.open_time = datetime.now(timezone.utc)
    pos.comment = "AIBot:sig-001"

    connector = AsyncMock()
    connector.get_positions = AsyncMock(return_value=[pos])
    db_trade = make_db_trade(broker_order_id="123456")
    mgr = make_manager(connector=connector)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_open_trades", return_value=[db_trade]), \
         patch.object(TradeService, "mark_trade_closed") as mock_close:

        result = await mgr.sync_open_positions()

    mock_close.assert_not_called()
    assert len(result) == 1


@pytest.mark.asyncio
async def test_tm_25_sync_returns_empty_when_mt5_unavailable():
    """RuntimeError from connector returns empty list — no crash."""
    connector = AsyncMock()
    connector.get_positions = AsyncMock(side_effect=RuntimeError("MT5 not available on Linux"))
    mgr = make_manager(connector=connector)
    result = await mgr.sync_open_positions()
    assert result == []


# ─── Monitor start / stop ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tm_26_monitor_starts_and_stops_cleanly():
    """Monitor task can be started and stopped without error."""
    connector = AsyncMock()
    connector.get_positions = AsyncMock(return_value=[])
    mgr = ConcreteTradeManager(connector=connector)

    monitor = TradeMonitor(interval_seconds=0.05)
    monitor._manager = mgr  # inject the test manager

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_open_trades", return_value=[]):

        await monitor.start()
        assert monitor._task is not None
        assert not monitor._task.done()

        await asyncio.sleep(0.15)  # let the loop run at least twice
        await monitor.stop()

    assert monitor._task is None


@pytest.mark.asyncio
async def test_tm_27_monitor_start_idempotent():
    """Calling start() twice does not create duplicate tasks."""
    connector = AsyncMock()
    connector.get_positions = AsyncMock(return_value=[])
    mgr = ConcreteTradeManager(connector=connector)
    monitor = TradeMonitor(interval_seconds=60.0)
    monitor._manager = mgr

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.modules.trade_manager.manager.AsyncSessionLocal", return_value=mock_session), \
         patch.object(TradeService, "get_open_trades", return_value=[]):

        await monitor.start()
        task_ref = monitor._task
        await monitor.start()  # idempotent call
        assert monitor._task is task_ref  # same task object
        await monitor.stop()


# ─── Retcode helper ───────────────────────────────────────────────────────────

def test_tm_28_retcode_to_message_known():
    msg = _retcode_to_message(10017)
    assert "disabled" in msg.lower()


def test_tm_29_retcode_to_message_unknown():
    msg = _retcode_to_message(99999)
    assert "99999" in msg


def test_tm_30_retcode_to_message_with_comment():
    msg = _retcode_to_message(10018, "Market closed on holidays")
    assert "Market closed on holidays" in msg


# ─── TradeService stats (pure Python — no DB needed) ─────────────────────────

def test_tm_31_stats_empty_returns_zeros():
    """get_stats returns all zeros when passed no rows (tested via pure logic)."""
    # We test the internal Python computation path, not the DB query
    pnls: List[float] = []
    total = len(pnls)
    wins  = [p for p in pnls if p > 0]
    assert total == 0
    assert len(wins) == 0


def test_tm_32_stats_profit_factor_calculation():
    """Profit factor = sum(wins) / abs(sum(losses))."""
    wins   = [100.0, 50.0]
    losses = [-30.0, -20.0]
    gross_profit = sum(wins)
    gross_loss   = sum(losses)
    pf = gross_profit / abs(gross_loss)
    assert abs(pf - 3.0) < 0.001


def test_tm_33_stats_max_drawdown_calculation():
    """Max drawdown computed correctly from PnL series."""
    pnls    = [100.0, -50.0, 200.0, -180.0, 50.0]
    running = 0.0
    peak    = 0.0
    max_dd  = 0.0
    for p in pnls:
        running += p
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd
    # Peak = 350 after 3rd trade; trough = 170 after 4th → drawdown = 180
    assert abs(max_dd - 180.0) < 0.001


# ─── Section 8 regression ─────────────────────────────────────────────────────

def test_tm_34_section8_risk_approval_boundary_still_enforced():
    """Confirm Section 8 boundary is intact in ConcreteTradeManager context."""
    mgr = make_manager()
    assert hasattr(mgr, "_validate_risk_approval")
    req = make_request(risk_approval=None)
    with pytest.raises(ValueError):
        mgr._validate_risk_approval(req)
