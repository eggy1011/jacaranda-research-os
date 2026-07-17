from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from time import perf_counter_ns
from typing import Annotated, Any, cast

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt, StrictStr, ValidationError

from jacaranda_api.llm.catalog import PromptCatalogReader, PromptTask
from jacaranda_api.llm.errors import (
    FreeOnlyModelPolicyError,
    InputSchemaMismatchError,
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMContentFilteredError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    MalformedUpstreamResponseError,
    NonRetryableFeedbackError,
    OpenRouterRequestRejectedError,
    OpenRouterTransportFailure,
    RetryExhaustedError,
    TransportFailureKind,
    WaitingForModelError,
)
from jacaranda_api.llm.http_client import OpenRouterHTTPClient, OpenRouterHTTPResponse
from jacaranda_api.llm.models import (
    JsonObject,
    JsonValue,
    LLMAttemptMetadata,
    LLMResult,
    ValidationFeedback,
)
from jacaranda_api.llm.schema_loader import (
    canonical_json,
    normalise_json_object,
    safe_feedback_payload,
    validate_instance,
    validate_schema_contract,
)

FREE_MODEL = "openrouter/free"
DEFAULT_MAX_ATTEMPTS = 3
Clock = Callable[[], int]


class _Usage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_tokens: Annotated[StrictInt, Field(ge=0)] | None = None
    completion_tokens: Annotated[StrictInt, Field(ge=0)] | None = None


