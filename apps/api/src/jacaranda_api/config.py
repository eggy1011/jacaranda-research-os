from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server-only application settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: Annotated[str, Field(min_length=1)]
    redis_url: Annotated[str, Field(min_length=1)]
    # Root for run artifacts and uploads; a shared volume in Docker Compose.
    data_dir: str = "data"
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openrouter/free"
    # D-008: ordered candidate list (comma-separated), free models first; paid
    # candidates are honoured only when allow_paid_models is explicitly true.
    openrouter_models: str = ""
    allow_paid_models: bool = False
    llm_max_attempts: Annotated[int, Field(ge=1, le=3)] = 3
    fmp_api_key: SecretStr | None = None
    finnhub_api_key: SecretStr | None = None
    sec_user_agent: str | None = None


@lru_cache
def get_settings() -> Settings:
    # pydantic-settings resolves required values from the environment at runtime.
    return Settings()  # type: ignore[call-arg]
