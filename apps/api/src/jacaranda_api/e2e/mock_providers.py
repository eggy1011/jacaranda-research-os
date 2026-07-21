from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from jacaranda_api.llm.catalog import PromptCatalog
from jacaranda_api.llm.errors import LLMProviderError
from jacaranda_api.llm.models import JsonValue, LLMAttemptMetadata, LLMResult, ValidationFeedback
from jacaranda_api.llm.schema_loader import validate_schema_contract


class FixtureAkshareClient:
    """Network-free client injected into the real AKShare adapter contract."""

    async def fetch_quote(self, symbol: str) -> Mapping[str, object]:
        if symbol != "600XXX":
            raise ValueError("fixture client accepts only the fictional sentinel")
        return {"latest": 28.4, "trade_date": date(2026, 7, 10), "currency": "CNY"}


class ScriptedMockLLMProvider:
    """Registry-driven LLM test double; validates every scripted result locally."""

    def __init__(self, repository_root: Path, failures: dict[str, int] | None = None) -> None:
        self._root = repository_root.resolve()
        self._catalog = PromptCatalog(self._root)
        self._failures = dict(failures or {})
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(
        self,
        task_name: str,
        structured_input: Mapping[str, JsonValue],
        output_json_schema: Mapping[str, JsonValue],
        *,
        validator_feedback: Sequence[ValidationFeedback] = (),
    ) -> LLMResult:
        task = self._catalog.resolve(task_name)
        schema = validate_schema_contract(output_json_schema, task.output_schema)
        remaining = self._failures.get(task_name, 0)
        if remaining:
            self._failures[task_name] = remaining - 1
            raise LLMProviderError(
                code="mock_transient_failure",
                retryable=True,
                message="fixture model requested a retry",
                attempt_count=1,
            )
        payload = copy.deepcopy(dict(structured_input))
        self.calls.append((task_name, payload))
        output = self._script(task_name, payload)
        Draft202012Validator(schema).validate(output)
        attempt = LLMAttemptMetadata(
            attempt=1,
            returned_model="mock/free-structured",
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            finish_status="stop",
        )
        return LLMResult(
            output=output,
            task_name=task_name,
            prompt_version=task.prompt_version,
            requested_model="openrouter/free",
            returned_model=attempt.returned_model,
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            attempt_count=1,
            finish_status="stop",
            attempts=(attempt,),
        )

    def _load(self, filename: str) -> dict[str, Any]:
        path = self._root / "packages/prompts/examples" / filename
        return json.loads(path.read_text(encoding="utf-8"))

    def _script(self, task_name: str, data: dict[str, Any]) -> dict[str, Any]:
        if task_name == "extraction":
            return self._without_annotations(self._load("02-extraction-output.json"))
        if task_name == "source_verification":
            return self._without_annotations(self._load("03-source-verification-output.json"))
        analysis = {
            "company_analysis": "s3a",
            "industry_analysis": "s3b",
            "financial_analysis": "s3c",
            "competition": "s3d",
        }
        if task_name in analysis:
            return copy.deepcopy(self._load("04-analysis-claims.json")[analysis[task_name]])
        if task_name == "valuation_narrative":
            return copy.deepcopy(
                self._load("05-valuation-catalysts-risks.json")["s4_valuation_narrative"]
            )
        if task_name == "catalysts_risks":
            return copy.deepcopy(
                self._load("05-valuation-catalysts-risks.json")["s5_catalysts_risks"]
            )
        if task_name == "translation":
            return {
                "authoritative_language": data["authoritative_language"],
                "texts": copy.deepcopy(data["texts"]),
                "translation_flags": [],
                "glossary_flags": [],
            }
        if task_name == "slide_compression_plan":
            deck = self._deck(str(data["edition"]))
            return {
                "deck_id": deck["deck_id"],
                "package_id": deck["package_id"],
                "edition": deck["edition"],
                "as_of_date": deck["as_of_date"],
                "theme": deck["theme"],
                "slide_stubs": [self._stub(slide) for slide in deck["slides"]],
            }
        if task_name == "slide_compression_slide":
            context = data["deck_context"]
            stub = data["slide_stub"]
            deck = self._deck(str(context["edition"]))
            return copy.deepcopy(deck["slides"][int(stub["slide_no"]) - 1])
        raise AssertionError(f"unhandled registered fixture task: {task_name}")

    def _deck(self, edition: str) -> dict[str, Any]:
        if edition not in {"zh-CN", "en-AU"}:
            raise ValueError("mock presentation supports only full zh-CN and en-AU editions")
        path = self._root / f"packages/presentation/fixtures/deck-sample.{edition}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _without_annotations(value: dict[str, Any]) -> dict[str, Any]:
        return {key: copy.deepcopy(item) for key, item in value.items() if not key.startswith("_")}

    @classmethod
    def _stub(cls, slide: dict[str, Any]) -> dict[str, Any]:
        claim_ids: set[str] = set()
        metric_ids: set[str] = set()

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "claim_id" and isinstance(item, str):
                        claim_ids.add(item)
                    elif key == "metric_id" and isinstance(item, str):
                        metric_ids.add(item)
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(slide)
        return {
            "slide_no": slide["slide_no"],
            "layout": slide["layout"],
            "section_id": slide["section_id"],
            "claim_ids": sorted(claim_ids),
            "metric_ids": sorted(metric_ids),
        }


def fixed_clock() -> datetime:
    return datetime(2026, 7, 10, 10, 0, 0, tzinfo=UTC)
