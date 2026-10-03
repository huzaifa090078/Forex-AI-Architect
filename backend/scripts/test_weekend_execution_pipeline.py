"""
Complete Weekend / Market-Closed Execution Pipeline Test Suite.

Tests the full trading execution pipeline:
  Signal generation → Risk Manager → Position sizing → SL/TP calculation
  → Trade validation → MT5 order construction → Execution guard → Position management.

STRICT SAFETY CONSTRAINTS:
  • DRY-RUN / VALIDATION ONLY.
  • NO real or demo orders sent to MT5.
  • NO positions opened, modified, or closed.
  • NO fake successful trades in MT5 history.
  • Full verification that execution call is NOT made.
"""

from __future__ import annotations

import asyncio
import logging
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, patch

# Configure backend path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.modules.market_scanner.session import (
    TradingSession,
    get_current_session,
    is_forex_market_open,
)
from app.modules.news_filter import news_filter as _news_filter
from app.modules.mt5_integration.base import RealMT5Connector, _MT5_AVAILABLE
from app.modules.mt5_integration.interfaces import (
    AccountInfo,
    BrokerPosition,
    BrokerDeal,
    IMT5Connector,
)
from app.modules.risk_manager.manager import RuleBasedRiskManager
from app.modules.risk_manager.types import RiskApproval
from app.modules.trade_manager.interfaces import OrderRequest, OrderResult
from app.modules.trade_manager.manager import ConcreteTradeManager
from app.modules.trade_manager.service import TradeService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("weekend_test")


class ExecutionSpyConnector(RealMT5Connector):
    """
    Instrumented MT5 connector subclass that acts as a strict watchdog.
    If send_market_order is ever invoked during dry-run, it immediately triggers an assertion failure.
    """
    def __init__(self):
        super().__init__()
        self.send_order_calls = 0
        self.last_order_kwargs = None

    async def send_market_order(self, *args, **kwargs) -> Dict[str, Any]:
        self.send_order_calls += 1
        self.last_order_kwargs = kwargs
        raise AssertionError("CRITICAL VIOLATION: send_market_order was called during dry-run validation!")


