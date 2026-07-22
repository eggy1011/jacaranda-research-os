from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DemoRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: Literal["600XXX"] = "600XXX"
    market: Literal["CN-A"] = "CN-A"
    exchange: Literal["SSE"] = "SSE"
    company_name: dict[Literal["zh_CN", "en_AU"], str] = {
        "zh_CN": "示例智能制造股份有限公司",
        "en_AU": "Example Intelligent Manufacturing Co., Ltd.",
    }
    as_of_date: date = date(2026, 7, 10)
    is_mock: Literal[True] = True
    editions: tuple[Literal["zh-CN", "en-AU"], ...] = ("zh-CN", "en-AU")

    @model_validator(mode="after")
    def require_both_editions(self) -> DemoRequest:
        expected_name = {
            "zh_CN": "示例智能制造股份有限公司",
            "en_AU": "Example Intelligent Manufacturing Co., Ltd.",
        }
        if (
            self.editions != ("zh-CN", "en-AU")
            or self.company_name != expected_name
            or self.as_of_date != date(2026, 7, 10)
        ):
            raise ValueError("the mock vertical slice accepts only the fixed bilingual fixture")
        return self


class InvocationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    RETRYABLE_FAILED = "retryable_failed"
    NON_RETRYABLE_FAILED = "non_retryable_failed"


class AttemptRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attempt: int = Field(ge=1)
    status: InvocationStatus
    code: str | None = None
    retryable: bool | None = None
    requested_model: str = "openrouter/free"
    returned_model: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)


class Checkpoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int = Field(ge=1)
    invocation_id: str
    stage: str
    task_name: str
    prompt_version: str
    status: InvocationStatus
    attempt_count: int = Field(ge=1)
    attempts: tuple[AttemptRecord, ...]
    output_sha256: str | None = None


class PipelineArtifacts(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True, extra="forbid")

    root: Path
    research_package: Path
    deck_json: dict[str, Path]
    pptx: dict[str, Path]
    overflow_reports: dict[str, Path]
    manifest: Path
    checkpoints: Path


JsonDict = dict[str, Any]


class PipelineConfigurationError(ValueError):
    """A required, registry-driven mock pipeline binding is absent or ambiguous."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class PresentationResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True, extra="forbid")

    edition: Literal["zh-CN", "en-AU"]
    pptx_path: Path
    pdf_path: None = None
    overflow_report: JsonDict
