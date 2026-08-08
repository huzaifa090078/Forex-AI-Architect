"""
Logs Service — read SystemLog records.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SystemLog
from app.db.schemas import LogEntryOut, PaginatedLogsOut

logger = logging.getLogger(__name__)


def _to_out(log: SystemLog) -> LogEntryOut:
    return LogEntryOut(
        id         = log.id,
        level      = log.level,
        module     = log.module,
        message    = log.message,
        metadata   = log.log_metadata,
        created_at = log.created_at,
    )


async def list_logs(
    db:     AsyncSession,
    page:   int = 1,
    limit:  int = 100,
    level:  str = "all",
    module: Optional[str] = None,
) -> PaginatedLogsOut:
    q = select(SystemLog)

    if level != "all":
        q = q.where(SystemLog.level == level)
    if module:
        q = q.where(SystemLog.module.ilike(f"%{module}%"))

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one() or 0

    q = q.order_by(SystemLog.created_at.desc())
    q = q.offset((page - 1) * limit).limit(limit)
    rows = (await db.execute(q)).scalars().all()

    return PaginatedLogsOut(
        items = [_to_out(r) for r in rows],
        total = total,
        page  = page,
        limit = limit,
    )


async def get_errors(db: AsyncSession) -> list[LogEntryOut]:
    q = (
        select(SystemLog)
        .where(SystemLog.level.in_(["error", "critical"]))
        .order_by(SystemLog.created_at.desc())
        .limit(100)
    )
    rows = (await db.execute(q)).scalars().all()
    return [_to_out(r) for r in rows]
