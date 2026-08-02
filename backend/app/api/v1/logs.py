"""
System Log routes — structured event log with filtering.
"""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.schemas import LogEntryOut, PaginatedLogsOut

router = APIRouter()


@router.get("", response_model=PaginatedLogsOut)
async def list_logs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=1000),
    level: str = Query(default="all", regex="^(debug|info|warning|error|critical|all)$"),
    module: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> PaginatedLogsOut:
    """Return paginated system event log with optional level and module filters."""
    raise NotImplementedError("logs.list — implement in log service")


@router.get("/errors", response_model=List[LogEntryOut])
async def get_errors(db: AsyncSession = Depends(get_db)) -> List[LogEntryOut]:
    """Return the 100 most recent error and critical log entries."""
    raise NotImplementedError("logs.errors — implement in log service")
