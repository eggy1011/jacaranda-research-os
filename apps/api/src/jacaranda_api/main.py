from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from jacaranda_api.config import get_settings


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    environment: str


app = FastAPI(
    title="Jacaranda Research OS API",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="jacaranda-api",
        environment=settings.app_env,
    )
