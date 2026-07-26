from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jacaranda_api.auth.deps import CurrentUser, require_role
from jacaranda_api.auth.security import (
    SESSION_COOKIE,
    SESSION_TTL,
    digest,
    hash_password,
    new_invite_code,
    new_session_token,
    verify_password,
)
from jacaranda_api.db.models import Invite, User, utc_now
from jacaranda_api.db.models import Session as DbSession
from jacaranda_api.routers.deps import get_session

router = APIRouter(tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invite_code: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: str


class InviteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(default="member", pattern="^(member|reviewer|admin)$")


def _set_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=bool(getattr(request.app.state, "secure_cookies", False)),
        path="/",
    )


async def _start_session(
    request: Request, session: AsyncSession, response: Response, user: User
) -> None:
    token = new_session_token()
    session.add(
        DbSession(id=digest(token), user_id=user.id, expires_at=utc_now() + SESSION_TTL)
    )
    _set_cookie(request, response, token)


@router.post("/auth/register", response_model=UserOut, status_code=201)
async def register(
    payload: RegisterIn, request: Request, response: Response, session: SessionDep
) -> User:
    invite = await session.scalar(
        select(Invite).where(Invite.code_hash == digest(payload.invite_code))
    )
    now = utc_now()
    if invite is None or invite.used_by is not None:
        raise HTTPException(status_code=403, detail="invite code is invalid or already used")
    if invite.expires_at is not None:
        expires = invite.expires_at
        reference = now.replace(tzinfo=None) if expires.tzinfo is None else now
        if expires < reference:
            raise HTTPException(status_code=403, detail="invite code has expired")
    existing = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        raise HTTPException(status_code=409, detail="an account with this email already exists")
    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=invite.role,
    )
    session.add(user)
    await session.flush()
    invite.used_by = user.id
    await _start_session(request, session, response, user)
    return user


@router.post("/auth/login", response_model=UserOut)
async def login(
    payload: LoginIn, request: Request, response: Response, session: SessionDep
) -> User:
    user = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="account is not active")
    await _start_session(request, session, response, user)
    return user


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, response: Response, session: SessionDep) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        record = await session.get(DbSession, digest(token))
        if record is not None:
            await session.delete(record)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/auth/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user


@router.post(
    "/admin/invites",
    status_code=201,
    dependencies=[Depends(require_role("admin"))],
)
async def create_invite(
    payload: InviteCreate, session: SessionDep, user: CurrentUser
) -> dict[str, str]:
    """Returns the invite code once; only its hash is stored."""
    code = new_invite_code()
    session.add(Invite(code_hash=digest(code), role=payload.role, created_by=user.id))
    await session.flush()
    return {"invite_code": code, "role": payload.role}


@router.get("/admin/invites", dependencies=[Depends(require_role("admin"))])
async def list_invites(session: SessionDep) -> list[dict[str, object]]:
    invites = await session.scalars(select(Invite).order_by(Invite.created_at.desc()))
    return [
        {
            "id": item.id,
            "role": item.role,
            "used": item.used_by is not None,
            "created_at": item.created_at.isoformat(),
        }
        for item in invites
    ]
