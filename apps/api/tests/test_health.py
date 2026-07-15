from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from pytest import MonkeyPatch

from jacaranda_api.config import get_settings
from jacaranda_api.main import app, create_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def configured_environment(monkeypatch: MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@postgres:5432/jacaranda")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_health_returns_service_status() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "jacaranda-api",
        "environment": "development",
    }


def test_backend_urls_are_required(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("REDIS_URL", "")
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()


@pytest.mark.anyio
async def test_openapi_docs_are_available_in_development() -> None:
    transport = ASGITransport(app=create_app("development"))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        docs_response = await client.get("/docs")
        redoc_response = await client.get("/redoc")

    assert docs_response.status_code == 200
    assert redoc_response.status_code == 200


@pytest.mark.anyio
async def test_openapi_docs_are_disabled_outside_development() -> None:
    transport = ASGITransport(app=create_app("production"))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        docs_response = await client.get("/docs")
        redoc_response = await client.get("/redoc")

    assert docs_response.status_code == 404
    assert redoc_response.status_code == 404
