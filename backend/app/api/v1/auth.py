"""
Authentication routes — login, register, token refresh, and current-user profile.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.schemas import (
    LoginInput,
    RegisterInput,
    RefreshInput,
    TokenPair,
    UserOut,
)

router = APIRouter()


@router.post("/login", response_model=TokenPair, status_code=status.HTTP_200_OK)
async def login(payload: LoginInput, db: AsyncSession = Depends(get_db)) -> TokenPair:
    """
    Authenticate a user and return a JWT access + refresh token pair.
    Raises 401 if credentials are invalid.
    """
    # Implementation: validate credentials, call auth service, return tokens.
    raise NotImplementedError("auth.login — implement in auth service layer")


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterInput, db: AsyncSession = Depends(get_db)) -> UserOut:
    """
    Register a new user account.
    Raises 409 if the email is already taken.
    """
    raise NotImplementedError("auth.register — implement in auth service layer")


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshInput, db: AsyncSession = Depends(get_db)) -> TokenPair:
    """
    Exchange a valid refresh token for a new access + refresh token pair.
    """
    raise NotImplementedError("auth.refresh — implement in auth service layer")


@router.get("/me", response_model=UserOut)
async def get_me(db: AsyncSession = Depends(get_db)) -> UserOut:
    """
    Return the authenticated user's profile.
    Requires a valid Bearer token in the Authorization header.
    """
    raise NotImplementedError("auth.me — implement bearer token dependency")
