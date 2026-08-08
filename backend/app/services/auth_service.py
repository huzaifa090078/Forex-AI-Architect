"""
Auth Service — JWT-based authentication.
Handles user creation, credential verification, and token issuance.

Security:
  - Passwords hashed with bcrypt.
  - Access tokens expire in 60 min (configurable via APP_SECRET_KEY).
  - Refresh tokens expire in 7 days.
  - NEVER returns passwords or raw tokens outside of login/refresh.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import User

logger = logging.getLogger(__name__)

_ALGORITHM     = "HS256"
_ACCESS_EXP    = timedelta(minutes=60)
_REFRESH_EXP   = timedelta(days=7)


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _make_token(sub: str, kind: str, exp: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub":  sub,
        "kind": kind,
        "iat":  now,
        "exp":  now + exp,
        "jti":  str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=_ALGORITHM)


def create_access_token(user_id: str) -> str:
    return _make_token(user_id, "access", _ACCESS_EXP)


def create_refresh_token(user_id: str) -> str:
    return _make_token(user_id, "refresh", _REFRESH_EXP)


def decode_access_token(token: str) -> Optional[str]:
    """Decode and validate an access token. Returns user_id or None."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[_ALGORITHM])
        if payload.get("kind") != "access":
            return None
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def decode_refresh_token(token: str) -> Optional[str]:
    """Decode and validate a refresh token. Returns user_id or None."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[_ALGORITHM])
        if payload.get("kind") != "refresh":
            return None
        return payload.get("sub")
    except jwt.InvalidTokenError:
        return None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Service operations
# ---------------------------------------------------------------------------

async def register_user(db: AsyncSession, email: str, password: str, name: str) -> User:
    existing = await get_user_by_email(db, email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    user = User(
        email           = email.lower().strip(),
        hashed_password = hash_password(password),
        name            = name.strip(),
        role            = "viewer",
        is_active       = True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("auth: registered new user %s", user.id)
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    user = await get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled.",
        )
    return user
