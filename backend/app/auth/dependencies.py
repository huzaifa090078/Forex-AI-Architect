"""
Reusable FastAPI dependencies for authorization and role enforcement.
"""

from fastapi import Depends, HTTPException, status

from app.auth.jwt import get_current_user, CurrentUser
from app.db.models import User


def require_role(*allowed_roles: str):
    """
    Factory that returns a dependency enforcing a minimum role.

    Usage:
        @router.delete("/{id}", dependencies=[Depends(require_role("admin"))])
        async def delete_something(...):
            ...
    """
    async def _check(user: CurrentUser = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not authorized. Required: {allowed_roles}",
            )
        return user
    return _check


# Convenience aliases
RequireAdmin = Depends(require_role("admin"))
RequireViewer = Depends(require_role("admin", "viewer"))
