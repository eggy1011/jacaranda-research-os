from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jacaranda_api.auth.security import digest, new_invite_code
from jacaranda_api.db.models import Invite


async def seed_invite(db: async_sessionmaker[AsyncSession], role: str) -> str:
    code = new_invite_code()
    async with db() as session:
        session.add(Invite(code_hash=digest(code), role=role))
        await session.commit()
    return code


async def sign_in(
    http: httpx.AsyncClient,
    db: async_sessionmaker[AsyncSession],
    *,
    role: str = "admin",
    email: str | None = None,
) -> None:
    """Register a fresh user via a seeded invite; the session cookie sticks to
    the client's cookie jar for subsequent requests."""
    code = await seed_invite(db, role)
    response = await http.post(
        "/auth/register",
        json={
            "invite_code": code,
            "email": email or f"{role}@example.com",
            "password": "correct-horse-battery",
        },
    )
    assert response.status_code == 201, response.text
