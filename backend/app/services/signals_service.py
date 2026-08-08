"""
Signals Service — read Signal records from the DB.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Signal
from app.db.schemas import PaginatedSignalsOut, SignalOut

logger = logging.getLogger(__name__)


def _to_out(s: Signal) -> SignalOut:
    return SignalOut(
        id                = s.id,
        pair              = s.pair,
        direction         = s.direction,
        confidence        = s.confidence,
        entry_zone_low    = s.entry_zone_low,
        entry_zone_high   = s.entry_zone_high,
        stop_loss         = s.stop_loss,
        take_profit       = s.take_profit,
        risk_reward_ratio = s.risk_reward_ratio,
        smc_pattern       = s.smc_pattern,
        indicators        = list(s.indicators or []),
        status            = s.status,
        created_at        = s.created_at,
        expires_at        = s.expires_at,
    )


async def list_signals(
    db:     AsyncSession,
    page:   int = 1,
    limit:  int = 50,
    status: str = "all",
) -> PaginatedSignalsOut:
    q = select(Signal)
    if status != "all":
        q = q.where(Signal.status == status)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one() or 0

    q = q.order_by(Signal.created_at.desc()).offset((page - 1) * limit).limit(limit)
    rows = (await db.execute(q)).scalars().all()

    return PaginatedSignalsOut(
        items = [_to_out(r) for r in rows],
        total = total,
        page  = page,
        limit = limit,
    )


async def get_active(db: AsyncSession) -> List[SignalOut]:
    q = (
        select(Signal)
        .where(Signal.status == "pending")
        .order_by(Signal.created_at.desc())
        .limit(20)
    )
    rows = (await db.execute(q)).scalars().all()
    return [_to_out(r) for r in rows]


async def get_by_id(db: AsyncSession, signal_id: str) -> Optional[SignalOut]:
    result = await db.execute(select(Signal).where(Signal.id == signal_id))
    s = result.scalar_one_or_none()
    return _to_out(s) if s else None
