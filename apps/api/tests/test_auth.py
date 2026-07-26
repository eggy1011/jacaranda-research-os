from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from auth_helpers import seed_invite, sign_in
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jacaranda_api.config import get_settings
from jacaranda_api.db.engine import create_engine, create_session_factory
from jacaranda_api.db.models import Base
from jacaranda_api.main import create_app


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


@pytest.fixture
async def client(
    db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///ignored.db")
    monkeypatch.setenv("REDIS_URL", "redis://ignored")
    get_settings.cache_clear()
    app = create_app("test")
    app.state.session_factory = db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_everything_requires_sign_in(client: httpx.AsyncClient) -> None:
    assert (await client.get("/projects")).status_code == 401
    assert (await client.get("/auth/me")).status_code == 401
    assert (await client.get("/health")).status_code == 200


@pytest.mark.anyio
async def test_register_login_logout_flow(
    client: httpx.AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    code = await seed_invite(db, "member")
    registered = await client.post(
        "/auth/register",
        json={
            "invite_code": code,
            "email": "Member@Example.COM",
            "password": "correct-horse-battery",
        },
    )
    assert registered.status_code == 201
    assert registered.json() == {
        "id": registered.json()["id"],
        "email": "member@example.com",
        "role": "member",
    }
    me = await client.get("/auth/me")
    assert me.status_code == 200

    # the invite is single-use
    reused = await client.post(
        "/auth/register",
        json={
            "invite_code": code,
            "email": "second@example.com",
            "password": "correct-horse-battery",
        },
    )
    assert reused.status_code == 403

    assert (await client.post("/auth/logout")).status_code == 204
    assert (await client.get("/auth/me")).status_code == 401

    wrong = await client.post(
        "/auth/login", json={"email": "member@example.com", "password": "nope-nope-nope"}
    )
    assert wrong.status_code == 401
    good = await client.post(
        "/auth/login",
        json={"email": "member@example.com", "password": "correct-horse-battery"},
    )
    assert good.status_code == 200
    assert (await client.get("/auth/me")).status_code == 200


@pytest.mark.anyio
async def test_bad_invite_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/auth/register",
        json={
            "invite_code": "not-a-real-code",
            "email": "x@example.com",
            "password": "correct-horse-battery",
        },
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_member_cannot_approve_or_mint_invites(
    client: httpx.AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    await sign_in(client, db, role="member", email="m1@example.com")
    assert (await client.post("/packages/whatever/verify")).status_code == 403
    assert (await client.post("/admin/invites", json={"role": "member"})).status_code == 403


@pytest.mark.anyio
async def test_admin_mints_invites_and_reviewer_can_transition(
    client: httpx.AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    await sign_in(client, db, role="admin", email="a1@example.com")
    minted = await client.post("/admin/invites", json={"role": "reviewer"})
    assert minted.status_code == 201
    invite_code = minted.json()["invite_code"]
    listed = await client.get("/admin/invites")
    assert listed.status_code == 200
    assert any(item["used"] is False for item in listed.json())

    await client.post("/auth/logout")
    registered = await client.post(
        "/auth/register",
        json={
            "invite_code": invite_code,
            "email": "reviewer@example.com",
            "password": "correct-horse-battery",
        },
    )
    assert registered.status_code == 201
    assert registered.json()["role"] == "reviewer"
    # reviewer reaches the transition endpoint (404: no such package, not 403)
    assert (await client.post("/packages/whatever/verify")).status_code == 404
