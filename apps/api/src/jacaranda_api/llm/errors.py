from __future__ import annotations

from enum import StrEnum
from typing import Any


class LLMProviderError(Exception):
    """Safe failure contract. Raw prompts, responses and credentials are never attached."""

    def __init__(
        self,
        *,
        code: str,
        retryable: bool,
        message: str,
        attempt_count: int = 0,
    ) -> None:
        self.code = code
        self.retryable = retryable
        self.message = message
        self.attempt_count = attempt_count
        super().__init__(message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "provider": "openrouter",
            "retryable": self.retryable,
            "message": self.message,
            "attempt_count": self.attempt_count,
        }


class LLMConfigurationError(LLMProviderError):
    def __init__(self, setting: str) -> None:
        super().__init__(
            code="llm_configuration_error",
            retryable=False,
            message=f"OpenRouter is not configured: required setting {setting} is missing",
        )


class FreeOnlyModelPolicyError(LLMProviderError):
    def __init__(self, setting: str = "OPENROUTER_MODEL") -> None:
        super().__init__(
            code="free_only_model_policy_violation",
            retryable=False,
            message=f"{setting} must use the approved free-only OpenRouter configuration",
        )


class PromptCatalogError(LLMProviderError):
    def __init__(self) -> None:
        super().__init__(
            code="prompt_catalog_error",
            retryable=False,
            message="the prompt catalogue does not match its machine-readable contract",
        )


class UnknownTaskError(LLMProviderError):
    def __init__(self) -> None:
        super().__init__(
            code="unknown_llm_task",
            retryable=False,
            message="task_name is not registered in the prompt catalogue",
        )


class InputSchemaMismatchError(LLMProviderError):
    def __init__(self) -> None:
        super().__init__(
            code="input_schema_mismatch",
            retryable=False,
            message="the structured input or output schema does not match the registered task",
        )


class NonRetryableFeedbackError(LLMProviderError):
    def __init__(self) -> None:
        super().__init__(
            code="non_retryable_validator_feedback",
            retryable=False,
            message="validator feedback requires human review before another model call",
        )


class LLMAuthenticationError(LLMProviderError):
    def __init__(self, attempt_count: int) -> None:
        super().__init__(
            code="llm_authentication_error",
            retryable=False,
            message="OpenRouter rejected its server-side credentials or permissions",
            attempt_count=attempt_count,
        )


class LLMRateLimitError(LLMProviderError):
    def __init__(self, attempt_count: int) -> None:
        super().__init__(
            code="llm_rate_limited",
            retryable=True,
            message="the OpenRouter free route is rate limited",
            attempt_count=attempt_count,
        )


class LLMTimeoutError(LLMProviderError):
    def __init__(self, attempt_count: int) -> None:
        super().__init__(
            code="llm_timeout",
            retryable=True,
            message="the OpenRouter free route timed out",
            attempt_count=attempt_count,
        )


class LLMUnavailableError(LLMProviderError):
    def __init__(self, attempt_count: int) -> None:
        super().__init__(
            code="llm_provider_unavailable",
            retryable=True,
            message="the OpenRouter free route is temporarily unavailable",
            attempt_count=attempt_count,
        )


class WaitingForModelError(LLMProviderError):
    def __init__(self, attempt_count: int) -> None:
        super().__init__(
            code="waiting_for_model",
            retryable=True,
            message="no free model currently supports the required structured output",
            attempt_count=attempt_count,
        )


class MalformedUpstreamResponseError(LLMProviderError):
    def __init__(self, attempt_count: int) -> None:
        super().__init__(
            code="malformed_llm_response",
            retryable=False,
            message="OpenRouter returned a response that does not match its protocol",
            attempt_count=attempt_count,
        )


class OpenRouterRequestRejectedError(LLMProviderError):
    def __init__(self, attempt_count: int) -> None:
        super().__init__(
            code="openrouter_request_rejected",
            retryable=False,
            message="OpenRouter rejected the structured request",
            attempt_count=attempt_count,
        )


class LLMContentFilteredError(LLMProviderError):
    def __init__(self, attempt_count: int) -> None:
        super().__init__(
            code="llm_content_filtered",
            retryable=False,
            message="the provider blocked the generated content",
            attempt_count=attempt_count,
        )


class RetryExhaustedError(LLMProviderError):
    def __init__(self, attempt_count: int, last_code: str) -> None:
        self.last_code = last_code
        super().__init__(
            code="llm_retry_exhausted",
            retryable=True,
            message=f"structured output remained invalid after {attempt_count} attempts",
            attempt_count=attempt_count,
        )

    def as_dict(self) -> dict[str, Any]:
        result = super().as_dict()
        result["last_code"] = self.last_code
        return result


class TransportFailureKind(StrEnum):
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    MALFORMED_RESPONSE = "malformed_response"


class OpenRouterTransportFailure(Exception):
    """Sanitised signal from the concrete HTTP boundary."""

    def __init__(self, kind: TransportFailureKind) -> None:
        self.kind = kind
        super().__init__(kind.value)