async def run_weekend_pipeline_tests():
    print("=" * 80)
    print("COMPLETE WEEKEND / MARKET-CLOSED EXECUTION PIPELINE TEST")
    print("=" * 80)
    print(f"Time (UTC): {datetime.now(timezone.utc).isoformat()}")
    print(f"Platform: Windows | MetaTrader 5 available: {_MT5_AVAILABLE}")
    print(f"Risk Config: RISK_PER_TRADE_PERCENT={settings.RISK_PER_TRADE_PERCENT}%, "
          f"RISK_MIN_RR={settings.RISK_MIN_RR}, MAX_OPEN_TRADES={settings.MAX_OPEN_TRADES}")
    print("=" * 80)

    # Instantiate real connector and watchdog spy
    real_connector = RealMT5Connector()
    spy_connector = ExecutionSpyConnector()

    connected = await real_connector.connect()
    assert connected, "Failed to connect to MT5 terminal"
    await spy_connector.connect()

    account = await real_connector.get_account_info()
    print(f"Connected MT5 Account: {account.login} | Server: {account.server} | Balance: ${account.balance:.2f} | Equity: ${account.equity:.2f}")

    test_results: List[Dict[str, Any]] = []

    def record(test_num: int, name: str, passed: bool, details: str):
        status = "PASS" if passed else "FAIL"
        test_results.append({
            "num": test_num,
            "name": name,
            "status": status,
            "details": details,
        })
        print(f"[{status}] Test {test_num}: {name}")
        print(f"       -> {details}")

    # Initialize Risk Manager with the existing news filter
    risk_mgr = RuleBasedRiskManager(news_filter=_news_filter)
    trade_mgr_spy = ConcreteTradeManager(connector=spy_connector)

    # Fetch symbol specification and current tick for EURUSD
    symbol_cand = "EURUSD"
    symbol_info = await real_connector.get_symbol_info(symbol_cand)
    tick = await real_connector.get_tick(symbol_cand)
    ask_price = float(tick["ask"])
    bid_price = float(tick["bid"])
    spread_pips = float(tick["spread"]) / (float(symbol_info["tick_size"]) * 10.0)

    print(f"Market Quote: {symbol_cand} Ask={ask_price:.5f}, Bid={bid_price:.5f}, Spread={spread_pips:.1f} pips")

    # On a $100 account with 1% risk ($1.00 budget):
    # 0.01 lot of EURUSD has pip value $0.10.
    # 10 pips SL = $1.00 risk (exact match to 1% of $100 budget).
    # 20 pips TP = R:R 2.0 (satisfies RISK_MIN_RR=2.0).
    sl_distance = 0.00100   # 10 pips
    tp_distance = 0.00200   # 20 pips

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 1: Valid BUY Order Construction (Dry-Run)
    # ─────────────────────────────────────────────────────────────────────────
    try:
        entry = ask_price
        sl = round(entry - sl_distance, 5)
        tp = round(entry + tp_distance, 5)

        # Risk Manager approval (Section 8)
        approval = await risk_mgr.approve_trade(
            pair=symbol_cand,
            direction="buy",
            entry=entry,
            stop_loss=sl,
            take_profit=tp,
            connector=real_connector,
        )

        assert approval.approved, f"Risk Manager rejected valid BUY: {approval.rejection_reasons}"

        # Construct OrderRequest with dry_run=True
        req = OrderRequest(
            pair=symbol_cand,
            direction="buy",
            entry_price=entry,
            stop_loss=approval.stop_loss,
            take_profit=approval.take_profit,
            lot_size=approval.lot_size,
            risk_approval=approval,
            signal_id="test_buy_001",
            dry_run=True,
        )

        res = await trade_mgr_spy.open_trade(req, dry_run=True)

        passed = (
            res.success is True
            and res.error_message == "DRY RUN ONLY — ORDER NOT SENT"
            and res.metadata.get("execution_call_made") is False
            and spy_connector.send_order_calls == 0
            and res.metadata.get("direction") == "buy"
            and res.metadata.get("mt5_request_payload") is not None
        )
        payload = res.metadata.get("mt5_request_payload", {})
        details = (
            f"Simulated BUY {payload.get('symbol')} {payload.get('volume')} lots @ {payload.get('price'):.5f} "
            f"[SL={payload.get('sl'):.5f}, TP={payload.get('tp'):.5f}, RR={approval.rr_ratio:.2f}]. "
            f"Result: '{res.error_message}'. Execution calls: {spy_connector.send_order_calls}"
        )
        record(1, "Valid BUY order construction", passed, details)
    except Exception as e:
        record(1, "Valid BUY order construction", False, f"Exception: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 2: Valid SELL Order Construction (Dry-Run)
    # ─────────────────────────────────────────────────────────────────────────
    try:
        entry = bid_price
        sl = round(entry + sl_distance, 5)
        tp = round(entry - tp_distance, 5)

        approval = await risk_mgr.approve_trade(
            pair=symbol_cand,
            direction="sell",
            entry=entry,
            stop_loss=sl,
            take_profit=tp,
            connector=real_connector,
        )

        assert approval.approved, f"Risk Manager rejected valid SELL: {approval.rejection_reasons}"

        req = OrderRequest(
            pair=symbol_cand,
            direction="sell",
            entry_price=entry,
            stop_loss=approval.stop_loss,
            take_profit=approval.take_profit,
            lot_size=approval.lot_size,
            risk_approval=approval,
            signal_id="test_sell_001",
            dry_run=True,
        )

        res = await trade_mgr_spy.open_trade(req, dry_run=True)

        passed = (
            res.success is True
            and res.error_message == "DRY RUN ONLY — ORDER NOT SENT"
            and res.metadata.get("execution_call_made") is False
            and spy_connector.send_order_calls == 0
            and res.metadata.get("direction") == "sell"
            and res.metadata.get("mt5_request_payload") is not None
        )
        payload = res.metadata.get("mt5_request_payload", {})
        details = (
            f"Simulated SELL {payload.get('symbol')} {payload.get('volume')} lots @ {payload.get('price'):.5f} "
            f"[SL={payload.get('sl'):.5f}, TP={payload.get('tp'):.5f}, RR={approval.rr_ratio:.2f}]. "
            f"Result: '{res.error_message}'. Execution calls: {spy_connector.send_order_calls}"
        )
        record(2, "Valid SELL order construction", passed, details)
    except Exception as e:
        record(2, "Valid SELL order construction", False, f"Exception: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 3: Invalid Symbol Rejection
    # ─────────────────────────────────────────────────────────────────────────
    try:
        invalid_pair = "NONEXISTENT_XYZ"
        # 1. Risk Manager rejects invalid symbol fail-closed
        app_inv = await risk_mgr.approve_trade(
            pair=invalid_pair,
            direction="buy",
            entry=1.2345,
            stop_loss=1.2300,
            take_profit=1.2400,
            connector=real_connector,
        )
        risk_rejected = not app_inv.approved and any("unavailable" in r.lower() for r in app_inv.rejection_reasons)

        # 2. Trade Manager rejects empty symbol in pre-flight
        dummy_approval = RiskApproval(
            approved=True,
            pair="",
            direction="buy",
            entry=1.2345,
            stop_loss=1.2300,
            take_profit=1.2400,
            lot_size=0.01,
            risk_amount=1.0,
            risk_pct=1.0,
            rr_ratio=2.0,
            rejection_reasons=(),
            protection_flags=(),
            approved_at=datetime.now(timezone.utc),
        )
        empty_req = OrderRequest(
            pair="",
            direction="buy",
            entry_price=1.2345,
            stop_loss=1.2300,
            take_profit=1.2400,
            lot_size=0.01,
            risk_approval=dummy_approval,
            dry_run=True,
        )
        tm_res = await trade_mgr_spy.open_trade(empty_req, dry_run=True)
        tm_rejected = not tm_res.success and "Invalid symbol" in (tm_res.error_message or "")

        passed = risk_rejected and tm_rejected and spy_connector.send_order_calls == 0
        details = (
            f"Risk Manager rejected '{invalid_pair}': '{app_inv.rejection_reasons[0]}'. "
            f"Trade Manager rejected empty symbol: '{tm_res.error_message}'."
        )
        record(3, "Invalid symbol rejection", passed, details)
    except Exception as e:
        record(3, "Invalid symbol rejection", False, f"Exception: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 4: Invalid Volume Rejection
    # ─────────────────────────────────────────────────────────────────────────
    try:
        vol_approval = RiskApproval(
            approved=True,
            pair=symbol_cand,
            direction="buy",
            entry=ask_price,
            stop_loss=ask_price - sl_distance,
            take_profit=ask_price + tp_distance,
            lot_size=0.0,
            risk_amount=0.0,
            risk_pct=1.0,
            rr_ratio=2.0,
            rejection_reasons=(),
            protection_flags=(),
            approved_at=datetime.now(timezone.utc),
        )
        # Zero lot
        zero_req = OrderRequest(
            pair=symbol_cand,
            direction="buy",
            entry_price=ask_price,
            stop_loss=ask_price - sl_distance,
            take_profit=ask_price + tp_distance,
            lot_size=0.0,
            risk_approval=vol_approval,
            dry_run=True,
        )
        zero_res = await trade_mgr_spy.open_trade(zero_req, dry_run=True)

        # Negative lot
        neg_approval = RiskApproval(
            approved=True,
            pair=symbol_cand,
            direction="buy",
            entry=ask_price,
            stop_loss=ask_price - sl_distance,
            take_profit=ask_price + tp_distance,
            lot_size=-0.05,
            risk_amount=0.0,
            risk_pct=1.0,
            rr_ratio=2.0,
            rejection_reasons=(),
            protection_flags=(),
            approved_at=datetime.now(timezone.utc),
        )
        neg_req = OrderRequest(
            pair=symbol_cand,
            direction="buy",
            entry_price=ask_price,
            stop_loss=ask_price - sl_distance,
            take_profit=ask_price + tp_distance,
            lot_size=-0.05,
            risk_approval=neg_approval,
            dry_run=True,
        )
        neg_res = await trade_mgr_spy.open_trade(neg_req, dry_run=True)

        passed = (
            not zero_res.success
            and "Invalid lot size" in (zero_res.error_message or "")
            and not neg_res.success
            and "Invalid lot size" in (neg_res.error_message or "")
            and spy_connector.send_order_calls == 0
        )
        details = f"Zero lot rejected: '{zero_res.error_message}'. Negative lot rejected: '{neg_res.error_message}'."
        record(4, "Invalid volume rejection", passed, details)
    except Exception as e:
        record(4, "Invalid volume rejection", False, f"Exception: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 5: Invalid SL/TP Boundary Rejection
    # ─────────────────────────────────────────────────────────────────────────
    try:
        # 1. BUY with SL above entry
        buy_bad_sl = await risk_mgr.approve_trade(
            pair=symbol_cand,
            direction="buy",
            entry=1.1000,
            stop_loss=1.1050,  # invalid: above entry
            take_profit=1.1100,
            connector=real_connector,
        )
        # 2. BUY with TP below entry
        buy_bad_tp = await risk_mgr.approve_trade(
            pair=symbol_cand,
            direction="buy",
            entry=1.1000,
            stop_loss=1.0950,
            take_profit=1.0900,  # invalid: below entry
            connector=real_connector,
        )
        # 3. SELL with SL below entry
        sell_bad_sl = await risk_mgr.approve_trade(
            pair=symbol_cand,
            direction="sell",
            entry=1.1000,
            stop_loss=1.0950,  # invalid: below entry
            take_profit=1.0900,
            connector=real_connector,
        )
        # 4. SELL with TP above entry
        sell_bad_tp = await risk_mgr.approve_trade(
            pair=symbol_cand,
            direction="sell",
            entry=1.1000,
            stop_loss=1.1050,
            take_profit=1.1100,  # invalid: above entry
            connector=real_connector,
        )

        passed = (
            not buy_bad_sl.approved
            and not buy_bad_tp.approved
            and not sell_bad_sl.approved
            and not sell_bad_tp.approved
            and spy_connector.send_order_calls == 0
        )
        details = (
            f"BUY bad SL: {buy_bad_sl.rejection_reasons[0]}; "
            f"BUY bad TP: {buy_bad_tp.rejection_reasons[0]}; "
            f"SELL bad SL: {sell_bad_sl.rejection_reasons[0]}; "
            f"SELL bad TP: {sell_bad_tp.rejection_reasons[0]}."
        )
        record(5, "Invalid SL/TP boundary rejection", passed, details)
    except Exception as e:
        record(5, "Invalid SL/TP boundary rejection", False, f"Exception: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 6: Invalid Risk & Sub-minimum R:R Rejection
    # ─────────────────────────────────────────────────────────────────────────
    try:
        # Proposed trade with R:R = 0.5 (SL=20 pips, TP=10 pips) while RISK_MIN_RR=2.0
        bad_rr_app = await risk_mgr.approve_trade(
            pair=symbol_cand,
            direction="buy",
            entry=1.1000,
            stop_loss=1.0980,    # 20 pips
            take_profit=1.1010,  # 10 pips (RR = 0.5)
            connector=real_connector,
        )

        passed = (
            not bad_rr_app.approved
            and any("below minimum" in r for r in bad_rr_app.rejection_reasons)
            and spy_connector.send_order_calls == 0
        )
        rr_reasons = [r for r in bad_rr_app.rejection_reasons if "below minimum" in r]
        details = f"Sub-minimum R:R rejected: '{rr_reasons[0]}'. Minimum required: {settings.RISK_MIN_RR}"
        record(6, "Invalid risk / R:R rejection", passed, details)
    except Exception as e:
        record(6, "Invalid risk / R:R rejection", False, f"Exception: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 7: Duplicate Position Protection
    # ─────────────────────────────────────────────────────────────────────────
    try:
        # Generate valid approval
        entry = ask_price
        sl = round(entry - sl_distance, 5)
        tp = round(entry + tp_distance, 5)
        valid_app = await risk_mgr.approve_trade(
            pair=symbol_cand,
            direction="buy",
            entry=entry,
            stop_loss=sl,
            take_profit=tp,
            connector=real_connector,
        )
        assert valid_app.approved, "Approval must be valid for duplicate test"

        dup_req = OrderRequest(
            pair=symbol_cand,
            direction="buy",
            entry_price=entry,
            stop_loss=valid_app.stop_loss,
            take_profit=valid_app.take_profit,
            lot_size=valid_app.lot_size,
            risk_approval=valid_app,
            dry_run=True,
        )

        # Mock database query returning an existing open trade for EURUSD
        with patch.object(TradeService, "get_open_trades_for_pair", new=AsyncMock(return_value=[{"id": "existing-1"}])):
            dup_res = await trade_mgr_spy.open_trade(dup_req, dry_run=True)

        passed = (
            not dup_res.success
            and "Duplicate trade blocked" in (dup_res.error_message or "")
            and spy_connector.send_order_calls == 0
        )
        details = f"Duplicate trade blocked: '{dup_res.error_message}'. Execution calls: {spy_connector.send_order_calls}"
        record(7, "Duplicate position protection", passed, details)
    except Exception as e:
        record(7, "Duplicate position protection", False, f"Exception: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 8: Market Closed Protection (Weekend Verification)
    # ─────────────────────────────────────────────────────────────────────────
    try:
        now_dt = datetime.now(timezone.utc)
        market_open = is_forex_market_open(now_dt)
        session = get_current_session(now_dt)

        # In live mode (dry_run=False), if market is closed, open_trade MUST block execution
        # Verify weekend logic
        saturday_dt = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)
        sat_market_open = is_forex_market_open(saturday_dt)
        sat_session = get_current_session(saturday_dt)

        assert sat_market_open is False, "Saturday must be evaluated as market closed!"
        assert sat_session == TradingSession.WEEKEND, f"Expected WEEKEND session, got {sat_session}"

        # Attempt a live trade on closed market
        live_req = OrderRequest(
            pair=symbol_cand,
            direction="buy",
            entry_price=entry,
            stop_loss=valid_app.stop_loss,
            take_profit=valid_app.take_profit,
            lot_size=valid_app.lot_size,
            risk_approval=valid_app,
            dry_run=False,  # Live execution attempt
        )

        with patch("app.modules.market_scanner.session.is_forex_market_open", return_value=False):
            closed_res = await trade_mgr_spy.open_trade(live_req, dry_run=False)

        passed = (
            not closed_res.success
            and "ORDER BLOCKED: MARKET CLOSED" in (closed_res.error_message or "")
            and spy_connector.send_order_calls == 0
        )
        details = (
            f"Current UTC: {now_dt.strftime('%A %H:%M UTC')} | "
            f"Market Open: {market_open} | Active Session: '{session.value}'. "
            f"Blocked Order Result: '{closed_res.error_message}'. Broker calls: {spy_connector.send_order_calls}"
        )
        record(8, "Market closed protection", passed, details)
    except Exception as e:
        record(8, "Market closed protection", False, f"Exception: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 9: Risk Limit Protection (Max Open Trades)
    # ─────────────────────────────────────────────────────────────────────────
    try:
        # Simulate 5 positions already open (MAX_OPEN_TRADES=5)
        mock_positions = [
            BrokerPosition(
                ticket=100 + i, symbol="EURUSD", type="buy", volume=0.01,
                open_price=1.1, current_price=1.1, sl=1.09, tp=1.12, profit=0.0,
                open_time=datetime.now(timezone.utc),
            )
            for i in range(settings.MAX_OPEN_TRADES)
        ]

        with patch.object(real_connector, "get_positions", new=AsyncMock(return_value=mock_positions)):
            limit_app = await risk_mgr.approve_trade(
                pair=symbol_cand,
                direction="buy",
                entry=ask_price,
                stop_loss=ask_price - sl_distance,
                take_profit=ask_price + tp_distance,
                connector=real_connector,
            )

        passed = (
            not limit_app.approved
            and any("Maximum open trades reached" in r for r in limit_app.rejection_reasons)
            and spy_connector.send_order_calls == 0
        )
        reasons = [r for r in limit_app.rejection_reasons if "Maximum open trades reached" in r]
        details = f"Blocked when positions={len(mock_positions)}: '{reasons[0]}'. Limit={settings.MAX_OPEN_TRADES}"
        record(9, "Risk limit protection (Max open trades)", passed, details)
    except Exception as e:
        record(9, "Risk limit protection (Max open trades)", False, f"Exception: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 10: Critical Execution Guard (Zero Broker Calls)
    # ─────────────────────────────────────────────────────────────────────────
    try:
        # Run 5 consecutive dry-run orders
        for i in range(5):
            req_guard = OrderRequest(
                pair=symbol_cand,
                direction="buy" if i % 2 == 0 else "sell",
                entry_price=ask_price,
                stop_loss=valid_app.stop_loss if i % 2 == 0 else ask_price + sl_distance,
                take_profit=valid_app.take_profit if i % 2 == 0 else ask_price - tp_distance,
                lot_size=valid_app.lot_size,
                risk_approval=valid_app if i % 2 == 0 else RiskApproval(
                    approved=True,
                    pair=symbol_cand,
                    direction="sell",
                    entry=ask_price,
                    stop_loss=ask_price + sl_distance,
                    take_profit=ask_price - tp_distance,
                    lot_size=valid_app.lot_size,
                    risk_amount=1.0,
                    risk_pct=1.0,
                    rr_ratio=2.0,
                    rejection_reasons=(),
                    protection_flags=(),
                    approved_at=datetime.now(timezone.utc),
                ),
                dry_run=True,
            )
            await trade_mgr_spy.open_trade(req_guard, dry_run=True)

        passed = (spy_connector.send_order_calls == 0)
        details = f"Verified: Exactly 0 broker calls made across all test cycles. Watchdog send_order_calls={spy_connector.send_order_calls}."
        record(10, "Critical dry-run execution guard", passed, details)
    except Exception as e:
        record(10, "Critical dry-run execution guard", False, f"Exception: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 11: MT5 Connection Failure Handling (Fail-Closed)
    # ─────────────────────────────────────────────────────────────────────────
    try:
        failing_connector = AsyncMock(spec=IMT5Connector)
        failing_connector.get_account_info.side_effect = RuntimeError("MT5 terminal connection dropped")

        fail_app = await risk_mgr.approve_trade(
            pair=symbol_cand,
            direction="buy",
            entry=1.1000,
            stop_loss=1.0980,
            take_profit=1.1040,
            connector=failing_connector,
        )

        passed = (
            not fail_app.approved
            and any("fail-closed" in r.lower() for r in fail_app.rejection_reasons)
        )
        details = f"Fail-closed verification: approval.approved={fail_app.approved}, reason='{fail_app.rejection_reasons[0]}'."
        record(11, "MT5 connection failure handling", passed, details)
    except Exception as e:
        record(11, "MT5 connection failure handling", False, f"Exception: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 12: MT5 Order Request Payload Validation & Sanitization
    # ─────────────────────────────────────────────────────────────────────────
    try:
        # Inspect generated payload for sanitization and completeness
        test_req = OrderRequest(
            pair=symbol_cand,
            direction="buy",
            entry_price=ask_price,
            stop_loss=valid_app.stop_loss,
            take_profit=valid_app.take_profit,
            lot_size=valid_app.lot_size,
            risk_approval=valid_app,
            signal_id="verify_payload_01",
            dry_run=True,
        )
        order_res = await trade_mgr_spy.open_trade(test_req, dry_run=True)
        payload = order_res.metadata.get("mt5_request_payload", {})

        required_keys = [
            "action", "symbol", "direction", "volume", "type",
            "price", "sl", "tp", "magic", "comment", "type_time", "type_filling",
        ]
        has_all_keys = all(k in payload for k in required_keys)

        # Credentials leakage check
        payload_str = str(payload).lower()
        forbidden_keywords = ["password", "token", "secret", "090078", "trial15"]
        no_credentials_leaked = not any(kw in payload_str for kw in forbidden_keywords)

        passed = has_all_keys and no_credentials_leaked
        details = (
            f"All {len(required_keys)} required MT5 order fields verified. "
            f"Filling: '{payload.get('type_filling')}', TimeInForce: '{payload.get('type_time')}', "
            f"Magic: {payload.get('magic')}. Credentials sanitization: 100% CLEAN."
        )
        record(12, "MT5 order request validation & sanitization", passed, details)
    except Exception as e:
        record(12, "MT5 order request validation & sanitization", False, f"Exception: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    passed_count = sum(1 for t in test_results if t["status"] == "PASS")
    total_count = len(test_results)
    print(f"AUTOMATED TEST RESULTS: {passed_count}/{total_count} PASSED")
    print("=" * 80)
    for t in test_results:
        print(f"[{t['status']}] Test {t['num']}: {t['name']}")

    assert passed_count == total_count, f"Some tests failed: {passed_count}/{total_count}"
    print("\nALL 12/12 EXECUTION PIPELINE TESTS COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(run_weekend_pipeline_tests())
