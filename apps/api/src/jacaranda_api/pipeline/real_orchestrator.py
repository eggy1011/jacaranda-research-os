from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import cast

from jacaranda_api.llm.contracts import LLMProvider
from jacaranda_api.market_data.adapters.akshare import AkshareClient
from jacaranda_api.pipeline.assembly import (
    build_company_block,
    build_disclaimer,
    build_evidence_chunks,
    build_sections,
    collect_section_assignments,
    map_verified_candidates,
)
from jacaranda_api.pipeline.calc import ValuationCalc
from jacaranda_api.pipeline.evidence import build_evidence_pack
from jacaranda_api.pipeline.models import JsonDict, PipelineArtifacts
from jacaranda_api.pipeline.orchestrator import StageOrchestrator
from jacaranda_api.pipeline.presentation import (
    PresentationProvider,
    TemplatePresentationProvider,
)
from jacaranda_api.pipeline.quality import evaluate_quality
from jacaranda_api.pipeline.upload_evidence import merge_upload_evidence
from jacaranda_api.pipeline.validation import (
    SemanticValidationError,
    validate_decks,
    validate_real_package,
)

PIPELINE_VERSION = "real-v1"

# (stage_key, status) — status is one of started/completed/cached/failed.
StageListener = Callable[[str, str], Awaitable[None]]


