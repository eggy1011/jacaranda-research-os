from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import cast

import pytest
from pydantic import SecretStr

from jacaranda_api.llm.catalog import PromptCatalogReader, PromptTask
from jacaranda_api.llm.contracts import LLMProvider
from jacaranda_api.llm.errors import (
    FreeOnlyModelPolicyError,
    InputSchemaMismatchError,
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMContentFilteredError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    MalformedUpstreamResponseError,
    NonRetryableFeedbackError,
    OpenRouterRequestRejectedError,
    OpenRouterTransportFailure,
    RetryExhaustedError,
    TransportFailureKind,
    UnknownTaskError,
    WaitingForModelError,
)
from jacaranda_api.llm.http_client import OpenRouterHTTPResponse
from jacaranda_api.llm.models import JsonObject, JsonValue, ValidationFeedback
from jacaranda_api.llm.openrouter import FREE_MODEL, OpenRouterLLMProvider

OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer"],
    "properties": {"answer": {"type": "string"}},
}
INPUT_SCHEMA: JsonObject = {
    "type": "object",
    "additionalProperties": False,
    "required": ["question"],
    "properties": {"question": {"type": "string"}},
}
FIXTURE_KEY = SecretStr("fixture-key")


@dataclass
class FakeCatalog(PromptCatalogReader):
    input_schema: JsonObject | None = None

    def resolve(self, task_name: str) -> PromptTask:
        if task_name != "test_task":
            raise UnknownTaskError()
        return PromptTask(
            task_name=task_name,
            prompt_version="0.1.0",
            stage="S-test",
            prompt_text="Return strict JSON. Never perform arithmetic.",
            output_schema=OUTPUT_SCHEMA,
            output_schema_reference="fixture",
            input_schema=self.input_schema,
            batching=None,
        )


@dataclass
class FakeHTTPClient:
    outcomes: list[OpenRouterHTTPResponse | OpenRouterTransportFailure]
    payloads: list[JsonObject] = field(default_factory=list)
    keys: list[SecretStr] = field(default_factory=list)

    async def create_chat_completion(
        self,
        *,
        api_key: SecretStr,
        payload: JsonObject,
    ) -> OpenRouterHTTPResponse:
        self.payloads.append(payload)
        self.keys.append(api_key)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, OpenRouterTransportFailure):
            raise outcome
        return outcome


def completion(
    content: str,
    *,
    model: str = "free/provider-model",
    finish_reason: str | None = "stop",
    usage: JsonObject | None = None,
) -> OpenRouterHTTPResponse:
    body: JsonObject = {
        "model": model,
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {"content": content},
            }
        ],
    }
    if usage is not None:
        body["usage"] = usage
    return OpenRouterHTTPResponse(status_code=200, body=body)


def provider(
    client: FakeHTTPClient,
    *,
    api_key: SecretStr | None = FIXTURE_KEY,
    catalog: PromptCatalogReader | None = None,
    max_attempts: int = 3,
) -> OpenRouterLLMProvider:
    return OpenRouterLLMProvider(
        api_key=api_key,
        requested_model=FREE_MODEL,
        catalog=catalog or FakeCatalog(),
        http_client=client,
        max_attempts=max_attempts,
    )


@pytest.mark.anyio
async def test_success_returns_validated_output_and_complete_metadata() -> None:
    client = FakeHTTPClient(
        [
            completion(
                '{"answer":"资料不足"}',
                model="vendor/model:free",
                usage={"prompt_tokens": 12, "completion_tokens": 4},
            )
        ]
    )
    llm = provider(client)

    result = await llm.run("test_task", {"question": "synthetic"}, OUTPUT_SCHEMA)

    assert isinstance(llm, LLMProvider)
    assert result.output == {"answer": "资料不足"}
    assert result.requested_model == "openrouter/free"
    assert result.returned_model == "vendor/model:free"
    assert result.input_tokens == 12
    assert result.output_tokens == 4
    assert result.attempt_count == 1
    assert result.finish_status == "stop"
    assert result.attempts[0].returned_model == "vendor/model:free"
    assert result.latency_ms >= 0
    payload = client.payloads[0]
    assert payload["model"] == "openrouter/free"
    assert payload["stream"] is False
    assert payload["provider"] == {"require_parameters": True}
    response_format = cast(dict[str, object], payload["response_format"])
    assert response_format["type"] == "json_schema"
    assert cast(dict[str, object], response_format["json_schema"])["strict"] is True
    assert "openrouter/auto" not in json.dumps(payload)
    assert "fixture-key" not in json.dumps(payload)
    assert client.keys[0].get_secret_value() == "fixture-key"


