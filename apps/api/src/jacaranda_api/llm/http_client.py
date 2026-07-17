from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import SecretStr

from jacaranda_api.llm.errors import (
    FreeOnlyModelPolicyError,
    OpenRouterTransportFailure,
    TransportFailureKind,
)
from jacaranda_api.llm.models import JsonObject, JsonValue

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True, slots=True)
class OpenRouterHTTPResponse:
    status_code: int
    body: JsonValue


class OpenRouterHTTPClient(Protocol):
    async def create_chat_completion(
        self,
        *,
        api_key: SecretStr,
        payload: JsonObject,
    ) -> OpenRouterHTTPResponse: ...


class HttpxOpenRouterHTTPClient:
    """Actual OpenRouter HTTP boundary; callers own the injected AsyncClient lifecycle."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str = OPENROUTER_BASE_URL,
        timeout_seconds: float = 60.0,
    ) -> None:
        if base_url.rstrip("/") != OPENROUTER_BASE_URL:
            raise FreeOnlyModelPolicyError("OPENROUTER_BASE_URL")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def create_chat_completion(
        self,
        *,
        api_key: SecretStr,
        payload: JsonObject,
    ) -> OpenRouterHTTPResponse:
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException:
            raise OpenRouterTransportFailure(TransportFailureKind.TIMEOUT) from None
        except httpx.HTTPError:
            raise OpenRouterTransportFailure(TransportFailureKind.UNAVAILABLE) from None
        try:
            body = response.json()
        except ValueError:
            raise OpenRouterTransportFailure(TransportFailureKind.MALFORMED_RESPONSE) from None
        return OpenRouterHTTPResponse(status_code=response.status_code, body=body)