class RealResearchOrchestrator(StageOrchestrator):
    """Live wiring of the shared stage machinery: real AKShare evidence, real
    LLM calls, deterministic valuation, and a draft package that stops short of
    human review. Every completed step is checkpointed to disk so an
    interrupted run resumes from the last finished stage instead of re-spending
    model calls."""

    network_label = "live"

    def __init__(
        self,
        repository_root: Path,
        *,
        llm: LLMProvider,
        akshare_client: AkshareClient,
        presentation: PresentationProvider | None = None,
        max_attempts: int = 3,
        stage_listener: StageListener | None = None,
    ) -> None:
        root = repository_root.resolve()
        super().__init__(
            root,
            llm=llm,
            presentation=presentation or TemplatePresentationProvider(root),
            max_attempts=max_attempts,
        )
        self._akshare_client = akshare_client
        self._stage_listener = stage_listener
        self._cache_dir: Path | None = None
        self._symbol_code = ""
        self._year = ""

    async def run(
        self,
        symbol: str,
        output_dir: Path,
        *,
        resume: bool = False,
        uploads: list[JsonDict] | None = None,
    ) -> PipelineArtifacts:
        resolved = output_dir.resolve()
        if resume:
            resolved.mkdir(parents=True, exist_ok=True)
        else:
            self._prepare_output(resolved)
        self._cache_dir = resolved / "checkpoints"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        evidence = await self._cached(
            "00-evidence",
            lambda: build_evidence_pack(symbol, self._akshare_client),
        )
        evidence, upload_chunks = merge_upload_evidence(evidence, uploads or [])
        self._symbol_code = evidence["symbol"]["provider_symbol"]
        self._year = evidence["generated_at"][:4]
        self.run_id = f"RUN-{self._symbol_code}-{evidence['generated_at'][:10]}"

        chunks = [*build_evidence_chunks(evidence), *upload_chunks]
        company = build_company_block(evidence)
        as_of_date = cast(str, evidence["generated_at"][:10])

        s1 = await self._cached(
            "01-extraction",
            lambda: self._execute(
                self._one_task("S1"),
                {
                    "company_context": {
                        "name": evidence["company"]["name_zh"],
                        "ticker": evidence["symbol"]["canonical"],
                        "market": evidence["symbol"]["market"],
                    },
                    "evidence_chunks": chunks,
                },
            ),
        )
        s2 = await self._cached(
            "02-source-verification",
            lambda: self._execute(
                self._one_task("S2"),
                {
                    "as_of_date": as_of_date,
                    "sources": self._verification_sources(evidence, chunks),
                    "candidates": {
                        "candidate_metrics": s1["candidate_metrics"],
                        "candidate_claims": s1["candidate_claims"],
                    },
                },
            ),
        )

        fact_claims, _, held = map_verified_candidates(s1, s2, next_claim_number=1)
        if not fact_claims:
            raise SemanticValidationError(
                "no candidate fact survived source verification; the run cannot continue"
            )
        if len(fact_claims) > 19:
            raise SemanticValidationError(
                "too many promoted facts for the CLM-001..019 block; adjust numbering"
            )

        calc = ValuationCalc().compute(
            evidence, metric_id_start=len(evidence["metrics"]) + 1
        )
        metrics: list[JsonDict] = [*evidence["metrics"], *calc["metrics"]]

        claims: list[JsonDict] = list(fact_claims)
        s3: dict[str, JsonDict] = {}
        for stage in ("S3a", "S3b", "S3c", "S3d"):
            stage_input: JsonDict = {
                "company": company,
                "verified_metrics": metrics,
                "verified_fact_claims": fact_claims,
                "next_claim_id": self._next_claim_id(claims),
            }
            output = await self._cached(
                f"03-{stage}", partial(self._execute, self._one_task(stage), stage_input)
            )
            output = self._rebase_stage_claims(output, "claims", claims)
            s3[stage] = output
            self._merge_claims(claims, cast(list[JsonDict], output["claims"]))

        s4 = await self._cached(
            "04-valuation-narrative",
            lambda: self._execute(
                self._one_task("S4"),
                {
                    "valuation_metrics": calc["metrics"],
                    "assumptions": [
                        {
                            "assumption_id": item["assumption_id"],
                            "name_authored": item["name"]["zh_CN"],
                            "value_text": item["value_text"],
                        }
                        for item in calc["assumptions"]
                    ],
                    "scenario_metrics": calc["scenario_metrics"],
                    "prior_claims": claims,
                    "next_claim_id": self._next_claim_id(claims),
                },
            ),
        )
        s4 = self._rebase_stage_claims(s4, "claims", claims)
        self._merge_claims(claims, cast(list[JsonDict], s4["claims"]))
        self._flag_counterevidence(claims, cast(list[str], s4["counterevidence_claim_ids"]))

        s5 = await self._cached(
            "05-catalysts-risks",
            lambda: self._execute(
                self._one_task("S5"),
                {
                    "as_of_date": as_of_date,
                    "prior_claims": claims,
                    "verified_metrics": metrics,
                    "next_ids": {
                        "claim": self._next_claim_id(claims),
                        "catalyst": "CAT-001",
                        "risk": "RSK-001",
                    },
                },
            ),
        )
        s5 = self._rebase_stage_claims(s5, "supporting_claims", claims)
        self._merge_claims(claims, cast(list[JsonDict], s5["supporting_claims"]))

        valuation = self._build_valuation(calc, s4)
        sections = build_sections(
            section_assignments=collect_section_assignments(s3),
            fact_claim_ids=[claim["claim_id"] for claim in fact_claims],
            rating_claim_id=cast(str, s4["rating_claim_id"]),
            counterevidence_claim_ids=cast(list[str], s4["counterevidence_claim_ids"]),
            scenario_claim_ids=[
                scenario["narrative_claim_id"]
                for scenario in cast(dict[str, JsonDict], valuation["scenarios"]).values()
            ],
            catalyst_claim_ids=[item["claim_id"] for item in s5["catalysts"]],
            risk_claim_ids=[item["claim_id"] for item in s5["risks"]],
            key_metric_ids={
                "company_snapshot": [m["metric_id"] for m in evidence["metrics"][:4]],
                "historical_financials": [
                    m["metric_id"] for m in evidence["metrics"] if m["period"] != "PIT"
                ],
                "valuation": [m["metric_id"] for m in calc["metrics"]],
            },
        )

        package: JsonDict = {
            "schema_version": "0.1.0",
            "package_id": f"RPK-{self._symbol_code}-{self._year}-001",
            "status": "draft",
            "as_of_date": as_of_date,
            "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "company": company,
            "sources": evidence["sources"],
            "metrics": metrics,
            "claims": claims,
            "sections": sections,
            "valuation": valuation,
            "catalysts": s5["catalysts"],
            "risks": s5["risks"],
            "disclaimer": build_disclaimer(as_of_date),
            "quality": {"rubric_version": "0.1.0", "checks": []},
            "generation_metadata": {"pipeline_version": PIPELINE_VERSION},
        }

        translations = await self._cached_list("06-translation", lambda: self._translate(package))
        translation_notes = self._apply_translations(package, translations)

        warnings = [*cast(list[str], evidence["warnings"])]
        if held:
            # Count only: raw CCLM ids would trip the package-wide reference scan.
            warnings.append(f"extraction candidates held for human review: {len(held)}")
        package["quality"] = evaluate_quality(package, evidence_warnings=warnings)
        self._set_generation_metadata(package, translation_notes, warnings)
        validate_real_package(self._root, package)

        decks: dict[str, JsonDict] = {}
        for edition in ("zh-CN", "en-AU"):
            decks[edition] = await self._cached(
                f"07-deck-{edition}", partial(self._deck, package, edition)
            )
        validate_decks(self._root, package, decks)
        return self._write_artifacts(resolved, package, decks)

    def _deck_id(self, edition: str) -> str:
        suffix = "ZH" if edition == "zh-CN" else "EN"
        return f"DCK-{self._symbol_code}-{self._year}-001-{suffix}"

    async def _notify(self, key: str, status: str) -> None:
        if self._stage_listener is not None:
            await self._stage_listener(key, status)

    async def _cached(self, key: str, thunk: Callable[[], Awaitable[JsonDict]]) -> JsonDict:
        cached = self._cache_load(key)
        if cached is not None:
            await self._notify(key, "cached")
            return cast(JsonDict, cached)
        await self._notify(key, "started")
        try:
            value = await thunk()
        except Exception:
            await self._notify(key, "failed")
            raise
        self._cache_store(key, value)
        await self._notify(key, "completed")
        return value

    async def _cached_list(
        self, key: str, thunk: Callable[[], Awaitable[list[JsonDict]]]
    ) -> list[JsonDict]:
        cached = self._cache_load(key)
        if cached is not None:
            await self._notify(key, "cached")
            return cast(list[JsonDict], cached)
        await self._notify(key, "started")
        try:
            value = await thunk()
        except Exception:
            await self._notify(key, "failed")
            raise
        self._cache_store(key, value)
        await self._notify(key, "completed")
        return value

    def _cache_load(self, key: str) -> object | None:
        if self._cache_dir is None:
            return None
        path = self._cache_dir / f"{key}.json"
        if not path.is_file():
            return None
        return cast(object, json.loads(path.read_text(encoding="utf-8")))

    def _cache_store(self, key: str, value: object) -> None:
        if self._cache_dir is None:
            return
        self._write_json(self._cache_dir / f"{key}.json", value)

    @staticmethod
    def _verification_sources(evidence: JsonDict, chunks: list[JsonDict]) -> list[JsonDict]:
        texts_by_source: dict[str, dict[str, str]] = {}
        for chunk in chunks:
            texts_by_source.setdefault(str(chunk["source_id"]), {})[
                str(chunk["locator"])
            ] = str(chunk["text"])
        sources: list[JsonDict] = []
        for source in evidence["sources"]:
            sources.append(
                {
                    "source_id": source["source_id"],
                    "type": source["type"],
                    "reliability_tier": source["reliability_tier"],
                    "published_date": source.get("published_date"),
                    "title": source["title"],
                    "text_by_locator": texts_by_source.get(str(source["source_id"]), {}),
                }
            )
        return sources

    @staticmethod
    def _next_claim_number(claims: list[JsonDict]) -> int:
        numbers = [
            int(str(claim["claim_id"])[4:])
            for claim in claims
            if str(claim.get("claim_id", "")).startswith("CLM-")
        ]
        return (max(numbers) + 1) if numbers else 1

    @classmethod
    def _next_claim_id(cls, claims: list[JsonDict]) -> str:
        """Running counter for the next free CLM- id, handed to a stage as its
        numbering hint. Each stage was previously handed a fixed 10-id block
        (S3a=020, S3b=030, …), but a live model sizes a stage's claims to the
        evidence, not to that block; deriving the hint from the ids already
        assigned steers the model away from the next stage's range."""
        return f"CLM-{cls._next_claim_number(claims):03d}"

    @classmethod
    def _remap_claim_ids(cls, value: object, mapping: dict[str, str]) -> object:
        if isinstance(value, str):
            return mapping.get(value, value)
        if isinstance(value, list):
            return [cls._remap_claim_ids(item, mapping) for item in value]
        if isinstance(value, dict):
            return {key: cls._remap_claim_ids(item, mapping) for key, item in value.items()}
        return value

    def _rebase_stage_claims(
        self, output: JsonDict, claims_key: str, existing: list[JsonDict]
    ) -> JsonDict:
        """Enforce collision-free claim ids even when a live model ignores the
        numbering hint. A hint steers the model but does not bind it, so a stage
        can still emit an id already taken by an earlier stage. Only when that
        happens are the stage's own claims rebased onto a fresh contiguous block
        and every reference to them inside this stage's output remapped; the
        collision-free happy path is returned untouched."""
        stage_ids = [
            str(claim["claim_id"]) for claim in cast(list[JsonDict], output.get(claims_key, []))
        ]
        existing_ids = {str(claim["claim_id"]) for claim in existing}
        if not any(stage_id in existing_ids for stage_id in stage_ids):
            return output
        base = self._next_claim_number(existing)
        mapping = {old: f"CLM-{base + offset:03d}" for offset, old in enumerate(stage_ids)}
        return cast(JsonDict, self._remap_claim_ids(output, mapping))

    @staticmethod
    def _merge_claims(claims: list[JsonDict], new_claims: list[JsonDict]) -> None:
        existing = {claim["claim_id"] for claim in claims}
        for claim in new_claims:
            if claim["claim_id"] in existing:
                raise SemanticValidationError(
                    f"stage output reused an existing claim id: {claim['claim_id']}"
                )
            existing.add(claim["claim_id"])
            claims.append(claim)

    @staticmethod
    def _flag_counterevidence(claims: list[JsonDict], counter_ids: list[str]) -> None:
        known = {claim["claim_id"]: claim for claim in claims}
        for claim_id in counter_ids:
            claim = known.get(claim_id)
            if claim is None:
                raise SemanticValidationError(
                    f"counterevidence references an unknown claim: {claim_id}"
                )
            claim["is_counterevidence"] = True

    @staticmethod
    def _build_valuation(calc: JsonDict, s4: JsonDict) -> JsonDict:
        rationales = {
            item["assumption_id"]: item["rationale_claim_id"]
            for item in cast(list[JsonDict], s4["assumption_rationales"])
        }
        assumptions: list[JsonDict] = []
        for item in cast(list[JsonDict], calc["assumptions"]):
            rationale = rationales.get(item["assumption_id"])
            if rationale is None:
                raise SemanticValidationError(
                    f"S4 provided no rationale for assumption {item['assumption_id']}"
                )
            assumptions.append({**item, "rationale_claim_id": rationale})
        scenario_narratives = cast(dict[str, str], s4["scenario_narratives"])
        base_narrative = scenario_narratives.get("base")
        if base_narrative is None:
            raise SemanticValidationError("S4 provided no base scenario narrative")
        scenarios: JsonDict = {
            "base": {
                "narrative_claim_id": base_narrative,
                "target_price_metric_id": calc["target_price_metric_id"],
            }
        }
        return {
            "methods": [calc["method"]],
            "assumptions": assumptions,
            "scenarios": scenarios,
            "rating": s4["rating"],
            "counterevidence_claim_ids": s4["counterevidence_claim_ids"],
            "target_price_metric_id": calc["target_price_metric_id"],
            "current_price_metric_id": calc["current_price_metric_id"],
        }

    def _set_generation_metadata(
        self, package: JsonDict, translation_notes: tuple[str, ...], warnings: list[str]
    ) -> None:
        notes = "Live run; draft pending human review."
        if warnings:
            notes += " Warnings: " + " | ".join(warnings)
        if translation_notes:
            notes += " Translation and glossary review flags: " + " | ".join(translation_notes)
        package["generation_metadata"] = {
            "pipeline_version": PIPELINE_VERSION,
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
