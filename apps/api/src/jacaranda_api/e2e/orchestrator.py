from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from jacaranda_api.e2e.mock_providers import (
    FixtureAkshareClient,
    ScriptedMockLLMProvider,
    fixed_clock,
)
from jacaranda_api.e2e.models import (
    AttemptRecord,
    Checkpoint,
    DemoRequest,
    InvocationStatus,
    JsonDict,
    PipelineArtifacts,
    PipelineConfigurationError,
)
from jacaranda_api.e2e.presentation import TemplatePresentationProvider
from jacaranda_api.e2e.validation import load_json, validate_decks, validate_package
from jacaranda_api.llm.catalog import PromptCatalog
from jacaranda_api.llm.contracts import LLMProvider
from jacaranda_api.llm.errors import LLMProviderError, RetryExhaustedError
from jacaranda_api.llm.models import LLMResult, ValidationFeedback
from jacaranda_api.llm.schema_loader import validate_instance
from jacaranda_api.market_data.adapters.akshare import AkshareMarketDataProvider
from jacaranda_api.market_data.models import (
    Exchange,
    Market,
    MarketDataCapability,
    NormalizedSymbol,
    ProviderRequest,
)
from jacaranda_api.market_data.source_registry import SourceRegistry


class MockResearchOrchestrator:
    """Deterministic S1-S7 vertical slice; no transport-capable dependency is constructed."""

    def __init__(
        self,
        repository_root: Path,
        *,
        llm: LLMProvider | None = None,
        presentation: TemplatePresentationProvider | None = None,
        max_attempts: int = 3,
    ) -> None:
        self._root = repository_root.resolve()
        self._catalog = PromptCatalog(self._root)
        self._tasks_by_stage = {
            stage: tuple(task for task in self._catalog.all_tasks() if task.stage == stage)
            for stage in ("S1", "S2", "S3a", "S3b", "S3c", "S3d", "S4", "S5", "S6", "S7")
        }
        self._llm = llm or ScriptedMockLLMProvider(self._root)
        self._presentation = presentation or TemplatePresentationProvider(self._root)
        self._max_attempts = max_attempts
        self._checkpoints: list[Checkpoint] = []
        self._results: list[LLMResult] = []

    async def run(self, request: DemoRequest, output_dir: Path) -> PipelineArtifacts:
        with (
            patch("socket.socket", side_effect=RuntimeError("network disabled for mock pipeline")),
            patch(
                "socket.create_connection",
                side_effect=RuntimeError("network disabled for mock pipeline"),
            ),
        ):
            return await self._run_socket_blocked(request, output_dir)

    async def _run_socket_blocked(
        self, request: DemoRequest, output_dir: Path
    ) -> PipelineArtifacts:
        self._prepare_output(output_dir)
        market = await self._market_data(request)
        s1 = await self._execute(
            self._one_task("S1"),
            {"company_context": request.model_dump(), "evidence_chunks": [market]},
        )
        s2 = await self._execute(
            self._one_task("S2"), {"sources": market["sources"], "candidates": s1}
        )
        analysis_input = {"verified": s2, "metrics": market["metrics"], "next_claim_id": "CLM-001"}
        s3 = {
            stage: await self._execute(self._one_task(stage), analysis_input)
            for stage in ("S3a", "S3b", "S3c", "S3d")
        }
        s4 = await self._execute(self._one_task("S4"), {"analysis": s3, "verified": s2})
        s5 = await self._execute(self._one_task("S5"), {"analysis": s3, "valuation": s4})
        package = self._assemble_package(market, s3, s4, s5, request)
        translations = await self._translate(package)
        translation_notes = self._apply_translations(package, translations)
        self._set_generation_metadata(package, translation_notes)
        validate_package(self._root, package)
        decks: dict[str, JsonDict] = {
            edition: await self._deck(package, edition) for edition in request.editions
        }
        validate_decks(self._root, package, decks)
        return self._write_artifacts(output_dir.resolve(), package, decks)

    def _one_task(self, stage: str) -> str:
        tasks = self._tasks_by_stage[stage]
        if len(tasks) != 1:
            raise ValueError(f"stage {stage} must bind exactly one registered task")
        return tasks[0].task_name

    async def _market_data(self, request: DemoRequest) -> JsonDict:
        symbol = NormalizedSymbol(
            original=request.symbol,
            canonical="600XXX.SS",
            provider_symbol="600XXX",
            market=Market.CN_A,
            exchange=Exchange.SSE,
        )
        provider = AkshareMarketDataProvider(FixtureAkshareClient(), clock=fixed_clock)
        result = await provider.fetch(
            ProviderRequest(
                symbol=symbol, capability=MarketDataCapability.QUOTE, metric_id_start=14
            ),
            SourceRegistry(),
        )
        provider_fragments = result.as_research_fragments()
        provider_sources = cast(list[JsonDict], provider_fragments["sources"])
        provider_metrics = cast(list[JsonDict], provider_fragments["metrics"])
        if len(provider_sources) != 1 or len(provider_metrics) != 1:
            raise PipelineConfigurationError(
                "invalid_mock_provider_output",
                "the fictional quote provider must produce exactly one source and one metric",
            )
        source = copy.deepcopy(provider_sources[0])
        metric = copy.deepcopy(provider_metrics[0])
        source["source_id"] = "SRC-002"
        metric["source_id"] = "SRC-002"
        fixture = load_json(self._root / "packages/presentation/fixtures/mock-package.json")
        sources = self._replace_fixture_record(
            fixture["sources"], "source_id", "SRC-002", source
        )
        metrics = self._replace_fixture_record(
            fixture["metrics"], "metric_id", "MET-014", metric
        )
        return {"sources": sources, "metrics": metrics}

    @staticmethod
    def _replace_fixture_record(
        records: Any, identifier: str, expected_id: str, replacement: JsonDict
    ) -> list[JsonDict]:
        if not isinstance(records, list):
            raise PipelineConfigurationError(
                "invalid_mock_fixture",
                f"the mock fixture must provide a {identifier} record for {expected_id}",
            )
        matches = [
            index
            for index, item in enumerate(records)
            if isinstance(item, dict) and item.get(identifier) == expected_id
        ]
        if len(matches) != 1:
            raise PipelineConfigurationError(
                "invalid_mock_fixture",
                f"the mock fixture must contain exactly one {identifier}={expected_id}",
            )
        copied = copy.deepcopy(records)
        copied[matches[0]] = replacement
        return cast(list[JsonDict], copied)

    async def _execute(self, task_name: str, structured_input: JsonDict) -> JsonDict:
        task = self._catalog.resolve(task_name)
        if task.input_schema is not None:
            input_feedback = validate_instance(
                structured_input, task.input_schema, stage=task.stage
            )
            if input_feedback:
                raise LLMProviderError(
                    code="input_schema_mismatch",
                    retryable=False,
                    message="scheduler rejected structured input",
                    attempt_count=0,
                )
        attempts: list[AttemptRecord] = []
        feedback: tuple[ValidationFeedback, ...] = ()
        for attempt_number in range(1, self._max_attempts + 1):
            try:
                result = await self._llm.run(
                    task_name, structured_input, task.output_schema, validator_feedback=feedback
                )
                schema_feedback = validate_instance(
                    result.output, task.output_schema, stage=task.stage
                )
                if schema_feedback:
                    raise LLMProviderError(
                        code="schema_validation_failed",
                        retryable=True,
                        message="mock output failed local validation",
                        attempt_count=attempt_number,
                    )
                attempts.append(
                    AttemptRecord(
                        attempt=attempt_number,
                        status=InvocationStatus.SUCCEEDED,
                        returned_model=result.returned_model,
                        latency_ms=result.latency_ms,
                    )
                )
                self._results.append(result)
                self._record(
                    task.stage,
                    task_name,
                    task.prompt_version,
                    InvocationStatus.SUCCEEDED,
                    attempts,
                    result.output,
                )
                return copy.deepcopy(result.output)
            except LLMProviderError as error:
                status = (
                    InvocationStatus.RETRYABLE_FAILED
                    if error.retryable
                    else InvocationStatus.NON_RETRYABLE_FAILED
                )
                attempts.append(
                    AttemptRecord(
                        attempt=attempt_number,
                        status=status,
                        code=error.code,
                        retryable=error.retryable,
                    )
                )
                if not error.retryable:
                    self._record(task.stage, task_name, task.prompt_version, status, attempts, None)
                    raise
                if attempt_number == self._max_attempts:
                    self._record(task.stage, task_name, task.prompt_version, status, attempts, None)
                    raise RetryExhaustedError(attempt_number, error.code) from None
                feedback = (
                    ValidationFeedback(
                        code=error.code,
                        stage=task.stage,
                        path="/",
                        retryable=True,
                        detail="previous fixture attempt failed; retry this invocation only",
                    ),
                )
        raise AssertionError("retry loop is exhaustive")

    def _record(
        self,
        stage: str,
        task_name: str,
        prompt_version: str,
        status: InvocationStatus,
        attempts: list[AttemptRecord],
        output: JsonDict | None,
    ) -> None:
        sequence = len(self._checkpoints) + 1
        digest = self._digest(output) if output is not None else None
        self._checkpoints.append(
            Checkpoint(
                sequence=sequence,
                invocation_id=f"{stage}.{task_name}.{sequence:03d}",
                stage=stage,
                task_name=task_name,
                prompt_version=prompt_version,
                status=status,
                attempt_count=len(attempts),
                attempts=tuple(attempts),
                output_sha256=digest,
            )
        )

    def _assemble_package(
        self,
        market: JsonDict,
        s3: JsonDict,
        s4: JsonDict,
        s5: JsonDict,
        request: DemoRequest,
    ) -> JsonDict:
        package = load_json(self._root / "packages/presentation/fixtures/mock-package.json")
        package["status"] = "verified"
        package["company"]["name"] = request.company_name
        package["company"]["exchange"] = request.exchange
        package["as_of_date"] = request.as_of_date.isoformat()
        package["sources"] = market["sources"]
        package["metrics"] = market["metrics"]
        generated_claims: dict[str, JsonDict] = {}
        for output in s3.values():
            generated_claims.update({claim["claim_id"]: claim for claim in output["claims"]})
        for claim in s4["claims"] + s5["supporting_claims"]:
            generated_claims[claim["claim_id"]] = claim
        package["claims"] = [
            generated_claims.get(claim["claim_id"], claim) for claim in package["claims"]
        ]
        package["catalysts"] = s5["catalysts"]
        package["risks"] = s5["risks"]
        return package

    async def _translate(self, package: JsonDict) -> list[JsonDict]:
        texts = self._localized_texts(package)
        task_name = self._one_task("S6")
        task = self._catalog.resolve(task_name)
        raw_limit = task.batching.get("max_texts_per_call") if task.batching else 20
        if not isinstance(raw_limit, int):
            raise ValueError("translation batch size must be an integer")
        limit = raw_limit
        outputs: list[JsonDict] = []
        for start in range(0, len(texts), limit):
            batch = texts[start : start + limit]
            outputs.append(
                await self._execute(
                    task_name,
                    {
                        "authoritative_language": "zh_CN",
                        "glossary": "packages/prompts/glossary.md",
                        "texts": batch,
                    },
                )
            )
        return outputs

    @staticmethod
    def _localized_texts(package: JsonDict) -> list[JsonDict]:
        texts: list[JsonDict] = []

        def visit(value: Any, path: str) -> None:
            if isinstance(value, dict):
                if set(value) == {"zh_CN", "en_AU"}:
                    texts.append({"path": path, "zh_CN": value["zh_CN"], "en_AU": value["en_AU"]})
                else:
                    for key in sorted(value):
                        visit(value[key], f"{path}.{key}" if path else key)
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    visit(item, f"{path}[{index}]")

        visit(package, "")
        return texts

    @staticmethod
    def _localized_text_targets(package: JsonDict) -> list[tuple[str, JsonDict]]:
        targets: list[tuple[str, JsonDict]] = []

        def visit(value: Any, path: str) -> None:
            if isinstance(value, dict):
                if set(value) == {"zh_CN", "en_AU"}:
                    targets.append((path, cast(JsonDict, value)))
                else:
                    for key in sorted(value):
                        visit(value[key], f"{path}.{key}" if path else key)
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    visit(item, f"{path}[{index}]")

        visit(package, "")
        return targets

    @staticmethod
    def _apply_translations(package: JsonDict, batches: list[JsonDict]) -> tuple[str, ...]:
        targets = MockResearchOrchestrator._localized_text_targets(package)
        targets_by_path = {path: value for path, value in targets}
        translated_by_path: dict[str, JsonDict] = {}
        translated_languages: dict[str, str] = {}
        translation_flags: list[JsonDict] = []
        glossary_flags: list[JsonDict] = []
        for batch in batches:
            authoritative_language = batch.get("authoritative_language")
            if authoritative_language not in {"zh_CN", "en_AU"}:
                raise ValueError(
                    "translation batch must declare a supported authoritative language"
                )
            translated_language = "en_AU" if authoritative_language == "zh_CN" else "zh_CN"
            for item in batch["texts"]:
                path = item["path"]
                target = targets_by_path.get(path)
                if target is None:
                    raise ValueError(f"translation batch contains an unknown path: {path}")
                if path in translated_by_path:
                    raise ValueError(f"translation batch contains a duplicate path: {path}")
                if item[authoritative_language] != target[authoritative_language]:
                    raise ValueError(
                        f"translation batch changed authoritative content at path: {path}"
                    )
                if (
                    MockResearchOrchestrator._protected_translation_tokens(
                        item[translated_language]
                    )
                    != MockResearchOrchestrator._protected_translation_tokens(
                        target[translated_language]
                    )
                ):
                    raise ValueError(
                        "translation batch changed protected identifiers or numeric values "
                        f"at path: {path}"
                    )
                translated_by_path[path] = item
                translated_languages[path] = translated_language
            translation_flags.extend(cast(list[JsonDict], batch["translation_flags"]))
            glossary_flags.extend(cast(list[JsonDict], batch["glossary_flags"]))
        missing_paths = [path for path, _ in targets if path not in translated_by_path]
        if missing_paths:
            raise ValueError(f"translation batch is missing path: {missing_paths[0]}")
        review_notes = MockResearchOrchestrator._translation_review_notes(
            translation_flags, glossary_flags, set(targets_by_path)
        )
        for path, target in targets:
            translated = translated_by_path[path]
            target[translated_languages[path]] = translated[translated_languages[path]]
        return review_notes

    @staticmethod
    def _protected_translation_tokens(text: Any) -> tuple[str, ...]:
        if not isinstance(text, str):
            raise ValueError("translation batch text must be a string")
        return tuple(
            re.findall(
                r"(?<![A-Za-z0-9_])(?:MET|CLM|SRC|ASM|RSK|CAT)-\d{3}(?![A-Za-z0-9_])"
                r"|(?<![A-Za-z0-9_])\d+(?:\.\d+)?%?(?![A-Za-z0-9_])",
                text,
            )
        )

    @staticmethod
    def _translation_review_notes(
        translation_flags: list[JsonDict], glossary_flags: list[JsonDict], known_paths: set[str]
    ) -> tuple[str, ...]:
        def require_known_path(flag: JsonDict) -> str:
            path = flag["path"]
            if not isinstance(path, str):
                raise ValueError("translation review flag path must be a string")
            if path not in known_paths:
                raise ValueError(f"translation review flag contains an unknown path: {path}")
            return path

        notes = [
            f"translation_flag path={require_known_path(flag)} problem={flag['problem']}"
            for flag in translation_flags
        ]
        notes.extend(
            "glossary_flag "
            f"path={require_known_path(flag)} term={flag['term']} "
            f"proposed_mapping={flag['proposed_mapping']}"
            for flag in glossary_flags
        )
        return tuple(sorted(notes))

    def _set_generation_metadata(
        self, package: JsonDict, translation_notes: tuple[str, ...]
    ) -> None:
        notes = (
            "Offline fixture-only run; no network or credentials used; "
            "human approval not performed."
        )
        if translation_notes:
            notes += " Translation and glossary review flags: " + " | ".join(translation_notes)
        package["generation_metadata"] = {
            "pipeline_version": "issue-26-offline-v1",
            "prompt_versions": {
                result.task_name: result.prompt_version for result in self._results
            },
            "llm_calls": [
                {
                    "task": result.task_name,
                    "requested_model": result.requested_model,
                    "returned_model": result.returned_model,
                    "latency_ms": result.latency_ms,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                }
                for result in self._results
            ],
            "notes": notes,
        }

    async def _deck(self, package: JsonDict, edition: str) -> JsonDict:
        deck_id = f"DCK-600XXX-2026-002-{'ZH' if edition == 'zh-CN' else 'EN'}"
        plan_task, slide_task = self._s7_task_names()
        plan = await self._execute(
            plan_task,
            {
                "edition": edition,
                "package": package,
                "layout_limits": "packages/presentation/layouts.md",
                "deck_id": deck_id,
            },
        )
        slides: list[JsonDict] = []
        for stub in plan["slide_stubs"]:
            excerpt = self._excerpt(package, stub)
            slides.append(
                await self._execute(
                    slide_task,
                    {
                        "slide_stub": stub,
                        "deck_context": {
                            "deck_id": plan["deck_id"],
                            "package_id": plan["package_id"],
                            "edition": plan["edition"],
                            "as_of_date": plan["as_of_date"],
                            "theme": plan.get("theme", "jacaranda-brand"),
                        },
                        "package_excerpt": excerpt,
                    },
                )
            )
        return {
            "schema_version": "0.1.0",
            **{key: value for key, value in plan.items() if key != "slide_stubs"},
            "slides": slides,
        }

    def _s7_task_names(self) -> tuple[str, str]:
        required = ("slide_compression_plan", "slide_compression_slide")
        selected: list[str] = []
        for task_name in required:
            count = sum(
                task.task_name == task_name for task in self._tasks_by_stage["S7"]
            )
            if count != 1:
                state = "missing" if count == 0 else "duplicated"
                raise PipelineConfigurationError(
                    "invalid_s7_task_registry",
                    f"{state} required S7 task: {task_name}",
                )
            selected.append(task_name)
        return selected[0], selected[1]

    @staticmethod
    def _excerpt(package: JsonDict, stub: JsonDict) -> JsonDict:
        metric_ids = set(stub["metric_ids"])
        claim_ids = set(stub["claim_ids"])
        metrics = [item for item in package["metrics"] if item["metric_id"] in metric_ids]
        claims = [item for item in package["claims"] if item["claim_id"] in claim_ids]
        source_ids = {item["source_id"] for item in metrics}
        for claim in claims:
            source_ids.update(claim.get("source_ids", []))
        return {
            "metrics": metrics,
            "claims": claims,
            "sources": [item for item in package["sources"] if item["source_id"] in source_ids],
            "assumptions": package["valuation"]["assumptions"],
            "valuation_refs": {
                "target_price_metric_id": package["valuation"]["target_price_metric_id"],
                "current_price_metric_id": package["valuation"]["current_price_metric_id"],
                "rating": package["valuation"]["rating"],
            },
        }

    def _write_artifacts(
        self, root: Path, package: JsonDict, decks: dict[str, JsonDict]
    ) -> PipelineArtifacts:
        audit = root / "audit"
        audit.mkdir(parents=True)
        package_path = root / "research-package.json"
        self._write_json(package_path, package)
        deck_paths: dict[str, Path] = {}
        pptx_paths: dict[str, Path] = {}
        report_paths: dict[str, Path] = {}
        reports: dict[str, JsonDict] = {}
        for edition, deck in decks.items():
            slug = edition.lower()
            deck_paths[edition] = root / f"slide-deck.{edition}.json"
            pptx_paths[edition] = root / f"report.{edition}.pptx"
            report_paths[edition] = root / f"overflow-{slug}.json"
            self._write_json(deck_paths[edition], deck)
            result = self._presentation.render(deck, package, pptx_paths[edition])
            reports[edition] = result.overflow_report
            self._write_json(report_paths[edition], reports[edition])
        checkpoint_path = audit / "checkpoints.json"
        self._write_json(
            checkpoint_path,
            {"checkpoints": [item.model_dump(mode="json") for item in self._checkpoints]},
        )
        manifest_path = root / "manifest.json"
        json_paths = [package_path, *deck_paths.values(), *report_paths.values(), checkpoint_path]
        manifest = {
            "run_id": "MOCK-RUN-20260710-001",
            "network": "socket-blocked",
            "status": "verified",
            "artifacts": [
                {
                    "path": str(path.relative_to(root)),
                    "sha256": self._digest_bytes(path.read_bytes()),
                }
                for path in json_paths
            ]
            + [
                {"path": str(path.relative_to(root)), "kind": "editable-pptx"}
                for path in pptx_paths.values()
            ],
        }
        self._write_json(manifest_path, manifest)
        return PipelineArtifacts(
            root=root,
            research_package=package_path,
            deck_json=deck_paths,
            pptx=pptx_paths,
            overflow_reports=report_paths,
            manifest=manifest_path,
            checkpoints=checkpoint_path,
        )

    @staticmethod
    def _prepare_output(output_dir: Path) -> None:
        resolved = output_dir.resolve()
        if (
            ".." in output_dir.parts
            or output_dir.is_symlink()
            or (resolved.exists() and any(resolved.iterdir()))
        ):
            raise ValueError("output directory must be new or empty and must not be a symlink")
        resolved.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    @staticmethod
    def _digest(value: Any) -> str:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        return MockResearchOrchestrator._digest_bytes(encoded)

    @staticmethod
    def _digest_bytes(value: bytes) -> str:
        return hashlib.sha256(value).hexdigest()


def run_pipeline(repository_root: Path, output_dir: Path) -> PipelineArtifacts:
    return asyncio.run(MockResearchOrchestrator(repository_root).run(DemoRequest(), output_dir))
