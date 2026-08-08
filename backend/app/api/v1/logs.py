"""
System Log routes — structured event log with filtering.
Requires authentication.
"""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.schemas import LogEntryOut, PaginatedLogsOut
from app.services.logs_service import list_logs, get_errors
from app.api.v1.auth import get_current_user_id

router = APIRouter()


@router.get("", response_model=PaginatedLogsOut)
async def list_logs_route(
    page:     int          = Query(default=1, ge=1),
    limit:    int          = Query(default=100, ge=1, le=1000),
    level:    str          = Query(default="all", pattern="^(debug|info|warning|error|critical|all)$"),
    module:   str | None   = Query(default=None),
    db:       AsyncSession = Depends(get_db),
    _user_id: str          = Depends(get_current_user_id),
) -> PaginatedLogsOut:
    return await list_logs(db, page=page, limit=limit, level=level, module=module)


@router.get("/errors", response_model=List[LogEntryOut])
async def get_errors_route(
    db:       AsyncSession = Depends(get_db),
    _user_id: str          = Depends(get_current_user_id),
) -> List[LogEntryOut]:
    return await get_errors(db)
