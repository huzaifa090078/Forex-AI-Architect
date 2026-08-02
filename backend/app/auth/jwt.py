"""
JWT bearer token dependency for FastAPI route protection.
Inject `CurrentUser` into any route that requires authentication.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.db.models import User

_bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Decode the Bearer token, validate it, and return the authenticated User.
    Raises HTTP 401 on any token or user lookup failure.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(credentials.credentials)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        token_type: str = payload.get("type")
        if token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Implementation: look up user in DB
    # user = await db.get(User, user_id)
    # if user is None or not user.is_active:
    #     raise credentials_exception
    # return user
    raise NotImplementedError("Implement database lookup for user_id in JWT sub claim")


# Type alias used in route signatures:  user: CurrentUser = Depends(get_current_user)
CurrentUser = User
