"""
AI Signal routes — list, filter, and retrieve trading signals.
Requires authentication.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.schemas import SignalOut, PaginatedSignalsOut
from app.services.signals_service import list_signals, get_active, get_by_id
from app.api.v1.auth import get_current_user_id

router = APIRouter()


@router.get("", response_model=PaginatedSignalsOut)
async def list_signals_route(
    page:     int          = Query(default=1, ge=1),
    limit:    int          = Query(default=50, ge=1, le=500),
    status:   str          = Query(default="all", alias="status"),
    db:       AsyncSession = Depends(get_db),
    _user_id: str          = Depends(get_current_user_id),
) -> PaginatedSignalsOut:
    return await list_signals(db, page=page, limit=limit, status=status)


@router.get("/active", response_model=List[SignalOut])
async def get_active_route(
    db:       AsyncSession = Depends(get_db),
    _user_id: str          = Depends(get_current_user_id),
) -> List[SignalOut]:
    return await get_active(db)


@router.get("/{id}", response_model=SignalOut)
async def get_signal_route(
    id:       str          = Path(...),
    db:       AsyncSession = Depends(get_db),
    _user_id: str          = Depends(get_current_user_id),
) -> SignalOut:
    signal = await get_by_id(db, id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found.")
    return signal
