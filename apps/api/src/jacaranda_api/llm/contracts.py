from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from jacaranda_api.llm.models import JsonValue, LLMResult, ValidationFeedback


@runtime_checkable
class LLMProvider(Protocol):
    async def run(
        self,
        task_name: str,
        structured_input: Mapping[str, JsonValue],
        output_json_schema: Mapping[str, JsonValue],
        *,
        validator_feedback: Sequence[ValidationFeedback] = (),
    ) -> LLMResult:
        """Run one registered task and return only locally validated structured output."""
        ...
