import os
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from jacaranda_api.config import get_settings


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


def create_app(app_env: str | None = None) -> FastAPI:
    environment = app_env or os.getenv("APP_ENV", "development")
    docs_enabled = environment == "development"
    api = FastAPI(
        title="Jacaranda Research OS API",
        version="0.1.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
    )
    api.add_api_route(
        "/health",
        health,
        response_model=HealthResponse,
        tags=["system"],
        methods=["GET"],
    )
    return api


app = create_app()
