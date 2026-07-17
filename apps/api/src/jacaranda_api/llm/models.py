from __future__ import annotations

from typing import Annotated, Any, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class ValidationFeedback(BaseModel):
    """Machine-readable validator feedback safe to pass to a retry attempt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: Annotated[str, Field(min_length=1, max_length=80)]
    stage: Annotated[str, Field(min_length=1, max_length=32)]
    path: Annotated[str, Field(min_length=1, max_length=512)]
    retryable: bool
    detail: Annotated[str, Field(min_length=1, max_length=512)]


class LLMAttemptMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attempt: Annotated[int, Field(ge=1)]
    returned_model: str
    latency_ms: Annotated[int, Field(ge=0)]
    input_tokens: Annotated[int, Field(ge=0)] | None
    output_tokens: Annotated[int, Field(ge=0)] | None
    finish_status: str | None


class LLMResult(BaseModel):
    """Validated provider output and audit metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    output: dict[str, Any]
    task_name: Annotated[str, Field(min_length=1)]
    prompt_version: Annotated[str, Field(min_length=1)]
    requested_model: Annotated[str, Field(min_length=1)]
    returned_model: Annotated[str, Field(min_length=1)]
    latency_ms: Annotated[int, Field(ge=0)]
    input_tokens: Annotated[int, Field(ge=0)] | None
    output_tokens: Annotated[int, Field(ge=0)] | None
    attempt_count: Annotated[int, Field(ge=1)]
    finish_status: str | None
    attempts: tuple[LLMAttemptMetadata, ...]
