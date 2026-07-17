from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from jacaranda_api.llm.errors import (
    FreeOnlyModelPolicyError,
    OpenRouterTransportFailure,
    TransportFailureKind,
)
from jacaranda_api.llm.http_client import (
    OPENROUTER_BASE_URL,
    HttpxOpenRouterHTTPClient,
)


@pytest.mark.anyio
async def test_httpx_boundary_sends_secret_only_in_authorization_header() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"model": "free/model", "choices": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        boundary = HttpxOpenRouterHTTPClient(client)
        response = await boundary.create_chat_completion(
            api_key=SecretStr("fixture-key"),
            payload={"model": "openrouter/free"},
        )

    assert captured == {
        "url": f"{OPENROUTER_BASE_URL}/chat/completions",
        "authorization": "Bearer fixture-key",
        "body": {"model": "openrouter/free"},
    }
    assert response.status_code == 200


def test_http_boundary_rejects_unapproved_endpoint_and_timeout() -> None:
    client = httpx.AsyncClient()
    try:
        with pytest.raises(FreeOnlyModelPolicyError):
            HttpxOpenRouterHTTPClient(client, base_url="https://example.invalid/api/v1")
        with pytest.raises(ValueError, match="positive"):
            HttpxOpenRouterHTTPClient(client, timeout_seconds=0)
    finally:
        import asyncio

        asyncio.run(client.aclose())


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("exception", "kind"),
    [
        (httpx.ReadTimeout("timeout"), TransportFailureKind.TIMEOUT),
        (httpx.ConnectError("offline"), TransportFailureKind.UNAVAILABLE),
    ],
)
async def test_http_boundary_sanitises_transport_failures(
    exception: Exception,
    kind: TransportFailureKind,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise exception

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        boundary = HttpxOpenRouterHTTPClient(client)
        with pytest.raises(OpenRouterTransportFailure) as caught:
            await boundary.create_chat_completion(
                api_key=SecretStr("fixture-key"),
                payload={"model": "openrouter/free"},
            )

    assert caught.value.kind is kind
    assert "fixture-key" not in str(caught.value)


@pytest.mark.anyio
async def test_http_boundary_rejects_non_json_response() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        boundary = HttpxOpenRouterHTTPClient(client)
        with pytest.raises(OpenRouterTransportFailure) as caught:
            await boundary.create_chat_completion(
                api_key=SecretStr("fixture-key"),
                payload={"model": "openrouter/free"},
            )

    assert caught.value.kind is TransportFailureKind.MALFORMED_RESPONSE
