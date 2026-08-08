"""
Bot Settings routes — read and update risk & configuration parameters.
Requires authentication.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.schemas import BotSettingsOut, BotSettingsUpdate
from app.services.settings_service import get_settings, update_settings
from app.api.v1.auth import get_current_user_id

router = APIRouter()


@router.get("", response_model=BotSettingsOut)
async def get_settings_route(
    db:       AsyncSession = Depends(get_db),
    _user_id: str          = Depends(get_current_user_id),
) -> BotSettingsOut:
    return await get_settings(db)


@router.patch("", response_model=BotSettingsOut)
async def update_settings_route(
    payload:  BotSettingsUpdate,
    db:       AsyncSession = Depends(get_db),
    _user_id: str          = Depends(get_current_user_id),
) -> BotSettingsOut:
    updates = payload.model_dump(exclude_none=True)
    return await update_settings(db, updates)