class _Message(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: StrictStr


class _Choice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    finish_reason: StrictStr | None = None
    message: _Message


class _Completion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: Annotated[StrictStr, Field(min_length=1)]
    choices: Annotated[list[_Choice], Field(min_length=1)]
    usage: _Usage | None = None


class OpenRouterLLMProvider:
    """Free-only OpenRouter implementation with strict local output validation."""

    def __init__(
        self,
        *,
        api_key: SecretStr | None,
        requested_model: str,
        catalog: PromptCatalogReader,
        http_client: OpenRouterHTTPClient,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        clock: Clock = perf_counter_ns,
    ) -> None:
        if requested_model != FREE_MODEL:
            raise FreeOnlyModelPolicyError()
        if not 1 <= max_attempts <= DEFAULT_MAX_ATTEMPTS:
            raise ValueError("max_attempts must be between 1 and 3")
        self._api_key = api_key
        self._requested_model = requested_model
        self._catalog = catalog
        self._http_client = http_client
        self._max_attempts = max_attempts
        self._clock = clock

    async def run(
        self,
        task_name: str,
        structured_input: Mapping[str, JsonValue],
        output_json_schema: Mapping[str, JsonValue],
        *,
        validator_feedback: Sequence[ValidationFeedback] = (),
    ) -> LLMResult:
        api_key = self._require_api_key()
        task = self._catalog.resolve(task_name)
        supplied_input = normalise_json_object(structured_input)
        schema = validate_schema_contract(output_json_schema, task.output_schema)
        if task.input_schema is not None:
            if validate_instance(supplied_input, task.input_schema, stage=task.stage):
                raise InputSchemaMismatchError()
        feedback = tuple(validator_feedback)
        if any(not item.retryable for item in feedback):
            raise NonRetryableFeedbackError()

        started = self._clock()
        attempts: list[LLMAttemptMetadata] = []
        last_code = "invalid_json"
        for attempt_number in range(1, self._max_attempts + 1):
            payload = self._request_payload(task, supplied_input, schema, feedback)
            attempt_started = self._clock()
            try:
                response = await self._http_client.create_chat_completion(
                    api_key=api_key,
                    payload=payload,
                )
            except OpenRouterTransportFailure as exc:
                self._raise_transport(exc, attempt_number)
            completion = self._parse_completion(response, attempt_number)
            attempt_latency = _elapsed_ms(attempt_started, self._clock())
            choice = completion.choices[0]
            usage = completion.usage
            attempts.append(
                LLMAttemptMetadata(
                    attempt=attempt_number,
                    returned_model=completion.model,
                    latency_ms=attempt_latency,
                    input_tokens=usage.prompt_tokens if usage else None,
                    output_tokens=usage.completion_tokens if usage else None,
                    finish_status=choice.finish_reason,
                )
            )

            if choice.finish_reason == "length":
                last_code = "truncated_response"
                feedback = (
                    ValidationFeedback(
                        code=last_code,
                        stage=task.stage,
                        path="/",
                        retryable=True,
                        detail="completion ended before the structured output was complete",
                    ),
                )
                continue
            if choice.finish_reason == "content_filter":
                raise LLMContentFilteredError(attempt_number)
            if choice.finish_reason == "error":
                raise LLMUnavailableError(attempt_number)
            if choice.finish_reason != "stop":
                raise MalformedUpstreamResponseError(attempt_number)

            try:
                output = _strict_json_loads(choice.message.content)
            except (TypeError, ValueError, json.JSONDecodeError):
                last_code = "invalid_json"
                feedback = (
                    ValidationFeedback(
                        code=last_code,
                        stage=task.stage,
                        path="/",
                        retryable=True,
                        detail="completion was not strict JSON",
                    ),
                )
                continue
            validation_feedback = validate_instance(output, schema, stage=task.stage)
            if validation_feedback:
                last_code = "schema_validation_failed"
                feedback = validation_feedback
                continue

            total_latency = _elapsed_ms(started, self._clock())
            final_attempt = attempts[-1]
            return LLMResult(
                output=cast(dict[str, Any], output),
                task_name=task.task_name,
                prompt_version=task.prompt_version,
                requested_model=self._requested_model,
                returned_model=completion.model,
                latency_ms=total_latency,
                input_tokens=final_attempt.input_tokens,
                output_tokens=final_attempt.output_tokens,
                attempt_count=attempt_number,
                finish_status=choice.finish_reason,
                attempts=tuple(attempts),
            )
        raise RetryExhaustedError(self._max_attempts, last_code)

    def _require_api_key(self) -> SecretStr:
        if self._api_key is None or not self._api_key.get_secret_value().strip():
            raise LLMConfigurationError("OPENROUTER_API_KEY")
        return self._api_key

    def _request_payload(
        self,
        task: PromptTask,
        structured_input: JsonObject,
        schema: JsonObject,
        feedback: Sequence[ValidationFeedback],
    ) -> JsonObject:
        user_envelope: JsonObject = {"structured_input": structured_input}
        if feedback:
            user_envelope["validator_feedback"] = cast(
                JsonValue,
                safe_feedback_payload(feedback),
            )
        user_content = canonical_json(user_envelope)
        schema_name = f"jacaranda_{task.task_name}_{task.prompt_version}".replace(".", "_")
        return {
            "model": self._requested_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": task.prompt_text},
                {"role": "user", "content": user_content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
            "provider": {"require_parameters": True},
        }

    def _parse_completion(
        self,
        response: OpenRouterHTTPResponse,
        attempt_number: int,
    ) -> _Completion:
        self._raise_for_status(response, attempt_number)
        if not isinstance(response.body, dict):
            raise MalformedUpstreamResponseError(attempt_number)
        try:
            return _Completion.model_validate(response.body)
        except ValidationError:
            raise MalformedUpstreamResponseError(attempt_number) from None

    def _raise_for_status(
        self,
        response: OpenRouterHTTPResponse,
        attempt_number: int,
    ) -> None:
        status = response.status_code
        if status < 400 and not _has_error(response.body):
            return
        embedded_status = _embedded_error_status(response.body)
        self._raise_status(embedded_status or status, attempt_number)

    def _raise_status(self, status: int, attempt_number: int) -> None:
        if status in (401, 403):
            raise LLMAuthenticationError(attempt_number)
        if status == 402:
            raise FreeOnlyModelPolicyError()
        if status == 408:
            raise LLMTimeoutError(attempt_number)
        if status == 429:
            raise LLMRateLimitError(attempt_number)
        if status in (404, 503):
            raise WaitingForModelError(attempt_number)
        if status >= 500:
            raise LLMUnavailableError(attempt_number)
        raise OpenRouterRequestRejectedError(attempt_number)

    def _raise_transport(
        self,
        failure: OpenRouterTransportFailure,
        attempt_number: int,
    ) -> None:
        if failure.kind is TransportFailureKind.TIMEOUT:
            raise LLMTimeoutError(attempt_number) from None
        if failure.kind is TransportFailureKind.MALFORMED_RESPONSE:
            raise MalformedUpstreamResponseError(attempt_number) from None
        raise LLMUnavailableError(attempt_number) from None


def _strict_json_loads(value: str) -> JsonValue:
    def reject_constant(_value: str) -> Any:
        raise ValueError("non-standard JSON constant")

    def reject_duplicate_keys(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
        result: JsonObject = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = item
        return result

    return cast(
        JsonValue,
        json.loads(
            value,
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_keys,
        ),
    )


def _has_error(body: JsonValue) -> bool:
    return isinstance(body, dict) and "error" in body


def _embedded_error_status(body: JsonValue) -> int | None:
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return code if isinstance(code, int) and not isinstance(code, bool) else None


def _elapsed_ms(started: int, ended: int) -> int:
    return max(0, (ended - started) // 1_000_000)
