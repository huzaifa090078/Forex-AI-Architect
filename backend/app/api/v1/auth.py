"""
Authentication routes — login, register, token refresh, and current-user profile.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.schemas import LoginInput, RegisterInput, RefreshInput, TokenPair, UserOut
from app.services import auth_service

router   = APIRouter()
_bearer  = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Dependency — get current user from Bearer token
# ---------------------------------------------------------------------------

async def get_current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db:    AsyncSession                         = Depends(get_db),
) -> str:
    from app.core.config import settings as _cfg
    # Dev bypass — no login required until bot goes live
    if _cfg.APP_ENV == "development":
        return "dev-operator"
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token.")
    user_id = auth_service.decode_access_token(creds.credentials)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")
    return user_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenPair, status_code=status.HTTP_200_OK)
async def login(payload: LoginInput, db: AsyncSession = Depends(get_db)) -> TokenPair:
    user = await auth_service.authenticate(db, payload.email, payload.password)
    return TokenPair(
        access_token  = auth_service.create_access_token(user.id),
        refresh_token = auth_service.create_refresh_token(user.id),
        token_type    = "bearer",
        expires_in    = 3600,
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterInput, db: AsyncSession = Depends(get_db)) -> UserOut:
    user = await auth_service.register_user(db, payload.email, payload.password, payload.name)
    return UserOut(id=user.id, email=user.email, name=user.name, role=user.role, created_at=user.created_at)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshInput, db: AsyncSession = Depends(get_db)) -> TokenPair:
    user_id = auth_service.decode_refresh_token(payload.refresh_token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token.")
    user = await auth_service.get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive.")
    return TokenPair(
        access_token  = auth_service.create_access_token(user.id),
        refresh_token = auth_service.create_refresh_token(user.id),
        token_type    = "bearer",
        expires_in    = 3600,
    )


@router.get("/me", response_model=UserOut)
async def get_me(
    user_id: str         = Depends(get_current_user_id),
    db:      AsyncSession = Depends(get_db),
) -> UserOut:
    user = await auth_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return UserOut(id=user.id, email=user.email, name=user.name, role=user.role, created_at=user.created_at)
