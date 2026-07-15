from functools import lru_cache
from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server-only application settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: Annotated[str, Field(min_length=1)]
    redis_url: Annotated[str, Field(min_length=1)]


@lru_cache
def get_settings() -> Settings:
    # pydantic-settings resolves required values from the environment at runtime.
    return Settings()  # type: ignore[call-arg]
