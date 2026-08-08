"""
Risk Manager — RuleBasedRiskManager (Section 8 concrete implementation).

Single source of truth for all trade risk approval.  Every proposed trade from
the AI Decision Engine must pass approve_trade() before the Trade Manager is
permitted to send an order to the broker.

Architectural guarantees:
  - Fails CLOSED: any unavailable required data → approved=False, never approved=True.
  - No fake / mock / hardcoded account or market data.
  - Stateless per-call except for in-memory daily stats (persistence-compatible).
  - Fully dependency-injected: MT5 connector and news filter are passed in, never
    created internally.
  - Session detection delegates to the existing session.py utility.
  - News protection delegates to the injected INewsFilter (if configured).
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.modules.market_scanner.session import get_current_session
from app.modules.mt5_integration.interfaces import AccountInfo, BrokerPosition, IMT5Connector
from app.modules.news_filter.interfaces import INewsFilter
from app.modules.risk_manager.interfaces import (
    IRiskManager,
    PositionSize,
    RiskCheckResult,
)
from app.modules.risk_manager.types import (
    DailyStats,
    ProtectionState,
    RiskApproval,
    SymbolSpec,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_currencies(pair: str) -> List[str]:
    """
    Extract base and quote currency codes from a forex pair symbol.
    e.g. 'EURUSD' → ['EUR', 'USD'],  'EUR/USD' → ['EUR', 'USD'].
    """
    clean = pair.replace("/", "").replace("_", "").replace(" ", "").upper()
    if len(clean) >= 6:
        return [clean[:3], clean[3:6]]
    return [clean]


def _normalize_volume(
    raw:         float,
    volume_min:  float,
    volume_max:  float,
    volume_step: float,
) -> float:
    """
    Normalize a raw lot size to broker volume constraints.

    Uses floor (not round) so the actual monetary risk never exceeds the
    requested budget after normalization.  Returns 0.0 for invalid inputs.
    """
    if not math.isfinite(raw) or raw <= 0:
        return 0.0
    steps      = math.floor(raw / volume_step)
    normalized = round(steps * volume_step, 10)   # eliminate float artifacts
    return max(volume_min, min(volume_max, normalized))


# ---------------------------------------------------------------------------
# Concrete implementation
# ---------------------------------------------------------------------------

class RuleBasedRiskManager(IRiskManager):
    """
    Production risk manager implementing all Section 8 protections.

    Daily stats are kept in memory (persistence-compatible structure).
    The news filter is optional; when news_protection is required but no
    filter is injected the trade is rejected (fail-closed).

    Usage:
        manager = RuleBasedRiskManager(news_filter=my_filter)
        approval = await manager.approve_trade(
            pair="EURUSD", direction="buy",
            entry=1.10000, stop_loss=1.0990, take_profit=1.1020,
            connector=mt5_connector,
        )
    """

    def __init__(
        self,
        news_filter: Optional[INewsFilter] = None,
    ) -> None:
        self._news_filter:  Optional[INewsFilter] = news_filter
        self._daily_stats:  Optional[DailyStats]  = None   # reset at UTC midnight

    # ── daily stats helpers ─────────────────────────────────────────────────

    def _get_or_init_daily(self, current_balance: float, today: date) -> DailyStats:
        """Return today's DailyStats, initialising or resetting as needed."""
        if self._daily_stats is None or self._daily_stats.trading_date != today:
            self._daily_stats = DailyStats(
                trading_date     = today,
                starting_balance = current_balance,
            )
        return self._daily_stats

    # ── lot size computation ────────────────────────────────────────────────

    def _compute_lot_and_risk(
        self,
        equity:    float,
        risk_pct:  float,
        entry:     float,
        stop_loss: float,
        spec:      SymbolSpec,
    ) -> Tuple[float, float]:
        """
        Compute (lot_size, risk_amount) from account equity and symbol spec.

        Uses actual MT5 tick_size and tick_value — no hardcoded pip values.

        Returns (0.0, 0.0) and logs a warning on any invalid input rather
        than raising, so the caller can include a rejection reason.
        """
        sl_distance = abs(entry - stop_loss)
        if sl_distance <= 0 or spec.tick_size <= 0 or spec.tick_value <= 0:
            logger.warning("Lot sizing: invalid distance or tick spec — sl_distance=%s", sl_distance)
            return 0.0, 0.0

        monetary_risk = equity * (risk_pct / 100.0)
        sl_ticks      = sl_distance / spec.tick_size
        lot_raw       = monetary_risk / (sl_ticks * spec.tick_value)

        lot_final     = _normalize_volume(
            lot_raw, spec.volume_min, spec.volume_max, spec.volume_step
        )
        actual_risk   = lot_final * sl_ticks * spec.tick_value
        return lot_final, actual_risk

    # ── SL / TP validation ──────────────────────────────────────────────────

    @staticmethod
    def _validate_sl(
        direction: str,
        entry:     float,
        stop_loss: float,
        spec:      SymbolSpec,
    ) -> List[str]:
        reasons: List[str] = []

        if stop_loss is None or not math.isfinite(stop_loss) or stop_loss == 0:
            reasons.append("Stop loss is missing or invalid")
            return reasons

        min_sl_distance = spec.tick_size * 10   # minimum 1 pip (10 ticks)

        if direction.lower() == "buy":
            if stop_loss >= entry:
                reasons.append(
                    f"BUY: stop loss {stop_loss} must be below entry {entry}"
                )
            elif entry - stop_loss < min_sl_distance:
                reasons.append(
                    f"Stop loss too close to entry — minimum distance is {min_sl_distance:.5f}"
                )
        elif direction.lower() == "sell":
            if stop_loss <= entry:
                reasons.append(
                    f"SELL: stop loss {stop_loss} must be above entry {entry}"
                )
            elif stop_loss - entry < min_sl_distance:
                reasons.append(
                    f"Stop loss too close to entry — minimum distance is {min_sl_distance:.5f}"
                )
        else:
            reasons.append(f"Unknown direction '{direction}'")

        # Maximum SL distance check (configurable)
        max_sl_pips = settings.RISK_MAX_SL_PIPS
        if max_sl_pips > 0 and math.isfinite(max_sl_pips):
            sl_distance_pips = abs(entry - stop_loss) / (spec.tick_size * 10)
            if sl_distance_pips > max_sl_pips:
                reasons.append(
                    f"Stop loss distance {sl_distance_pips:.1f} pips exceeds maximum {max_sl_pips:.1f} pips"
                )

        return reasons

    @staticmethod
    def _validate_tp(
        direction:   str,
        entry:       float,
        stop_loss:   float,
        take_profit: float,
    ) -> List[str]:
        reasons: List[str] = []

        if take_profit is None or not math.isfinite(take_profit) or take_profit == 0:
            reasons.append("Take profit is missing or invalid")
            return reasons

        if abs(take_profit - entry) <= 0:
            reasons.append("Take profit must differ from entry price")
            return reasons

        if direction.lower() == "buy":
            if take_profit <= entry:
                reasons.append(
                    f"BUY: take profit {take_profit} must be above entry {entry}"
                )
        elif direction.lower() == "sell":
            if take_profit >= entry:
                reasons.append(
                    f"SELL: take profit {take_profit} must be below entry {entry}"
                )

        return reasons

    # ── R:R computation ─────────────────────────────────────────────────────

    @staticmethod
    def _compute_rr(entry: float, stop_loss: float, take_profit: float) -> float:
        """Return the actual risk:reward ratio. Returns 0.0 on invalid inputs."""
        sl_dist = abs(entry - stop_loss)
        tp_dist = abs(take_profit - entry)
        if sl_dist <= 0:
            return 0.0
        return tp_dist / sl_dist

    # ── protection checks ───────────────────────────────────────────────────

    def _is_daily_loss_exceeded(
        self,
        daily:          DailyStats,
        current_equity: float,
    ) -> bool:
        """
        True when combined realized + unrealized daily loss >= configured limit.

        Splits realized (closed trades) from unrealized (floating P&L) to avoid
        double-counting positions already reflected in equity.
        """
        if settings.MAX_DAILY_LOSS_PERCENT <= 0:
            return False
        if daily.starting_balance <= 0:
            return False

        realized_loss = max(0.0, -daily.realized_pnl)

        # Unrealized loss = balance after realized − current equity
        balance_after_realized = daily.starting_balance + daily.realized_pnl
        unrealized_loss        = max(0.0, balance_after_realized - current_equity)

        total_loss_pct = (
            (realized_loss + unrealized_loss) / daily.starting_balance * 100.0
        )
        return total_loss_pct >= settings.MAX_DAILY_LOSS_PERCENT

    def _is_daily_profit_reached(
        self,
        daily:          DailyStats,
        current_equity: float,
        current_balance: float,
    ) -> bool:
        """True when daily profit limit is enabled and reached."""
        limit = settings.RISK_MAX_DAILY_PROFIT_PERCENT
        if limit <= 0:
            return False
        profit_pct = (current_equity - daily.starting_balance) / daily.starting_balance * 100.0
        return profit_pct >= limit

    def _is_drawdown_exceeded(
        self,
        daily:          DailyStats,
        current_equity: float,
    ) -> bool:
        """True when current drawdown from day-open balance >= configured limit."""
        limit = settings.RISK_MAX_DRAWDOWN_PERCENT
        if limit <= 0:
            return False
        if daily.starting_balance <= 0:
            return False
        drawdown_pct = max(
            0.0,
            (daily.starting_balance - current_equity) / daily.starting_balance * 100.0,
        )
        return drawdown_pct >= limit

    def _check_session(self, dt: Optional[datetime] = None) -> Optional[str]:
        """
        Return a rejection reason if the current session is not in the allowed list.
        Returns None when all sessions are allowed (empty list) or session is allowed.
        """
        allowed = settings.RISK_ALLOWED_SESSIONS
        if not allowed:
            return None   # empty = all sessions permitted

        current = get_current_session(dt)
        current_lower = current.value.lower()
        for s in allowed:
            s_lower = s.lower()
            if s_lower in current_lower or current_lower in s_lower:
                return None   # this session is allowed

        return (
            f"Current session '{current.value}' is not in allowed sessions "
            f"{settings.RISK_ALLOWED_SESSIONS}"
        )

    @staticmethod
    def _check_exposure(
        pair:      str,
        positions: List[BrokerPosition],
    ) -> Optional[str]:
        """
        Return a rejection reason if adding this trade would breach exposure limits.

        Checks:
          1. Total open lots across all positions.
          2. Per-currency lots (base and quote of the proposed pair).

        Uses actual broker positions — no fake exposure data.
        """
        currencies = _extract_currencies(pair)

        # Total open lots
        total_lots = sum(p.volume for p in positions)
        if total_lots >= settings.RISK_MAX_TOTAL_OPEN_LOTS:
            return (
                f"Total open exposure {total_lots:.2f} lots at limit "
                f"{settings.RISK_MAX_TOTAL_OPEN_LOTS:.2f} — cannot add new position"
            )

        # Per-currency exposure
        for currency in currencies:
            currency_lots = sum(
                p.volume for p in positions
                if currency in p.symbol.upper()
            )
            if currency_lots >= settings.RISK_MAX_CURRENCY_EXPOSURE_LOTS:
                return (
                    f"{currency} exposure {currency_lots:.2f} lots at limit "
                    f"{settings.RISK_MAX_CURRENCY_EXPOSURE_LOTS:.2f} lots"
                )

        return None

    # ── spread in pips ──────────────────────────────────────────────────────

    @staticmethod
    def _spread_pips(tick_data: Dict[str, Any], spec: SymbolSpec) -> float:
        """Convert MT5 spread (price units) to pips using the symbol's tick size."""
        spread_price = float(tick_data.get("spread", 0.0))
        if spec.tick_size <= 0:
            return 0.0
        # 1 pip = 10 ticks for standard 5/3-digit brokers
        return spread_price / (spec.tick_size * 10.0)

    # ── IRiskManager.approve_trade ──────────────────────────────────────────

    async def approve_trade(
        self,
        pair:        str,
        direction:   str,
        entry:       float,
        stop_loss:   float,
        take_profit: float,
        connector:   IMT5Connector,
        *,
        news_filter: Optional[INewsFilter] = None,
        metadata:    Optional[Dict[str, Any]] = None,
        _now:        Optional[datetime] = None,   # for testing only
    ) -> RiskApproval:
        """
        Single authoritative approval path for all Section 8 risk checks.

        Fails CLOSED — returns approved=False on any unavailable required data.
        Never raises; always returns a RiskApproval with reasons.
        """
        reasons:  List[str] = []
        flags:    List[str] = []
        now_utc   = _now if _now is not None else datetime.now(timezone.utc)
        today     = now_utc.date()
        effective_news = news_filter or self._news_filter

        # ── 1. Account info (fail-closed) ────────────────────────────────────
        try:
            account: AccountInfo = await connector.get_account_info()
        except Exception as exc:
            logger.error("approve_trade: account info unavailable — %s", exc)
            return self._rejected(
                pair, direction, entry, stop_loss, take_profit, now_utc,
                ("Account data unavailable — fail-closed",),
            )

        # ── 2. Symbol specification (fail-closed) ────────────────────────────
        try:
            spec_dict = await connector.get_symbol_info(pair)
            spec = SymbolSpec(
                symbol        = pair,
                tick_size     = float(spec_dict["tick_size"]),
                tick_value    = float(spec_dict["tick_value"]),
                contract_size = float(spec_dict["contract_size"]),
                volume_min    = float(spec_dict["volume_min"]),
                volume_max    = float(spec_dict["volume_max"]),
                volume_step   = float(spec_dict["volume_step"]),
                digits        = int(spec_dict["digits"]),
            )
            if spec.tick_size <= 0 or spec.tick_value <= 0 or spec.volume_step <= 0:
                raise ValueError("Symbol spec contains zero/negative values")
        except Exception as exc:
            logger.error("approve_trade: symbol spec unavailable for %s — %s", pair, exc)
            return self._rejected(
                pair, direction, entry, stop_loss, take_profit, now_utc,
                (f"Symbol specification unavailable for {pair} — fail-closed",),
            )

        # ── 3. Tick / spread data (fail-closed) ─────────────────────────────
        try:
            tick_data = await connector.get_tick(pair)
            spread_pips = self._spread_pips(tick_data, spec)
        except Exception as exc:
            logger.error("approve_trade: tick data unavailable for %s — %s", pair, exc)
            return self._rejected(
                pair, direction, entry, stop_loss, take_profit, now_utc,
                (f"Tick data unavailable for {pair} — fail-closed",),
            )

        # ── 4. Open positions (fail-closed) ──────────────────────────────────
        try:
            positions: List[BrokerPosition] = await connector.get_positions()
        except Exception as exc:
            logger.error("approve_trade: position data unavailable — %s", exc)
            return self._rejected(
                pair, direction, entry, stop_loss, take_profit, now_utc,
                ("Open position data unavailable — fail-closed",),
            )

        # ── 5. SL validation ─────────────────────────────────────────────────
        sl_reasons = self._validate_sl(direction, entry, stop_loss, spec)
        reasons.extend(sl_reasons)

        # ── 6. TP validation ─────────────────────────────────────────────────
        tp_reasons = self._validate_tp(direction, entry, stop_loss, take_profit)
        reasons.extend(tp_reasons)

        # ── 7. R:R check ─────────────────────────────────────────────────────
        rr_ratio = 0.0
        if not sl_reasons and not tp_reasons:
            rr_ratio = self._compute_rr(entry, stop_loss, take_profit)
            # Use a small epsilon to absorb floating-point rounding at the boundary
            if rr_ratio < settings.RISK_MIN_RR - 1e-9:
                reasons.append(
                    f"R:R {rr_ratio:.2f} is below minimum {settings.RISK_MIN_RR:.2f}"
                )

        # ── 8. Lot size computation ───────────────────────────────────────────
        lot_size, risk_amount = self._compute_lot_and_risk(
            equity    = account.equity,
            risk_pct  = settings.RISK_PER_TRADE_PERCENT,
            entry     = entry,
            stop_loss = stop_loss,
            spec      = spec,
        )
        if lot_size <= 0:
            reasons.append(
                "Lot size calculation produced zero/invalid result — "
                "check SL distance, tick spec, and risk %"
            )

        # ── 9. Risk cap after normalization ──────────────────────────────────
        if lot_size > 0:
            budget = account.equity * (settings.RISK_PER_TRADE_PERCENT / 100.0)
            if risk_amount > budget * 1.02:   # 2 % rounding tolerance
                reasons.append(
                    f"Normalized lot size would risk {risk_amount:.2f} "
                    f"> budget {budget:.2f} — rejected"
                )

        # ── 10. Maximum open trades ───────────────────────────────────────────
        open_count = len(positions)
        if open_count >= settings.MAX_OPEN_TRADES:
            reasons.append(
                f"Maximum open trades reached ({open_count}/{settings.MAX_OPEN_TRADES})"
            )
            flags.append("max_open_trades")

        # ── 11. Spread protection ─────────────────────────────────────────────
        if spread_pips > settings.RISK_MAX_SPREAD_PIPS:
            reasons.append(
                f"Spread {spread_pips:.1f} pips exceeds maximum {settings.RISK_MAX_SPREAD_PIPS:.1f} pips"
            )
            flags.append("spread_protection")

        # ── 12-14. Daily protections ──────────────────────────────────────────
        daily = self._get_or_init_daily(account.balance, today)

        if self._is_daily_loss_exceeded(daily, account.equity):
            reasons.append(
                f"Daily loss limit {settings.MAX_DAILY_LOSS_PERCENT:.1f}% reached — "
                f"trading blocked for the remainder of the trading day"
            )
            flags.append("daily_loss_protection")

        if self._is_daily_profit_reached(daily, account.equity, account.balance):
            reasons.append(
                f"Daily profit target {settings.RISK_MAX_DAILY_PROFIT_PERCENT:.1f}% reached — "
                f"trading paused for the remainder of the trading day"
            )
            flags.append("daily_profit_protection")

        if self._is_drawdown_exceeded(daily, account.equity):
            reasons.append(
                f"Maximum drawdown {settings.RISK_MAX_DRAWDOWN_PERCENT:.1f}% exceeded — "
                f"new trades blocked"
            )
            flags.append("drawdown_protection")

        # ── 15. Consecutive loss protection ───────────────────────────────────
        if daily.consecutive_losses >= settings.RISK_MAX_CONSECUTIVE_LOSSES:
            reasons.append(
                f"Consecutive loss limit {settings.RISK_MAX_CONSECUTIVE_LOSSES} reached "
                f"({daily.consecutive_losses} consecutive losses) — new trades blocked"
            )
            flags.append("consecutive_loss_protection")

        # ── 16. Session protection ────────────────────────────────────────────
        session_reason = self._check_session(dt=now_utc)
        if session_reason:
            reasons.append(session_reason)
            flags.append("session_protection")

        # ── 17. News protection ───────────────────────────────────────────────
        if effective_news is not None:
            try:
                allowed = await effective_news.is_trading_allowed(pair)
                if not allowed:
                    reasons.append(
                        f"High-impact news event affecting {pair} — trading suppressed"
                    )
                    flags.append("news_protection")
            except Exception as exc:
                logger.warning("approve_trade: news filter raised — failing closed: %s", exc)
                if settings.NEWS_FILTER_ENABLED:
                    reasons.append(
                        "News filter unavailable — failing closed (NEWS_FILTER_ENABLED=True)"
                    )
                    flags.append("news_protection")
        elif settings.NEWS_FILTER_ENABLED:
            # News protection required but no filter was injected → fail closed
            reasons.append(
                "News filter is enabled (NEWS_FILTER_ENABLED=True) but no filter "
                "was provided — failing closed"
            )
            flags.append("news_protection")

        # ── 18. Exposure control ──────────────────────────────────────────────
        exposure_reason = self._check_exposure(pair, positions)
        if exposure_reason:
            reasons.append(exposure_reason)
            flags.append("exposure_protection")

        # ── Final decision ────────────────────────────────────────────────────
        approved = len(reasons) == 0 and lot_size > 0

        logger.info(
            "approve_trade: %s %s %s — approved=%s reasons=%d",
            direction.upper(), pair, entry, approved, len(reasons),
        )

        return RiskApproval(
            approved          = approved,
            pair              = pair,
            direction         = direction,
            entry             = entry,
            stop_loss         = stop_loss,
            take_profit       = take_profit,
            lot_size          = lot_size if approved else 0.0,
            risk_amount       = risk_amount if approved else 0.0,
            risk_pct          = settings.RISK_PER_TRADE_PERCENT,
            rr_ratio          = rr_ratio,
            rejection_reasons = tuple(reasons),
            protection_flags  = tuple(flags),
            approved_at       = now_utc,
        )

    # ── IRiskManager.record_closed_trade ────────────────────────────────────

    async def record_closed_trade(self, trade_id: str, pnl: float) -> None:
        """
        Update daily stats after a trade closes.

        Idempotent — the same trade_id is only counted once.
        Initialises daily stats with pnl=0 starting balance if not yet set
        (this path is for trades that closed without a corresponding approval
        in this session — treated as zero-basis for the daily state).
        """
        today = datetime.now(timezone.utc).date()
        if self._daily_stats is None or self._daily_stats.trading_date != today:
            # Stats not initialised yet — use 0 as starting balance placeholder;
            # approve_trade() will reset with the real balance on next call.
            self._daily_stats = DailyStats(
                trading_date     = today,
                starting_balance = 0.0,
            )
        self._daily_stats = self._daily_stats.record_closed_trade(trade_id, pnl)
        logger.info(
            "record_closed_trade: %s pnl=%.2f | daily_pnl=%.2f consecutive_losses=%d",
            trade_id, pnl, self._daily_stats.realized_pnl, self._daily_stats.consecutive_losses,
        )

    # ── IRiskManager.get_protection_state ───────────────────────────────────

    async def get_protection_state(self, connector: IMT5Connector) -> ProtectionState:
        """
        Return a snapshot of all active protection states.

        Fails safely — returns a default ProtectionState on any connector error.
        """
        state = ProtectionState()
        try:
            account   = await connector.get_account_info()
            positions = await connector.get_positions()
        except Exception as exc:
            logger.warning("get_protection_state: connector error — %s", exc)
            return state

        today = datetime.now(timezone.utc).date()
        daily = self._get_or_init_daily(account.balance, today)

        open_count    = len(positions)
        daily_pnl     = daily.realized_pnl
        daily_pnl_pct = (
            daily_pnl / daily.starting_balance * 100.0
            if daily.starting_balance > 0 else 0.0
        )
        drawdown_pct  = (
            (daily.starting_balance - account.equity) / daily.starting_balance * 100.0
            if daily.starting_balance > 0 else 0.0
        )

        state.daily_loss_active       = self._is_daily_loss_exceeded(daily, account.equity)
        state.daily_profit_active     = self._is_daily_profit_reached(daily, account.equity, account.balance)
        state.drawdown_active         = self._is_drawdown_exceeded(daily, account.equity)
        state.consecutive_loss_active = daily.consecutive_losses >= settings.RISK_MAX_CONSECUTIVE_LOSSES
        state.max_open_trades_active  = open_count >= settings.MAX_OPEN_TRADES
        state.session_blocked         = self._check_session() is not None
        state.daily_pnl               = daily_pnl
        state.daily_pnl_pct           = daily_pnl_pct
        state.drawdown_pct            = drawdown_pct
        state.consecutive_losses      = daily.consecutive_losses
        state.open_trades             = open_count
        return state

    # ── IRiskManager legacy stubs ────────────────────────────────────────────

    async def check_trade(
        self,
        pair:            str,
        direction:       str,
        entry:           float,
        stop_loss:       float,
        take_profit:     float,
        account_balance: float,
    ) -> RiskCheckResult:
        """
        Legacy check_trade — delegates to approve_trade logic but requires no
        live connector (no spread / open-position / session checks).

        For full Section 8 protection use approve_trade() instead.
        """
        sl_dist = abs(entry - stop_loss)
        tp_dist = abs(take_profit - entry)
        rr      = tp_dist / sl_dist if sl_dist > 0 else 0.0

        if rr < settings.RISK_MIN_RR:
            return RiskCheckResult(
                approved = False,
                reason   = f"R:R {rr:.2f} below minimum {settings.RISK_MIN_RR:.2f}",
            )

        risk_amount = account_balance * (settings.RISK_PER_TRADE_PERCENT / 100.0)
        return RiskCheckResult(
            approved       = True,
            position_size  = PositionSize(
                lot_size          = settings.DEFAULT_LOT_SIZE,
                risk_amount       = risk_amount,
                pip_value         = 10.0,       # placeholder — use approve_trade() for real value
                stop_loss_pips    = sl_dist / 0.0001,
                risk_reward_ratio = rr,
            ),
        )

    async def compute_position_size(
        self,
        pair:            str,
        entry:           float,
        stop_loss:       float,
        account_balance: float,
        risk_pct:        float,
    ) -> PositionSize:
        """Legacy compute_position_size — no symbol spec available; uses defaults."""
        sl_dist      = abs(entry - stop_loss)
        pip_value    = 10.0                    # placeholder; real value from spec
        sl_pips      = sl_dist / 0.0001
        monetary_risk = account_balance * (risk_pct / 100.0)
        lot_size      = monetary_risk / (sl_pips * pip_value) if sl_pips > 0 else 0.0
        tp_dist       = 0.0                    # TP not provided
        rr            = 0.0
        return PositionSize(
            lot_size          = max(0.01, round(lot_size, 2)),
            risk_amount       = monetary_risk,
            pip_value         = pip_value,
            stop_loss_pips    = sl_pips,
            risk_reward_ratio = rr,
        )

    async def is_daily_loss_exceeded(self, account_balance: float) -> bool:
        """Legacy check using in-memory daily stats."""
        today = datetime.now(timezone.utc).date()
        daily = self._get_or_init_daily(account_balance, today)
        # With no current equity available, use realized PnL only
        realized_loss_pct = (
            (-daily.realized_pnl) / daily.starting_balance * 100.0
            if daily.starting_balance > 0 else 0.0
        )
        return realized_loss_pct >= settings.MAX_DAILY_LOSS_PERCENT

    async def open_trade_count(self) -> int:
        """Legacy open trade count — returns 0 (no connector available here)."""
        return 0

    # ── private factory ──────────────────────────────────────────────────────

    @staticmethod
    def _rejected(
        pair:       str,
        direction:  str,
        entry:      float,
        stop_loss:  float,
        take_profit: float,
        now_utc:    datetime,
        reasons:    Tuple[str, ...],
    ) -> RiskApproval:
        """Create a fail-closed rejection RiskApproval."""
        return RiskApproval(
            approved          = False,
            pair              = pair,
            direction         = direction,
            entry             = entry,
            stop_loss         = stop_loss,
            take_profit       = take_profit,
            lot_size          = 0.0,
            risk_amount       = 0.0,
            risk_pct          = settings.RISK_PER_TRADE_PERCENT,
            rr_ratio          = 0.0,
            rejection_reasons = reasons,
            protection_flags  = (),
            approved_at       = now_utc,
        )
