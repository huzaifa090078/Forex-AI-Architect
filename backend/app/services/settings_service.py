"""
Settings Service — read and update BotSettings for the system bot user.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotSettings, User
from app.db.schemas import BotSettingsOut

logger = logging.getLogger(__name__)

_BOT_USER_EMAIL = "bot@nexus-ai.internal"


async def _get_bot_user_id(db: AsyncSession) -> Optional[str]:
    result = await db.execute(select(User.id).where(User.email == _BOT_USER_EMAIL))
    row = result.scalar_one_or_none()
    return row


async def _get_or_create_settings(db: AsyncSession) -> BotSettings:
    user_id = await _get_bot_user_id(db)
    if not user_id:
        return _default_settings_obj()

    result = await db.execute(
        select(BotSettings).where(BotSettings.user_id == user_id)
    )
    settings_obj = result.scalar_one_or_none()
    if settings_obj is None:
        settings_obj = BotSettings(
            user_id          = user_id,
            risk_per_trade   = 1.0,
            max_open_trades  = 5,
            max_daily_loss   = 5.0,
            allowed_pairs    = [],
            trading_enabled  = False,
            news_filter_enabled = True,
            min_confidence   = 0.75,
            default_lot_size = 0.01,
        )
        db.add(settings_obj)
        await db.commit()
        await db.refresh(settings_obj)
    return settings_obj


class _FakeSettings:
    """In-memory default settings when no bot user exists yet.
    Uses plain Python object — no SQLAlchemy state needed."""
    def __init__(self) -> None:
        self.risk_per_trade    = 1.0
        self.max_open_trades   = 5
        self.max_daily_loss    = 5.0
        self.allowed_pairs: list = []
        self.trading_enabled   = False
        self.news_filter_enabled = True
        self.mt5_account       = None
        self.mt5_server        = None
        self.min_confidence    = 0.75
        self.default_lot_size  = 0.01


def _default_settings_obj() -> _FakeSettings:
    """Return a plain default when no bot user exists yet."""
    return _FakeSettings()


def _to_out(s, mt5_connected: bool = False) -> BotSettingsOut:
    return BotSettingsOut(
        risk_per_trade      = s.risk_per_trade,
        max_open_trades     = s.max_open_trades,
        max_daily_loss      = s.max_daily_loss,
        allowed_pairs       = list(s.allowed_pairs or []),
        trading_enabled     = s.trading_enabled,
        news_filter_enabled = s.news_filter_enabled,
        mt5_connected       = mt5_connected,
        mt5_account         = s.mt5_account,
        mt5_server          = s.mt5_server,
        min_confidence      = s.min_confidence,
        default_lot_size    = s.default_lot_size,
    )


async def get_settings(db: AsyncSession) -> BotSettingsOut:
    s = await _get_or_create_settings(db)
    return _to_out(s)


async def update_settings(db: AsyncSession, updates: Dict[str, Any]) -> BotSettingsOut:
    s = await _get_or_create_settings(db)

    # If no bot user exists, `s` is a transient object — we cannot commit it.
    # Apply updates in-memory only and return the merged defaults.
    user_id = await _get_bot_user_id(db)
    if not user_id:
        allowed_fields = {
            "risk_per_trade", "max_open_trades", "max_daily_loss",
            "allowed_pairs", "trading_enabled", "news_filter_enabled",
            "mt5_account", "mt5_server", "min_confidence", "default_lot_size",
        }
        for field, value in updates.items():
            if field in allowed_fields and value is not None:
                setattr(s, field, value)
        logger.info("settings: no bot user — update applied in-memory only")
        return _to_out(s)

    allowed_fields = {
        "risk_per_trade", "max_open_trades", "max_daily_loss",
        "allowed_pairs", "trading_enabled", "news_filter_enabled",
        "mt5_account", "mt5_server", "min_confidence", "default_lot_size",
    }
    for field, value in updates.items():
        if field in allowed_fields and value is not None:
            setattr(s, field, value)

    await db.commit()
    await db.refresh(s)
    logger.info("settings: updated — %s", list(updates.keys()))
    return _to_out(s)
