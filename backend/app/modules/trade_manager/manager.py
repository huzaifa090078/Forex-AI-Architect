"""
Trade Manager — concrete implementation (Section 9).

ConcreteTradeManager owns the full order lifecycle:
  AI Engine → Risk Manager → ConcreteTradeManager → IMT5Connector → Exness

Responsibilities:
  • Execute approved Market Buy / Market Sell orders through the connector.
  • Record every execution attempt in the database.
  • Monitor open positions and synchronise local state with the broker.
  • Manage SL/TP modifications and position closes.
  • Reject any order without a valid RiskApproval (inherited gate).

NOT responsible for:
  • Deciding whether a trade is good (AI Engine's job).
  • Calculating risk/lot size (Risk Manager's job).
  • Communicating with MT5 directly (IMT5Connector's job).
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.modules.trade_manager.base import BaseTradeManager
from app.modules.trade_manager.interfaces import OrderRequest, OrderResult
from app.modules.trade_manager.service import TradeService
from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.modules.mt5_integration.interfaces import IMT5Connector

logger = logging.getLogger(__name__)

# MT5 TRADE_RETCODE_DONE
_MT5_RETCODE_DONE = 10009


def _retcode_to_message(retcode: int, broker_comment: str = "") -> str:
    """Return a human-readable message for an MT5 return code."""
    _CODES: Dict[int, str] = {
        10004: "Requote — price changed",
        10006: "Request rejected by broker",
        10007: "Request cancelled by trader",
        10008: "Order placed (pending, not yet executed)",
        10010: "Request partially completed",
        10011: "Request processing error",
        10012: "Request cancelled by timeout",
        10013: "Invalid request",
        10014: "Invalid volume in request",
        10015: "Invalid price in request",
        10016: "Invalid stop-loss or take-profit in request",
        10017: "Trade is disabled",
        10018: "Market is closed",
        10019: "Insufficient funds",
        10020: "Prices changed",
        10021: "No quotes available",
        10022: "Invalid order expiration",
        10023: "Order state changed",
        10024: "Too frequent requests",
        10025: "No changes in request",
        10026: "Auto-trading disabled by server",
        10027: "Auto-trading disabled by client terminal",
        10028: "Request locked for processing",
        10029: "Order or position frozen",
        10030: "Invalid order filling type",
    }
    base = _CODES.get(retcode, f"Broker error (retcode={retcode})")
    return f"{base}: {broker_comment}" if broker_comment else base


class ConcreteTradeManager(BaseTradeManager):
    """
    Production Trade Manager.

    Constructor args:
        connector — an IMT5Connector implementation (RealMT5Connector on Windows,
                    mock/stub in tests).
    """

    def __init__(self, connector: IMT5Connector) -> None:
        self._connector = connector

    # ─── Core execution ──────────────────────────────────────────────────────

    async def open_trade(self, request: OrderRequest, dry_run: bool = False) -> OrderResult:
        """
        Execute an approved market order end-to-end (or perform a safe dry-run):
          1. Validate RiskApproval (inherited gate — raises ValueError on violation).
          2. Pre-flight sanity checks (volume, symbol, direction, SL/TP side).
          3. Duplicate-position protection.
          4. Market-closed check.
          5. Dry-run guard: constructs payload, validates, and exits without broker call.
          6. Send to broker via connector (live execution only).
          7. Validate broker response.
          8. Persist to database.
          9. Return structured result.
        """
        # ── 1. Risk approval gate (raises ValueError if invalid) ──────────────
        self._validate_risk_approval(request)

        # ── 2. Pre-flight sanity checks ───────────────────────────────────────
        if request.lot_size <= 0 or not math.isfinite(request.lot_size):
            return OrderResult(success=False, error_message="Invalid lot size — must be a positive finite number")
        if not request.pair or not request.pair.strip():
            return OrderResult(success=False, error_message="Invalid symbol — pair is empty")
        if request.direction not in ("buy", "sell"):
            return OrderResult(success=False, error_message="Direction must be 'buy' or 'sell'")
        if request.stop_loss <= 0 or request.take_profit <= 0:
            return OrderResult(success=False, error_message="SL and TP must be positive prices")

        # Directional SL / TP placement check
        if request.direction == "buy":
            if request.stop_loss >= request.entry_price:
                return OrderResult(
                    success=False,
                    error_message=f"BUY invalid: stop loss {request.stop_loss} must be below entry {request.entry_price}",
                )
            if request.take_profit <= request.entry_price:
                return OrderResult(
                    success=False,
                    error_message=f"BUY invalid: take profit {request.take_profit} must be above entry {request.entry_price}",
                )
        elif request.direction == "sell":
            if request.stop_loss <= request.entry_price:
                return OrderResult(
                    success=False,
                    error_message=f"SELL invalid: stop loss {request.stop_loss} must be above entry {request.entry_price}",
                )
            if request.take_profit >= request.entry_price:
                return OrderResult(
                    success=False,
                    error_message=f"SELL invalid: take profit {request.take_profit} must be below entry {request.entry_price}",
                )

        # ── 3. Duplicate-position protection ──────────────────────────────────
        if settings.TRADE_PREVENT_DUPLICATE_SYMBOL or settings.TRADE_PREVENT_DUPLICATE_DIRECTION:
            try:
                async with AsyncSessionLocal() as db:
                    direction_check = request.direction if settings.TRADE_PREVENT_DUPLICATE_DIRECTION else None
                    duplicates = await TradeService.get_open_trades_for_pair(db, request.pair, direction_check)
                if duplicates:
                    scope = "symbol+direction" if settings.TRADE_PREVENT_DUPLICATE_DIRECTION else "symbol"
                    return OrderResult(
                        success=False,
                        error_message=(
                            f"Duplicate trade blocked: {request.pair} already has an open "
                            f"position ({scope} protection)"
                        ),
                    )
            except Exception as db_exc:
                logger.debug("Duplicate check DB query skipped/unavailable: %s", db_exc)

        # ── 4. Market-closed protection ───────────────────────────────────────
        from app.modules.market_scanner.session import is_forex_market_open
        market_open = is_forex_market_open()
        is_dry_run = dry_run or getattr(request, "dry_run", False) or request.metadata.get("dry_run", False)

        if not market_open and not is_dry_run:
            logger.info("open_trade: blocked because forex market is currently closed.")
            return OrderResult(
                success=False,
                error_message="ORDER BLOCKED: MARKET CLOSED (Weekend)",
            )

        # ── 5. Safe Dry-Run Execution Guard ───────────────────────────────────
        comment = (
            f"{settings.TRADE_BOT_COMMENT_PREFIX}:"
            f"{request.signal_id or 'manual'}"
        )
        magic = getattr(settings, "TRADE_BOT_MAGIC_NUMBER", 1001)

        if is_dry_run:
            order_type_str = "ORDER_TYPE_BUY (0)" if request.direction == "buy" else "ORDER_TYPE_SELL (1)"
            sanitized_mt5_payload = {
                "action": "TRADE_ACTION_DEAL (1)",
                "symbol": request.pair.upper(),
                "direction": request.direction.upper(),
                "volume": float(request.lot_size),
                "type": order_type_str,
                "price": float(request.entry_price),
                "sl": float(request.stop_loss),
                "tp": float(request.take_profit),
                "magic": int(magic),
                "comment": comment,
                "type_time": "ORDER_TIME_GTC (0)",
                "type_filling": "ORDER_FILLING_IOC (1)",
            }
            risk_amt = getattr(request.risk_approval, "actual_risk", 0.0) if request.risk_approval else 0.0
            rr = getattr(request.risk_approval, "rr_ratio", 0.0) if request.risk_approval else 0.0

            logger.info(
                "DRY RUN ONLY — ORDER NOT SENT: %s %s %.2f lots @ %.5f [SL=%.5f, TP=%.5f] (Execution call NOT made)",
                request.direction.upper(), request.pair.upper(), request.lot_size, request.entry_price,
                request.stop_loss, request.take_profit,
            )

            return OrderResult(
                success=True,
                broker_order_id="DRY_RUN_SIMULATED",
                fill_price=request.entry_price,
                fill_time=datetime.now(timezone.utc),
                error_message="DRY RUN ONLY — ORDER NOT SENT",
                metadata={
                    "dry_run": True,
                    "execution_call_made": False,
                    "symbol": request.pair.upper(),
                    "direction": request.direction,
                    "volume": float(request.lot_size),
                    "entry_price": float(request.entry_price),
                    "stop_loss": float(request.stop_loss),
                    "take_profit": float(request.take_profit),
                    "risk_amount": float(risk_amt),
                    "risk_percentage": float(settings.RISK_PER_TRADE_PERCENT),
                    "rr_ratio": float(rr),
                    "magic_number": int(magic),
                    "comment": comment,
                    "order_type": "buy" if request.direction == "buy" else "sell",
                    "time_in_force": "ORDER_TIME_GTC",
                    "filling_mode": "ORDER_FILLING_IOC",
                    "market_open": market_open,
                    "market_status": "OPEN" if market_open else "CLOSED (Weekend)",
                    "mt5_request_payload": sanitized_mt5_payload,
                },
            )

        # ── 6. Send to broker (LIVE ORDERS ONLY) ───────────────────────────────
        try:
            broker_resp = await self._connector.send_market_order(
                symbol=request.pair.upper(),
                direction=request.direction,
                volume=request.lot_size,
                sl=request.stop_loss,
                tp=request.take_profit,
                comment=comment,
            )
        except RuntimeError as exc:
            logger.warning("open_trade: broker unavailable: %s", exc)
            return OrderResult(success=False, error_message=str(exc))
        except Exception as exc:  # pragma: no cover
            logger.error("open_trade: unexpected broker error: %s", exc)
            return OrderResult(success=False, error_message=f"Unexpected broker error: {exc}")

        # ── 5. Validate broker response ───────────────────────────────────────
        retcode = broker_resp.get("retcode", -1)
        if retcode != _MT5_RETCODE_DONE:
            err_comment = broker_resp.get("comment", "")
            logger.warning(
                "open_trade: broker rejected order pair=%s retcode=%s comment=%s",
                request.pair, retcode, err_comment,
            )
            return OrderResult(
                success=False,
                error_message=_retcode_to_message(retcode, err_comment),
                metadata=broker_resp,
            )

        # ── 6. Extract execution details ──────────────────────────────────────
        ticket      = str(broker_resp.get("order") or broker_resp.get("deal") or "")
        fill_price  = float(broker_resp.get("price") or request.entry_price)
        fill_time   = datetime.now(timezone.utc)
        exec_volume = float(broker_resp.get("volume") or request.lot_size)

        rr = getattr(request.risk_approval, "rr_ratio", None)

        # ── 7. Persist to DB (with one retry — Task 5) ───────────────────────
        trade_record = {
            "user_id":           settings.TRADE_BOT_USER_ID,
            "pair":              request.pair.upper(),
            "direction":         request.direction,
            "entry_price":       fill_price,
            "stop_loss":         request.stop_loss,
            "take_profit":       request.take_profit,
            "lot_size":          exec_volume,
            "status":            "open",
            "broker_order_id":   ticket,
            "opened_at":         fill_time,
            "signal_id":         request.signal_id,
            "notes":             request.notes or None,
            "risk_reward_ratio": rr,
        }
        db_persisted = False
        db_error: Optional[str] = None
        for attempt in range(2):  # initial attempt + 1 retry
            try:
                async with AsyncSessionLocal() as db:
                    await TradeService.create_trade(db, trade_record)
                db_persisted = True
                break
            except Exception as exc:
                db_error = str(exc)
                if attempt == 0:
                    logger.warning(
                        "open_trade: DB persist attempt 1 failed (ticket=%s pair=%s) — retrying: %s",
                        ticket, request.pair, exc,
                    )
                else:
                    logger.critical(
                        "CRITICAL: Trade executed on broker (ticket=%s pair=%s) but DB persist "
                        "FAILED after retry — position is untracked. Manual recovery required. "
                        "Error: %s",
                        ticket, request.pair, exc,
                    )

        logger.info(
            "open_trade: executed pair=%s direction=%s lot=%.2f ticket=%s fill=%.5f db_ok=%s",
            request.pair, request.direction, exec_volume, ticket, fill_price, db_persisted,
        )
        result_meta: Dict[str, Any] = {**broker_resp, "executed_volume": exec_volume}
        if not db_persisted:
            result_meta["db_persist_failed"] = True
            result_meta["db_error"] = db_error
        return OrderResult(
            success=True,
            broker_order_id=ticket,
            fill_price=fill_price,
            fill_time=fill_time,
            metadata=result_meta,
        )

    async def close_trade(self, trade_id: str, reason: str) -> OrderResult:
        """
        Close an open position at market price.
        Looks up the trade's broker ticket from the DB, instructs the connector
        to close it, then updates the DB record with the realized P&L.
        """
        async with AsyncSessionLocal() as db:
            trade = await TradeService.get_trade(db, trade_id)

        if trade is None:
            return OrderResult(success=False, error_message=f"Trade {trade_id} not found")
        if trade.status != "open":
            return OrderResult(
                success=False,
                error_message=f"Trade {trade_id} is not open (status={trade.status!r})",
            )
        if not trade.broker_order_id:
            return OrderResult(
                success=False,
                error_message=f"Trade {trade_id} has no broker ticket — cannot close via broker",
            )

        try:
            ticket = int(trade.broker_order_id)
        except (ValueError, TypeError):
            return OrderResult(
                success=False,
                error_message=f"Invalid broker ticket {trade.broker_order_id!r} — cannot convert to int",
            )

        try:
            broker_resp = await self._connector.close_position(ticket)
        except RuntimeError as exc:
            return OrderResult(success=False, error_message=str(exc))
        except Exception as exc:
            logger.error("close_trade: unexpected error for ticket=%s: %s", ticket, exc)
            return OrderResult(success=False, error_message=f"Unexpected error: {exc}")

        retcode = broker_resp.get("retcode", -1)
        if retcode != _MT5_RETCODE_DONE:
            return OrderResult(
                success=False,
                error_message=_retcode_to_message(retcode, broker_resp.get("comment", "")),
                metadata=broker_resp,
            )

        close_price = float(broker_resp.get("price") or 0)
        profit      = float(broker_resp.get("profit") or 0)
        close_time  = datetime.now(timezone.utc)

        try:
            async with AsyncSessionLocal() as db:
                await TradeService.mark_trade_closed(
                    db, trade_id,
                    pnl=profit,
                    close_reason=reason,
                    close_price=close_price,
                    closed_at=close_time,
                )
        except Exception as exc:
            logger.error("close_trade: DB update failed for trade %s: %s", trade_id, exc)

        logger.info(
            "close_trade: closed trade=%s ticket=%s reason=%s pnl=%.2f",
            trade_id, ticket, reason, profit,
        )
        return OrderResult(
            success=True,
            broker_order_id=str(ticket),
            fill_price=close_price,
            fill_time=close_time,
            metadata={**broker_resp, "pnl": profit},
        )

    async def modify_trade(
        self,
        trade_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        """
        Modify the SL and/or TP on an open position.
        Validates price levels before forwarding to broker.
        Calls the broker first; updates the DB only on ACK.
        """
        if stop_loss is None and take_profit is None:
            logger.warning("modify_trade: called with no changes for trade %s", trade_id)
            return True  # no-op, not an error

        async with AsyncSessionLocal() as db:
            trade = await TradeService.get_trade(db, trade_id)

        if trade is None:
            logger.warning("modify_trade: trade %s not found", trade_id)
            return False
        if trade.status != "open":
            logger.warning("modify_trade: trade %s not open (status=%s)", trade_id, trade.status)
            return False
        if not trade.broker_order_id:
            logger.warning("modify_trade: trade %s has no broker ticket", trade_id)
            return False

        # ── Task 7: SL/TP validation ──────────────────────────────────────────
        entry     = trade.entry_price
        direction = trade.direction

        if stop_loss is not None:
            if stop_loss <= 0 or not math.isfinite(stop_loss):
                logger.warning(
                    "modify_trade: invalid SL=%.5f for trade %s — must be a positive finite number",
                    stop_loss, trade_id,
                )
                return False
            if direction == "buy" and stop_loss >= entry:
                logger.warning(
                    "modify_trade: SL=%.5f must be below entry=%.5f for BUY trade %s",
                    stop_loss, entry, trade_id,
                )
                return False
            if direction == "sell" and stop_loss <= entry:
                logger.warning(
                    "modify_trade: SL=%.5f must be above entry=%.5f for SELL trade %s",
                    stop_loss, entry, trade_id,
                )
                return False

        if take_profit is not None:
            if take_profit <= 0 or not math.isfinite(take_profit):
                logger.warning(
                    "modify_trade: invalid TP=%.5f for trade %s — must be a positive finite number",
                    take_profit, trade_id,
                )
                return False
            if direction == "buy" and take_profit <= entry:
                logger.warning(
                    "modify_trade: TP=%.5f must be above entry=%.5f for BUY trade %s",
                    take_profit, entry, trade_id,
                )
                return False
            if direction == "sell" and take_profit >= entry:
                logger.warning(
                    "modify_trade: TP=%.5f must be below entry=%.5f for SELL trade %s",
                    take_profit, entry, trade_id,
                )
                return False

        try:
            ticket = int(trade.broker_order_id)
        except (ValueError, TypeError):
            return False

        try:
            success = await self._connector.modify_position(
                ticket,
                sl=stop_loss,
                tp=take_profit,
            )
        except RuntimeError as exc:
            logger.error("modify_trade: broker unavailable: %s", exc)
            return False
        except Exception as exc:
            logger.error("modify_trade: unexpected error ticket=%s: %s", ticket, exc)
            return False

        if success:
            updates: Dict[str, Any] = {}
            if stop_loss is not None:
                updates["stop_loss"] = stop_loss
            if take_profit is not None:
                updates["take_profit"] = take_profit
            try:
                async with AsyncSessionLocal() as db:
                    await TradeService.update_trade(db, trade_id, **updates)
            except Exception as exc:
                logger.error("modify_trade: DB update failed for trade %s: %s", trade_id, exc)
        else:
            logger.warning("modify_trade: broker rejected modification for ticket=%s", ticket)

        return success

    async def sync_open_positions(self) -> List[Dict[str, Any]]:
        """
        Reconcile local database state with the broker's live open positions.

        1. Fetch all open positions from MT5 via the connector.
        2. Fetch all 'open' trades from the DB.
        3. Any DB trade whose broker ticket is no longer on the broker is
           marked 'closed' with reason='broker_closed' (SL/TP hit, or
           manually closed on the MT5 terminal).
        4. Return the broker's live position list as plain dicts.

        On Linux/non-Windows (no MT5), the connector raises RuntimeError;
        this is caught and logged at DEBUG level — the monitor continues
        running so it is ready when a real connection becomes available.
        """
        try:
            broker_positions = await self._connector.get_positions()
        except RuntimeError as exc:
            logger.debug("sync_open_positions: MT5 not available on this platform: %s", exc)
            return []
        except Exception as exc:
            logger.error("sync_open_positions: unexpected broker error: %s", exc)
            return []

        broker_ticket_set = {str(p.ticket) for p in broker_positions}

        # Detect DB-open trades that the broker has already closed
        try:
            async with AsyncSessionLocal() as db:
                db_trades = await TradeService.get_open_trades(db)
        except Exception as exc:
            logger.error("sync_open_positions: DB query failed: %s", exc)
            return []

        for trade in db_trades:
            if trade.broker_order_id and trade.broker_order_id not in broker_ticket_set:
                logger.info(
                    "sync: trade=%s ticket=%s no longer on broker → marking closed",
                    trade.id, trade.broker_order_id,
                )
                try:
                    async with AsyncSessionLocal() as db:
                        await TradeService.mark_trade_closed(
                            db, trade.id,
                            pnl=None,
                            close_reason="broker_closed",
                            close_price=None,
                            closed_at=datetime.now(timezone.utc),
                        )
                except Exception as exc:
                    logger.error("sync: DB update failed for trade %s: %s", trade.id, exc)

        # Return current broker state as plain dicts
        now = datetime.now(timezone.utc)
        result = []
        for p in broker_positions:
            duration = int((now - p.open_time).total_seconds()) if p.open_time else 0
            result.append({
                "ticket":           p.ticket,
                "symbol":           p.symbol,
                "direction":        p.type,
                "volume":           p.volume,
                "open_price":       p.open_price,
                "current_price":    p.current_price,
                "sl":               p.sl,
                "tp":               p.tp,
                "profit":           p.profit,
                "open_time":        p.open_time.isoformat() if p.open_time else None,
                "duration_seconds": duration,
                "comment":          p.comment,
            })
        return result


# ─── Module-level singleton ──────────────────────────────────────────────────
# Uses RealMT5Connector. On Replit/Linux the constructor is safe — the
# RuntimeError is only raised when connector methods try to call the MT5 library.

from app.modules.mt5_integration.base import RealMT5Connector as _RealMT5Connector  # noqa: E402
trade_manager = ConcreteTradeManager(connector=_RealMT5Connector())
