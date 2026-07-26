from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from jacaranda_api.auth.security import SESSION_COOKIE, digest, role_allows
from jacaranda_api.db.models import Session as DbSession
from jacaranda_api.db.models import User, utc_now
from jacaranda_api.routers.deps import get_session


async def get_current_user(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="not signed in")
    record = await session.get(DbSession, digest(token))
    if record is None:
        raise HTTPException(status_code=401, detail="session expired")
    expires = record.expires_at
    now = utc_now()
    if expires.tzinfo is None:
        # SQLite loses timezone info; both timestamps are UTC by construction.
        now = now.replace(tzinfo=None)
    if expires < now:
        raise HTTPException(status_code=401, detail="session expired")
    user = await session.get(User, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="account is not active")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(required: str) -> Callable[..., Coroutine[Any, Any, User]]:
    async def dependency(user: CurrentUser) -> User:
        if not role_allows(user.role, required):
            raise HTTPException(status_code=403, detail=f"requires the {required} role")
        return user

    return dependency
