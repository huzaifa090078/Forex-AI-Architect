"""
Trade Manager — database service layer.

All database CRUD operations for the trades table live here.
The service is intentionally stateless: every method accepts an
AsyncSession injected by the caller so the session lifecycle stays
under caller control.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Trade, User

logger = logging.getLogger(__name__)


class TradeService:
    """Static-method service for trade CRUD and aggregate statistics."""

    # ─── Bot user ────────────────────────────────────────────────────────────

    @staticmethod
    async def ensure_bot_user(db: AsyncSession) -> str:
        """
        Guarantee the system bot user exists in the DB.
        Creates it with a locked (unusable) password if absent.
        Returns the bot user_id.
        """
        from app.core.config import settings

        result = await db.execute(
            select(User.id).where(User.id == settings.TRADE_BOT_USER_ID)
        )
        if result.scalar_one_or_none() is not None:
            return settings.TRADE_BOT_USER_ID

        # Use bcrypt directly to avoid passlib/bcrypt version compatibility issues.
        # This hash is for a random discarded password — the bot user never logs in.
        try:
            import bcrypt as _bcrypt
            _pw_hash = _bcrypt.hashpw(b"LOCKED_BOT_ACCOUNT", _bcrypt.gensalt(4)).decode()
        except Exception:
            # Absolute fallback: SHA-512 crypt format — passlib verify returns False
            _pw_hash = "$6$LOCKED$" + "A" * 86

        bot_user = User(
            id=settings.TRADE_BOT_USER_ID,
            email=settings.TRADE_BOT_EMAIL,
            hashed_password=_pw_hash,
            name="System Bot",
            role="admin",
            is_active=True,
        )
        db.add(bot_user)
        await db.flush()
        logger.info("Created system bot user id=%s", settings.TRADE_BOT_USER_ID)
        return settings.TRADE_BOT_USER_ID

    # ─── Reads ───────────────────────────────────────────────────────────────

    @staticmethod
    async def get_trades(
        db: AsyncSession,
        status_filter: str = "all",
        pair: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Tuple[List[Trade], int]:
        """Return paginated trade records with optional filters."""
        stmt = select(Trade)
        if status_filter != "all":
            stmt = stmt.where(Trade.status == status_filter)
        if pair:
            stmt = stmt.where(Trade.pair == pair.upper())
        stmt = stmt.order_by(Trade.created_at.desc())

        # Total count (without pagination)
        from sqlalchemy import func as sqlfunc
        count_stmt = select(sqlfunc.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar_one() or 0

        offset = (page - 1) * limit
        stmt = stmt.offset(offset).limit(limit)
        rows = (await db.execute(stmt)).scalars().all()
        return list(rows), total

    @staticmethod
    async def get_trade(db: AsyncSession, trade_id: str) -> Optional[Trade]:
        """Fetch a single trade by its UUID."""
        result = await db.execute(select(Trade).where(Trade.id == trade_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_open_trades(db: AsyncSession) -> List[Trade]:
        """Return all trades with status='open'."""
        result = await db.execute(
            select(Trade).where(Trade.status == "open").order_by(Trade.opened_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_open_trades_for_pair(
        db: AsyncSession,
        pair: str,
        direction: Optional[str] = None,
    ) -> List[Trade]:
        """
        Return open trades for the given pair.
        If direction is provided, filter to that direction only
        (used for same-symbol+direction duplicate check).
        """
        conditions = [Trade.status == "open", Trade.pair == pair.upper()]
        if direction is not None:
            conditions.append(Trade.direction == direction.lower())
        result = await db.execute(select(Trade).where(and_(*conditions)))
        return list(result.scalars().all())

    # ─── Writes ──────────────────────────────────────────────────────────────

    @staticmethod
    async def create_trade(db: AsyncSession, data: Dict[str, Any]) -> Trade:
        """Insert a new trade record and return it."""
        if "pair" in data and data["pair"]:
            data["pair"] = data["pair"].upper()
        trade = Trade(**data)
        db.add(trade)
        await db.flush()
        await db.refresh(trade)
        return trade

    @staticmethod
    async def update_trade(
        db: AsyncSession,
        trade_id: str,
        **updates: Any,
    ) -> Optional[Trade]:
        """Update arbitrary fields on a trade record."""
        trade = await TradeService.get_trade(db, trade_id)
        if trade is None:
            return None
        for key, value in updates.items():
            if hasattr(trade, key):
                setattr(trade, key, value)
        await db.flush()
        await db.refresh(trade)
        return trade

    @staticmethod
    async def mark_trade_closed(
        db: AsyncSession,
        trade_id: str,
        pnl: Optional[float],
        close_reason: str,
        close_price: Optional[float],
        closed_at: Optional[datetime] = None,
    ) -> Optional[Trade]:
        """Mark a trade as closed and record exit details."""
        return await TradeService.update_trade(
            db,
            trade_id,
            status="closed",
            pnl=pnl,
            close_reason=close_reason,
            close_price=close_price,
            closed_at=closed_at or datetime.now(timezone.utc),
        )

    @staticmethod
    async def delete_trade(db: AsyncSession, trade_id: str) -> bool:
        """
        Delete a trade record.
        Only safe for trades in 'open' status with no broker_order_id
        (i.e. never sent to the broker) — callers must enforce this.
        """
        trade = await TradeService.get_trade(db, trade_id)
        if trade is None:
            return False
        await db.delete(trade)
        await db.flush()
        return True

    # ─── Aggregate statistics ────────────────────────────────────────────────

    @staticmethod
    async def get_stats(db: AsyncSession) -> Dict[str, Any]:
        """
        Compute aggregate performance statistics across all closed trades.
        Fetches raw rows and computes in Python so the logic is transparent
        and testable without complex SQL expressions.
        """
        result = await db.execute(
            select(Trade.pnl, Trade.risk_reward_ratio)
            .where(Trade.status == "closed")
            .order_by(Trade.closed_at.asc())
        )
        rows = result.all()

        if not rows:
            return {
                "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "win_rate": 0.0, "total_pnl": 0.0, "avg_win": 0.0,
                "avg_loss": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0,
                "avg_rr": 0.0,
            }

        pnls = [float(r.pnl or 0) for r in rows]
        rrs  = [float(r.risk_reward_ratio) for r in rows if r.risk_reward_ratio is not None]

        wins   = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total      = len(pnls)
        total_pnl  = sum(pnls)
        win_rate   = len(wins) / total if total else 0.0
        avg_win    = sum(wins) / len(wins) if wins else 0.0
        avg_loss   = sum(losses) / len(losses) if losses else 0.0
        gross_loss = sum(losses)
        profit_factor = (sum(wins) / abs(gross_loss)) if gross_loss < 0 else 0.0
        avg_rr     = sum(rrs) / len(rrs) if rrs else 0.0

        # Running peak-to-trough max drawdown
        max_dd  = 0.0
        running = 0.0
        peak    = 0.0
        for p in pnls:
            running += p
            if running > peak:
                peak = running
            dd = peak - running
            if dd > max_dd:
                max_dd = dd

        return {
            "total_trades":   total,
            "winning_trades": len(wins),
            "losing_trades":  len(losses),
            "win_rate":       round(win_rate, 4),
            "total_pnl":      round(total_pnl, 2),
            "avg_win":        round(avg_win, 2),
            "avg_loss":       round(avg_loss, 2),
            "profit_factor":  round(profit_factor, 4),
            "max_drawdown":   round(max_dd, 2),
            "avg_rr":         round(avg_rr, 4),
        }
