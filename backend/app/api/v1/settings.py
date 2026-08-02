"""
Bot Settings routes — read and update risk & configuration parameters.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.schemas import BotSettingsOut, BotSettingsUpdate

router = APIRouter()


@router.get("", response_model=BotSettingsOut)
async def get_settings(db: AsyncSession = Depends(get_db)) -> BotSettingsOut:
    """Return the bot's current configuration for the authenticated user."""
    raise NotImplementedError("settings.get — implement in settings service")


@router.patch("", response_model=BotSettingsOut)
async def update_settings(
    payload: BotSettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> BotSettingsOut:
    """
    Partial-update bot configuration.
    Only fields present in the request body are modified.
    Changes take effect on the next scheduler tick.
    """
    raise NotImplementedError("settings.update — implement in settings service")