@pytest.mark.anyio
async def test_missing_usage_is_explicitly_none() -> None:
    result = await provider(FakeHTTPClient([completion('{"answer":"ok"}')])).run(
        "test_task",
        {"question": "synthetic"},
        OUTPUT_SCHEMA,
    )

    assert result.input_tokens is None
    assert result.output_tokens is None


@pytest.mark.parametrize(
    "model",
    ["openrouter/auto", "openai/gpt-paid", "vendor/model:free", "", " OPENROUTER/FREE "],
)
def test_any_model_other_than_free_router_is_rejected(model: str) -> None:
    client = FakeHTTPClient([])
    with pytest.raises(FreeOnlyModelPolicyError):
        OpenRouterLLMProvider(
            api_key=SecretStr("fixture-key"),
            requested_model=model,
            catalog=FakeCatalog(),
            http_client=client,
        )
    assert client.payloads == []


def test_retry_limit_is_bounded() -> None:
    client = FakeHTTPClient([])
    for invalid in (0, 4):
        with pytest.raises(ValueError, match="between 1 and 3"):
            provider(client, max_attempts=invalid)


@pytest.mark.anyio
@pytest.mark.parametrize("api_key", [None, SecretStr(""), SecretStr("   ")])
async def test_missing_key_is_safe_and_fails_before_network(api_key: SecretStr | None) -> None:
    client = FakeHTTPClient([])
    with pytest.raises(LLMConfigurationError) as caught:
        await provider(client, api_key=api_key).run(
            "test_task",
            {"question": "synthetic"},
            OUTPUT_SCHEMA,
        )

    assert client.payloads == []
    assert "fixture" not in str(caught.value)


@pytest.mark.anyio
async def test_unknown_task_and_contract_mismatches_fail_before_network() -> None:
    client = FakeHTTPClient([])
    llm = provider(client)

    with pytest.raises(UnknownTaskError):
        await llm.run("unknown", {"question": "synthetic"}, OUTPUT_SCHEMA)
    with pytest.raises(InputSchemaMismatchError):
        await llm.run(
            "test_task",
            {"question": "synthetic"},
            {"type": "object"},
        )
    with pytest.raises(InputSchemaMismatchError):
        await provider(client, catalog=FakeCatalog(INPUT_SCHEMA)).run(
            "test_task",
            {"wrong": "field"},
            OUTPUT_SCHEMA,
        )
    with pytest.raises(InputSchemaMismatchError):
        await llm.run(
            "test_task",
            {"question": float("nan")},
            OUTPUT_SCHEMA,
        )
    assert client.payloads == []


@pytest.mark.anyio
async def test_valid_machine_readable_input_schema_reaches_provider() -> None:
    client = FakeHTTPClient([completion('{"answer":"ok"}')])
    result = await provider(client, catalog=FakeCatalog(INPUT_SCHEMA)).run(
        "test_task",
        {"question": "synthetic"},
        OUTPUT_SCHEMA,
    )
    assert result.output == {"answer": "ok"}


@pytest.mark.anyio
async def test_non_retryable_feedback_halts_and_retryable_feedback_is_sanitised() -> None:
    blocked_client = FakeHTTPClient([])
    non_retryable = ValidationFeedback(
        code="insufficient_evidence",
        stage="S-test",
        path="/",
        retryable=False,
        detail="human review required",
    )
    with pytest.raises(NonRetryableFeedbackError):
        await provider(blocked_client).run(
            "test_task",
            {"question": "synthetic"},
            OUTPUT_SCHEMA,
            validator_feedback=(non_retryable,),
        )

    retryable = non_retryable.model_copy(
        update={
            "code": "dangling_reference",
            "retryable": True,
            "detail": "raw-secret-must-not-be-forwarded",
        }
    )
    client = FakeHTTPClient([completion('{"answer":"ok"}')])
    await provider(client).run(
        "test_task",
        {"question": "synthetic"},
        OUTPUT_SCHEMA,
        validator_feedback=(retryable,),
    )
    payload_text = json.dumps(client.payloads[0])
    assert "dangling_reference" in payload_text
    assert "raw-secret-must-not-be-forwarded" not in payload_text


