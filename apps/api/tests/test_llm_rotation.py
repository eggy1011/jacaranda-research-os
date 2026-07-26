from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest
from pydantic import SecretStr

from jacaranda_api.config import Settings
from jacaranda_api.llm.errors import (
    FreeOnlyModelPolicyError,
    LLMAuthenticationError,
    LLMProviderError,
    LLMRateLimitError,
    RetryExhaustedError,
    WaitingForModelError,
)
from jacaranda_api.llm.factory import build_llm_provider, candidate_models
from jacaranda_api.llm.http_client import OpenRouterHTTPResponse
from jacaranda_api.llm.models import JsonObject, JsonValue, LLMResult, ValidationFeedback
from jacaranda_api.llm.openrouter import OpenRouterLLMProvider, model_allowed
from jacaranda_api.llm.rotation import RotatingOpenRouterProvider

SCHEMA: dict[str, JsonValue] = {"type": "object"}


def _result(model: str) -> LLMResult:
    return LLMResult(
        output={"ok": True},
        task_name="extraction",
        prompt_version="1.0.0",
        requested_model=model,
        returned_model=model,
        latency_ms=1,
        input_tokens=None,
        output_tokens=None,
        attempt_count=1,
        finish_status="stop",
        attempts=(),
    )


class ScriptedProvider:
    """LLMProvider double: raises queued errors, then succeeds forever."""

    def __init__(self, model: str, errors: list[LLMProviderError] | None = None) -> None:
        self.model = model
        self.errors = list(errors or [])
        self.calls = 0

    async def run(
        self,
        task_name: str,
        structured_input: Mapping[str, JsonValue],
        output_json_schema: Mapping[str, JsonValue],
        *,
        validator_feedback: Sequence[ValidationFeedback] = (),
    ) -> LLMResult:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return _result(self.model)


class TestModelPolicy:
    def test_free_router_and_free_suffix_allowed(self) -> None:
        assert model_allowed("openrouter/free", allow_paid=False)
        assert model_allowed("deepseek/deepseek-chat:free", allow_paid=False)

    def test_paid_requires_opt_in(self) -> None:
        assert not model_allowed("deepseek/deepseek-chat", allow_paid=False)
        assert model_allowed("deepseek/deepseek-chat", allow_paid=True)

    def test_auto_and_malformed_never_allowed(self) -> None:
        assert not model_allowed("openrouter/auto", allow_paid=True)
        assert not model_allowed("", allow_paid=True)
        assert not model_allowed(" padded/model ", allow_paid=True)
        assert not model_allowed("no-slash", allow_paid=True)


class TestRotation:
    @pytest.mark.anyio
    async def test_rotates_on_availability_errors_and_sticks(self) -> None:
        first = ScriptedProvider("a/free:free", [WaitingForModelError(1)])
        second = ScriptedProvider("b/free:free")
        rotating = RotatingOpenRouterProvider(
            [("a/free:free", first), ("b/free:free", second)]
        )
        result = await rotating.run("extraction", {}, SCHEMA)
        assert result.returned_model == "b/free:free"
        assert rotating.current_model == "b/free:free"
        # sticky: the next call starts at the model that worked
        await rotating.run("extraction", {}, SCHEMA)
        assert first.calls == 1
        assert second.calls == 2

    @pytest.mark.anyio
    async def test_rotates_on_rate_limit_and_retry_exhaustion(self) -> None:
        rotating = RotatingOpenRouterProvider(
            [
                ("a/m:free", ScriptedProvider("a/m:free", [LLMRateLimitError(1)])),
                (
                    "b/m:free",
                    ScriptedProvider("b/m:free", [RetryExhaustedError(3, "invalid_json")]),
                ),
                ("c/m:free", ScriptedProvider("c/m:free")),
            ]
        )
        result = await rotating.run("extraction", {}, SCHEMA)
        assert result.returned_model == "c/m:free"

    @pytest.mark.anyio
    async def test_runtime_free_policy_violation_rotates(self) -> None:
        rotating = RotatingOpenRouterProvider(
            [
                ("a/m:free", ScriptedProvider("a/m:free", [FreeOnlyModelPolicyError()])),
                ("b/m:free", ScriptedProvider("b/m:free")),
            ]
        )
        result = await rotating.run("extraction", {}, SCHEMA)
        assert result.returned_model == "b/m:free"

    @pytest.mark.anyio
    async def test_non_retryable_caller_error_does_not_rotate(self) -> None:
        second = ScriptedProvider("b/m:free")
        rotating = RotatingOpenRouterProvider(
            [
                ("a/m:free", ScriptedProvider("a/m:free", [LLMAuthenticationError(1)])),
                ("b/m:free", second),
            ]
        )
        with pytest.raises(LLMAuthenticationError):
            await rotating.run("extraction", {}, SCHEMA)
        assert second.calls == 0

    @pytest.mark.anyio
    async def test_exhausting_all_candidates_raises_last_error(self) -> None:
        rotating = RotatingOpenRouterProvider(
            [
                ("a/m:free", ScriptedProvider("a/m:free", [WaitingForModelError(1)])),
                ("b/m:free", ScriptedProvider("b/m:free", [LLMRateLimitError(1)])),
            ]
        )
        with pytest.raises(LLMRateLimitError):
            await rotating.run("extraction", {}, SCHEMA)

    def test_empty_candidate_list_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            RotatingOpenRouterProvider([])


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql://localhost/test",
        "redis_url": "redis://localhost",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


class TestFactory:
    def test_candidates_default_to_single_model(self) -> None:
        assert candidate_models(_settings()) == ["openrouter/free"]

    def test_candidates_parse_ordered_list(self) -> None:
        settings = _settings(openrouter_models=" a/m:free , b/m:free ,")
        assert candidate_models(settings) == ["a/m:free", "b/m:free"]

    def test_paid_candidate_without_opt_in_fails_at_configuration_time(self) -> None:
        from pathlib import Path

        from jacaranda_api.llm.catalog import PromptCatalog

        root = Path(__file__).resolve().parents[3]
        settings = _settings(openrouter_models="a/m:free,deepseek/deepseek-chat")
        with pytest.raises(FreeOnlyModelPolicyError):
            build_llm_provider(settings, PromptCatalog(root), _FakeHTTP())

    def test_paid_candidate_with_opt_in_builds_rotation(self) -> None:
        from pathlib import Path

        from jacaranda_api.llm.catalog import PromptCatalog

        root = Path(__file__).resolve().parents[3]
        settings = _settings(
            openrouter_models="a/m:free,deepseek/deepseek-chat", allow_paid_models=True
        )
        provider = build_llm_provider(settings, PromptCatalog(root), _FakeHTTP())
        assert isinstance(provider, RotatingOpenRouterProvider)
        assert provider.current_model == "a/m:free"

    def test_single_candidate_builds_plain_provider(self) -> None:
        from pathlib import Path

        from jacaranda_api.llm.catalog import PromptCatalog

        root = Path(__file__).resolve().parents[3]
        provider = build_llm_provider(_settings(), PromptCatalog(root), _FakeHTTP())
        assert isinstance(provider, OpenRouterLLMProvider)


class _FakeHTTP:
    async def create_chat_completion(
        self, *, api_key: SecretStr, payload: JsonObject
    ) -> OpenRouterHTTPResponse:
        raise AssertionError("factory tests never issue requests")
