from __future__ import annotations

from collections.abc import Mapping, Sequence

from jacaranda_api.llm.contracts import LLMProvider
from jacaranda_api.llm.errors import (
    FreeOnlyModelPolicyError,
    LLMProviderError,
    RetryExhaustedError,
)
from jacaranda_api.llm.models import JsonValue, LLMResult, ValidationFeedback


def _should_rotate(error: LLMProviderError) -> bool:
    """Rotate on availability/limit problems and on a model that keeps failing
    validation; never on caller errors (bad input, bad key, bad feedback)."""
    if isinstance(error, RetryExhaustedError):
        return True
    if isinstance(error, FreeOnlyModelPolicyError):
        # A runtime 402 means a listed "free" candidate started charging.
        return True
    return error.retryable


class RotatingOpenRouterProvider:
    """LLMProvider that walks an ordered candidate list (free first, D-008).

    The index is sticky: after a rotation, subsequent calls start at the model
    that last worked instead of hammering a rate-limited candidate. Which model
    served each call is visible in LLMResult.requested_model/returned_model.
    """

    def __init__(self, providers: Sequence[tuple[str, LLMProvider]]) -> None:
        if not providers:
            raise ValueError("at least one model candidate is required")
        self._providers = tuple(providers)
        self._current = 0

    @property
    def current_model(self) -> str:
        return self._providers[self._current][0]

    async def run(
        self,
        task_name: str,
        structured_input: Mapping[str, JsonValue],
        output_json_schema: Mapping[str, JsonValue],
        *,
        validator_feedback: Sequence[ValidationFeedback] = (),
    ) -> LLMResult:
        total = len(self._providers)
        last_error: LLMProviderError | None = None
        for step in range(total):
            index = (self._current + step) % total
            _, provider = self._providers[index]
            try:
                result = await provider.run(
                    task_name,
                    structured_input,
                    output_json_schema,
                    validator_feedback=validator_feedback,
                )
            except LLMProviderError as error:
                if not _should_rotate(error):
                    raise
                last_error = error
                continue
            self._current = index
            return result
        if last_error is None:  # pragma: no cover - loop always sets or returns
            raise RuntimeError("rotation loop finished without an error or a result")
        raise last_error