@pytest.mark.anyio
async def test_invalid_json_retries_without_echoing_raw_output() -> None:
    client = FakeHTTPClient(
        [
            completion("not-json-private-output"),
            completion('{"answer":"valid"}', model="another/free-model"),
        ]
    )

    result = await provider(client).run(
        "test_task",
        {"question": "synthetic"},
        OUTPUT_SCHEMA,
    )

    assert result.output == {"answer": "valid"}
    assert result.attempt_count == 2
    assert len(result.attempts) == 2
    second_payload = json.dumps(client.payloads[1])
    assert "invalid_json" in second_payload
    assert "not-json-private-output" not in second_payload


@pytest.mark.anyio
async def test_schema_invalid_json_retries_with_structured_feedback() -> None:
    client = FakeHTTPClient(
        [
            completion('{"answer":123}'),
            completion('{"answer":"valid"}'),
        ]
    )

    result = await provider(client).run(
        "test_task",
        {"question": "synthetic"},
        OUTPUT_SCHEMA,
    )

    assert result.attempt_count == 2
    feedback_envelope = json.loads(
        cast(list[dict[str, str]], client.payloads[1]["messages"])[1]["content"]
    )
    feedback = feedback_envelope["validator_feedback"][0]
    assert feedback["code"] == "schema_validation_failed"
    assert feedback["path"] == "/answer"
    assert "123" not in feedback["detail"]


@pytest.mark.anyio
async def test_truncated_completion_is_retried_and_never_accepted() -> None:
    client = FakeHTTPClient(
        [
            completion('{"answer":"partial"}', finish_reason="length"),
            completion('{"answer":"complete"}'),
        ]
    )
    result = await provider(client).run(
        "test_task",
        {"question": "synthetic"},
        OUTPUT_SCHEMA,
    )

    assert result.output == {"answer": "complete"}
    assert "truncated_response" in json.dumps(client.payloads[1])


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("contents", "last_code"),
    [
        (["bad", "bad", "bad"], "invalid_json"),
        (['{"answer":1}', '{"answer":2}', '{"answer":3}'], "schema_validation_failed"),
    ],
)
async def test_repeated_invalid_output_raises_retry_exhausted(
    contents: Sequence[str],
    last_code: str,
) -> None:
    client = FakeHTTPClient([completion(item) for item in contents])
    with pytest.raises(RetryExhaustedError) as caught:
        await provider(client).run(
            "test_task",
            {"question": "synthetic"},
            OUTPUT_SCHEMA,
        )

    assert caught.value.retryable is True
    assert caught.value.attempt_count == 3
    assert caught.value.as_dict()["last_code"] == last_code
    assert len(client.payloads) == 3


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (401, LLMAuthenticationError),
        (403, LLMAuthenticationError),
        (404, WaitingForModelError),
        (408, LLMTimeoutError),
        (429, LLMRateLimitError),
        (400, OpenRouterRequestRejectedError),
        (500, LLMUnavailableError),
        (502, LLMUnavailableError),
        (503, WaitingForModelError),
    ],
)
async def test_http_statuses_are_classified_and_sanitised(
    status: int,
    error_type: type[LLMProviderError],
) -> None:
    client = FakeHTTPClient(
        [
            OpenRouterHTTPResponse(
                status_code=status,
                body={"error": {"code": status, "message": "apikey=must-not-leak"}},
            )
        ]
    )
    with pytest.raises(error_type) as caught:
        await provider(client).run(
            "test_task",
            {"question": "synthetic"},
            OUTPUT_SCHEMA,
        )

    assert "must-not-leak" not in str(caught.value)


