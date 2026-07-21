from __future__ import annotations

import asyncio
import copy
import hashlib
import json
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
        self._apply_translations(package, translations)
        self._set_generation_metadata(package)
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
        source = cast(list[JsonDict], provider_fragments["sources"])[0]
        metric = cast(list[JsonDict], provider_fragments["metrics"])[0]
        source["source_id"] = "SRC-002"
        metric["source_id"] = "SRC-002"
        fixture = load_json(self._root / "packages/presentation/fixtures/mock-package.json")
        fixture["sources"][1] = source
        fixture["metrics"] = [
            metric if item["metric_id"] == "MET-014" else item for item in fixture["metrics"]
        ]
        return {"sources": fixture["sources"], "metrics": fixture["metrics"]}

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
    def _apply_translations(package: JsonDict, batches: list[JsonDict]) -> None:
        expected = {item["path"] for item in MockResearchOrchestrator._localized_texts(package)}
        actual = {item["path"] for batch in batches for item in batch["texts"]}
        if actual != expected:
            raise ValueError("translation batch merge did not preserve every unique path")

    def _set_generation_metadata(self, package: JsonDict) -> None:
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
            "notes": (
                "Offline fixture-only run; no network or credentials used; "
                "human approval not performed."
            ),
        }

    async def _deck(self, package: JsonDict, edition: str) -> JsonDict:
        deck_id = f"DCK-600XXX-2026-002-{'ZH' if edition == 'zh-CN' else 'EN'}"
        plan_tasks = self._tasks_by_stage["S7"]
        plan_task = next(task.task_name for task in plan_tasks if task.input_schema is None)
        slide_task = next(task.task_name for task in plan_tasks if task.input_schema is not None)
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
