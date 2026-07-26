from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from jacaranda_api.config import get_settings
from jacaranda_api.routers import artifacts, packages, projects, runs, uploads
from jacaranda_api.routers.deps import ArqJobQueue

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    environment: str


def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="jacaranda-api",
        environment=settings.app_env,
    )


@asynccontextmanager
async def lifespan(api: FastAPI) -> AsyncIterator[None]:
    """Attach persistence and the job queue. /health stays a pure liveness
    check: failures here are logged and the affected endpoints answer 503."""
    engine = None
    try:
        from jacaranda_api.db.engine import create_engine, create_session_factory

        settings = get_settings()
        engine = create_engine(settings.database_url)
        api.state.session_factory = create_session_factory(engine)
    except Exception:
        logger.exception("database initialisation failed; data endpoints will return 503")
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        api.state.job_queue = ArqJobQueue(pool)
    except Exception:
        logger.exception("job queue initialisation failed; run creation will return 503")
    yield
    if engine is not None:
        await engine.dispose()


def create_app(app_env: str | None = None) -> FastAPI:
    environment = app_env or os.getenv("APP_ENV", "development")
    docs_enabled = environment == "development"
    api = FastAPI(
        title="Jacaranda Research OS API",
        version="0.1.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        lifespan=lifespan,
    )
    api.add_api_route(
        "/health",
        health,
        response_model=HealthResponse,
        tags=["system"],
        methods=["GET"],
    )
    api.include_router(projects.router)
    api.include_router(runs.router)
    api.include_router(uploads.router)
    api.include_router(packages.router)
    api.include_router(artifacts.router)
    return api


app = create_app()