@pytest.mark.anyio
async def test_payment_required_fails_closed_without_fallback() -> None:
    client = FakeHTTPClient(
        [OpenRouterHTTPResponse(status_code=402, body={"error": {"code": 402}})]
    )
    with pytest.raises(FreeOnlyModelPolicyError):
        await provider(client).run(
            "test_task",
            {"question": "synthetic"},
            OUTPUT_SCHEMA,
        )
    assert len(client.payloads) == 1
    assert client.payloads[0]["model"] == "openrouter/free"


@pytest.mark.anyio
async def test_embedded_error_status_is_classified_even_with_http_200() -> None:
    client = FakeHTTPClient(
        [OpenRouterHTTPResponse(status_code=200, body={"error": {"code": 429}})]
    )
    with pytest.raises(LLMRateLimitError):
        await provider(client).run(
            "test_task",
            {"question": "synthetic"},
            OUTPUT_SCHEMA,
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body",
    [
        [],
        {"error": "invalid"},
        {"error": {"code": True}},
    ],
)
async def test_malformed_error_envelopes_fall_back_to_http_status(body: object) -> None:
    client = FakeHTTPClient(
        [OpenRouterHTTPResponse(status_code=400, body=cast(JsonValue, body))]
    )
    with pytest.raises(OpenRouterRequestRejectedError):
        await provider(client).run(
            "test_task",
            {"question": "synthetic"},
            OUTPUT_SCHEMA,
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("kind", "error_type"),
    [
        (TransportFailureKind.TIMEOUT, LLMTimeoutError),
        (TransportFailureKind.UNAVAILABLE, LLMUnavailableError),
        (TransportFailureKind.MALFORMED_RESPONSE, MalformedUpstreamResponseError),
    ],
)
async def test_transport_failures_are_classified_without_internal_retry(
    kind: TransportFailureKind,
    error_type: type[LLMProviderError],
) -> None:
    client = FakeHTTPClient([OpenRouterTransportFailure(kind)])
    with pytest.raises(error_type):
        await provider(client).run(
            "test_task",
            {"question": "synthetic"},
            OUTPUT_SCHEMA,
        )
    assert len(client.payloads) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response", "error_type"),
    [
        (OpenRouterHTTPResponse(200, []), MalformedUpstreamResponseError),
        (
            OpenRouterHTTPResponse(200, {"model": "", "choices": []}),
            MalformedUpstreamResponseError,
        ),
        (completion("{}", finish_reason="content_filter"), LLMContentFilteredError),
        (completion("{}", finish_reason="error"), LLMUnavailableError),
        (completion("{}", finish_reason="tool_calls"), MalformedUpstreamResponseError),
        (completion("{}", finish_reason=None), MalformedUpstreamResponseError),
    ],
)
async def test_malformed_or_unsupported_completion_is_never_accepted(
    response: OpenRouterHTTPResponse,
    error_type: type[LLMProviderError],
) -> None:
    with pytest.raises(error_type):
        await provider(FakeHTTPClient([response])).run(
            "test_task",
            {"question": "synthetic"},
            OUTPUT_SCHEMA,
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "content",
    [
        '{"answer":"first","answer":"second"}',
        '{"answer":NaN}',
    ],
)
async def test_non_standard_or_ambiguous_json_is_rejected(content: str) -> None:
    client = FakeHTTPClient([completion(content)])
    with pytest.raises(RetryExhaustedError):
        await provider(client, max_attempts=1).run(
            "test_task",
            {"question": "synthetic"},
            OUTPUT_SCHEMA,
        )


@pytest.mark.anyio
async def test_negative_clock_delta_is_safely_clamped() -> None:
    ticks = iter([4_000_000, 3_000_000, 2_000_000, 1_000_000])
    client = FakeHTTPClient([completion('{"answer":"ok"}')])
    llm = OpenRouterLLMProvider(
        api_key=FIXTURE_KEY,
        requested_model=FREE_MODEL,
        catalog=FakeCatalog(),
        http_client=client,
        clock=lambda: next(ticks),
    )
    result = await llm.run("test_task", {"question": "synthetic"}, OUTPUT_SCHEMA)
    assert result.latency_ms == 0
    assert result.attempts[0].latency_ms == 0
