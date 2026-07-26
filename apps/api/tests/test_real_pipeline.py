from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest

from jacaranda_api.llm.models import JsonValue, LLMAttemptMetadata, LLMResult, ValidationFeedback
from jacaranda_api.pipeline.assembly import (
    build_evidence_chunks,
    build_sections,
    map_verified_candidates,
)
from jacaranda_api.pipeline.calc import DeterministicCalcError, ValuationCalc
from jacaranda_api.pipeline.cli_real import main as real_main
from jacaranda_api.pipeline.models import JsonDict, PresentationResult
from jacaranda_api.pipeline.real_orchestrator import RealResearchOrchestrator
from jacaranda_api.pipeline.validation import (
    SemanticValidationError,
    load_json,
    validate_real_package,
    validate_renderable_package,
)

ROOT = Path(__file__).resolve().parents[3]


class EvidenceClient:
    """Payload-level AkshareClient double producing a complete evidence pack."""

    async def fetch_quote(self, symbol: str) -> Mapping[str, object]:
        return {"latest": 100.0, "trade_date": date(2026, 7, 24), "currency": "CNY"}

    async def fetch_financial_indicators(self, symbol: str) -> Mapping[str, object]:
        common = {"period": "FY2025", "as_of_date": date(2025, 12, 31)}
        return {
            "records": [
                {
                    "field": "total_revenue",
                    "name_zh": "营业总收入",
                    "name_en": "Total operating revenue",
                    "value": 5_000_000_000.0,
                    "unit": "CNY",
                    "currency": "CNY",
                    **common,
                },
                {
                    "field": "basic_eps",
                    "name_zh": "基本每股收益",
                    "name_en": "Basic earnings per share",
                    "value": 5.0,
                    "unit": "CNY/share",
                    "currency": "CNY",
                    **common,
                },
                {
                    "field": "gross_margin",
                    "name_zh": "毛利率",
                    "name_en": "Gross margin",
                    "value": None,
                    "unit": "%",
                    "currency": None,
                    **common,
                },
            ]
        }

    async def fetch_company_profile(self, symbol: str) -> Mapping[str, object]:
        return {
            "name_zh": "测试制造股份有限公司",
            "name_en": "Test Manufacturing Co., Ltd.",
            "industry": "高端制造",
            "listing_date": date(2010, 1, 4),
        }


def _text(zh: str, en: str | None = None) -> JsonDict:
    return {"zh_CN": zh, "en_AU": en or zh}


def _claim(
    claim_id: str,
    claim_type: str,
    zh: str,
    *,
    source_ids: list[str] | None = None,
    metric_ids: list[str] | None = None,
    based_on: list[str] | None = None,
) -> JsonDict:
    claim: JsonDict = {
        "claim_id": claim_id,
        "type": claim_type,
        "text": _text(zh),
        "review_status": "unreviewed",
    }
    if source_ids:
        claim["source_ids"] = source_ids
    if metric_ids:
        claim["metric_ids"] = metric_ids
    if based_on:
        claim["based_on_claim_ids"] = based_on
    return claim


# Twelve stubs: cover first, conclusion last, mandatory sections included.
_STUB_PLAN: tuple[tuple[str, str, list[str]], ...] = (
    ("L01_cover", "cover", []),
    ("L02_section_divider", "investment_thesis", ["CLM-063", "CLM-064"]),
    ("L03_kpi_snapshot", "company_snapshot", ["CLM-001"]),
    ("L07_value_chain", "industry_value_chain", ["CLM-030"]),
    ("L04_chart_commentary", "business_model_segments", ["CLM-020"]),
    ("L06_comparison_cards", "competition_moat", ["CLM-050"]),
    ("L05_financial_table", "historical_financials", ["CLM-040"]),
    ("L04_chart_commentary", "forecast_drivers", ["CLM-060"]),
    ("L09_football_field", "valuation", ["CLM-061", "CLM-062"]),
    ("L08_timeline", "catalysts", ["CLM-070"]),
    ("L10_catalysts_risks", "risks", ["CLM-071", "CLM-072", "CLM-073"]),
    ("L11_conclusion_sources", "conclusion_sources_disclaimer", ["CLM-063"]),
)


class FakeRealLLM:
    """Deterministic stand-in for the live provider: derives schema-valid stage
    outputs from the structured input, mirroring what the prompts ask for."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(
        self,
        task_name: str,
        structured_input: Mapping[str, JsonValue],
        output_json_schema: Mapping[str, JsonValue],
        *,
        validator_feedback: Sequence[ValidationFeedback] = (),
    ) -> LLMResult:
        self.calls.append(task_name)
        output = self._output(task_name, cast(dict[str, Any], dict(structured_input)))
        attempt = LLMAttemptMetadata(
            attempt=1,
            returned_model="fake/model:free",
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            finish_status="stop",
        )
        return LLMResult(
            output=output,
            task_name=task_name,
            prompt_version="test",
            requested_model="fake/model:free",
            returned_model="fake/model:free",
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            attempt_count=1,
            finish_status="stop",
            attempts=(attempt,),
        )

    def _output(self, task_name: str, data: dict[str, Any]) -> dict[str, Any]:
        if task_name == "extraction":
            chunks = data["evidence_chunks"]
            profile_chunk = next(
                chunk for chunk in chunks if "公司名称" in chunk["text"]
            )
            quote = profile_chunk["text"].split("\n")[0]
            return {
                "candidate_metrics": [],
                "candidate_claims": [
                    {
                        "candidate_id": "CCLM-001",
                        "type": "fact",
                        "text_original_language": "公司全称为测试制造股份有限公司。",
                        "source_ids": [profile_chunk["source_id"]],
                        "quote": quote,
                    },
                    {
                        "candidate_id": "CCLM-002",
                        "type": "fact",
                        "text_original_language": "公司属于高端制造行业。",
                        "source_ids": [profile_chunk["source_id"]],
                        "quote": quote,
                    },
                    {
                        "candidate_id": "CCLM-003",
                        "type": "fact",
                        "text_original_language": "该说法无法核实。",
                        "source_ids": [profile_chunk["source_id"]],
                        "quote": quote,
                    },
                ],
                "extraction_gaps": [],
            }
        if task_name == "source_verification":
            candidates = data["candidates"]
            verdicts = []
            for item in candidates["candidate_claims"]:
                verified = item["candidate_id"] != "CCLM-003"
                verdicts.append(
                    {
                        "candidate_id": item["candidate_id"],
                        "verdict": "verified" if verified else "needs_review",
                        "checks": {
                            "quote_found": True,
                            "value_matches_quote": True,
                            "source_tier_sufficient": True,
                            "date_fresh": True,
                            "entity_known": verified,
                        },
                        "reasons": [] if verified else ["cannot verify the entity"],
                    }
                )
            return {"verdicts": verdicts, "unverifiable_entities": []}
        if task_name == "company_analysis":
            return {
                "claims": [
                    _claim("CLM-020", "inference", "主营业务结构稳定。", based_on=["CLM-001"])
                ],
                "section_assignment": {"business_model_segments": ["CLM-020"]},
                "insufficient": [],
            }
        if task_name == "industry_analysis":
            return {
                "claims": [
                    _claim("CLM-030", "inference", "行业景气度平稳。", based_on=["CLM-002"])
                ],
                "section_assignment": {"industry_value_chain": ["CLM-030"]},
                "insufficient": [],
                "value_chain_nodes": [
                    {"position": "upstream", "name_authored": "原材料", "highlight": False},
                    {"position": "midstream", "name_authored": "制造", "highlight": True},
                    {"position": "downstream", "name_authored": "销售", "highlight": False},
                ],
                "market_specific_claims": {"cn_policy_context": [], "us_filing_context": []},
            }
        if task_name == "financial_analysis":
            metric_id = data["verified_metrics"][1]["metric_id"]
            return {
                "claims": [
                    _claim("CLM-040", "inference", "收入规模保持增长。", metric_ids=[metric_id])
                ],
                "section_assignment": {"historical_financials": ["CLM-040"]},
                "insufficient": [],
                "requested_calculations": [],
            }
        if task_name == "competition":
            return {
                "claims": [_claim("CLM-050", "inference", "竞争格局分散。", based_on=["CLM-002"])],
                "section_assignment": {"competition_moat": ["CLM-050"]},
                "insufficient": ["缺少同业对比数据"],
                "comparison_entities": [
                    {
                        "entity_authored": "测试制造股份有限公司",
                        "metric_ids": [],
                        "claim_ids": ["CLM-050"],
                        "limited_data": True,
                    }
                ],
            }
        if task_name == "valuation_narrative":
            target = data["scenario_metrics"]["base"]
            return {
                "assumption_rationales": [
                    {"assumption_id": "ASM-001", "rationale_claim_id": "CLM-061"},
                    {"assumption_id": "ASM-002", "rationale_claim_id": "CLM-062"},
                ],
                "scenario_narratives": {"base": "CLM-060"},
                "rating": "hold",
                "rating_claim_id": "CLM-063",
                "counterevidence_claim_ids": ["CLM-064"],
                "claims": [
                    _claim(
                        "CLM-060", "inference", "基准情景假设估值中枢不变。", metric_ids=[target]
                    ),
                    _claim(
                        "CLM-061", "inference", "市盈率锚取自当前市场定价。", metric_ids=[target]
                    ),
                    _claim("CLM-062", "inference", "区间宽度反映不确定性。", metric_ids=[target]),
                    _claim("CLM-063", "opinion", "综合判断给予持有评级。"),
                    _claim(
                        "CLM-064",
                        "inference",
                        "缺少前瞻盈利数据是主要反方证据。",
                        based_on=["CLM-060"],
                    ),
                ],
                "insufficient": [],
            }
        if task_name == "catalysts_risks":
            return {
                "catalysts": [
                    {
                        "catalyst_id": "CAT-001",
                        "title": _text("新产能投放", "New capacity"),
                        "claim_id": "CLM-070",
                        "timeframe": "3-12m",
                    }
                ],
                "risks": [
                    {
                        "risk_id": "RSK-001",
                        "title": _text("需求下滑", "Demand decline"),
                        "claim_id": "CLM-071",
                        "category": "industry",
                        "severity": "medium",
                        "likelihood": "medium",
                    },
                    {
                        "risk_id": "RSK-002",
                        "title": _text("原材料涨价", "Input cost inflation"),
                        "claim_id": "CLM-072",
                        "category": "operations",
                        "severity": "medium",
                        "likelihood": "low",
                    },
                    {
                        "risk_id": "RSK-003",
                        "title": _text("数据不足", "Insufficient data"),
                        "claim_id": "CLM-073",
                        "category": "other",
                        "severity": "low",
                        "likelihood": "high",
                    },
                ],
                "supporting_claims": [
                    _claim("CLM-070", "inference", "产能投放带来增量。", based_on=["CLM-020"]),
                    _claim("CLM-071", "inference", "需求存在下行风险。", based_on=["CLM-030"]),
                    _claim("CLM-072", "inference", "成本端存在压力。", based_on=["CLM-040"]),
                    _claim("CLM-073", "inference", "资料不足限制判断。", based_on=["CLM-050"]),
                ],
                "notes": "",
            }
        if task_name == "translation":
            return {
                "authoritative_language": data["authoritative_language"],
                "texts": [dict(item) for item in data["texts"]],
                "translation_flags": [],
                "glossary_flags": [],
            }
        if task_name == "slide_compression_plan":
            package = data["package"]
            return {
                "deck_id": data["deck_id"],
                "package_id": package["package_id"],
                "edition": data["edition"],
                "as_of_date": package["as_of_date"],
                "theme": "jacaranda-brand",
                "slide_stubs": [
                    {
                        "slide_no": index + 1,
                        "layout": layout,
                        "section_id": section_id,
                        "claim_ids": claim_ids,
                        "metric_ids": [],
                    }
                    for index, (layout, section_id, claim_ids) in enumerate(_STUB_PLAN)
                ],
            }
        if task_name == "slide_compression_slide":
            stub = data["slide_stub"]
            context = data["deck_context"]
            if stub["layout"] == "L01_cover":
                blocks: list[dict[str, Any]] = [
                    {
                        "block_type": "cover_meta",
                        "priority": 1,
                        "cover_meta": {
                            "company_line": "测试制造股份有限公司",
                            "date_line": context["as_of_date"],
                            "edition_line": context["edition"],
                        },
                    }
                ]
            else:
                refs = [
                    {"claim_id": claim_id} for claim_id in (stub["claim_ids"] or ["CLM-001"])
                ]
                blocks = [
                    {
                        "block_type": "bullets",
                        "priority": 1,
                        "bullets": [
                            {
                                "text": f"要点 {stub['section_id']}",
                                "refs": refs,
                                "claim_type": "inference",
                            }
                        ],
                    }
                ]
            return {
                "slide_no": stub["slide_no"],
                "layout": stub["layout"],
                "title": f"第{stub['slide_no']}页",
                "blocks": blocks,
                "footer": {
                    "show_page_number": stub["layout"] != "L01_cover",
                    "data_as_of": context["as_of_date"],
                    "source_ids": ["SRC-001"],
                },
            }
        raise AssertionError(f"unexpected task: {task_name}")


class NullPresentation:
    def __init__(self) -> None:
        self.rendered: list[str] = []

    def render(
        self, deck: dict[str, Any], package: dict[str, Any], output_path: Path
    ) -> PresentationResult:
        validate_renderable_package(ROOT, package)
        self.rendered.append(str(deck["edition"]))
        output_path.write_bytes(b"pptx-placeholder")
        return PresentationResult(
            edition=cast(Any, deck["edition"]),
            pptx_path=output_path,
            overflow_report={"status": "pass", "issues": []},
        )


class TestValuationCalc:
    def test_pe_band_metrics_are_auditable(self) -> None:
        evidence = {
            "metrics": [
                {
                    "metric_id": "MET-001",
                    "name": _text("收盘价"),
                    "value": 100.0,
                    "unit": "CNY/share",
                    "currency": "CNY",
                    "period": "PIT",
                    "as_of_date": "2026-07-24",
                    "source_id": "SRC-001",
                    "source_url_or_document": "provider://akshare/quote/X",
                    "retrieved_at": "2026-07-27T09:00:00Z",
                    "computed_by": "provider",
                },
                {
                    "metric_id": "MET-002",
                    "name": _text("基本每股收益"),
                    "value": 5.0,
                    "unit": "CNY/share",
                    "currency": "CNY",
                    "period": "FY2025",
                    "as_of_date": "2025-12-31",
                    "source_id": "SRC-002",
                    "source_url_or_document": "provider://akshare/financials/X",
                    "retrieved_at": "2026-07-27T09:00:00Z",
                    "computed_by": "provider",
                },
            ]
        }
        result = ValuationCalc().compute(evidence, metric_id_start=3)
        by_name = {m["name"]["zh_CN"]: m for m in result["metrics"]}
        assert by_name["市盈率（滚动）"]["value"] == 20.0
        assert by_name["目标价（基准情景）"]["value"] == 100.0
        assert by_name["估值区间下限"]["value"] == 85.0
        assert by_name["估值区间上限"]["value"] == 115.0
        for metric in result["metrics"]:
            assert metric["computed_by"] == "deterministic_calc"
            assert metric["calculation"]["input_metric_ids"]
        assert result["method"]["low"] == by_name["估值区间下限"]["metric_id"]
        assert [a["assumption_id"] for a in result["assumptions"]] == ["ASM-001", "ASM-002"]

    def test_missing_eps_raises(self) -> None:
        evidence: JsonDict = {"metrics": []}
        with pytest.raises(DeterministicCalcError):
            ValuationCalc().compute(evidence, metric_id_start=1)


class TestAssemblyHelpers:
    def test_chunks_only_for_sources_with_content(self) -> None:
        evidence = {
            "sources": [
                {
                    "source_id": "SRC-001",
                    "type": "market_data_api",
                    "locator": "X",
                    "retrieved_at": "2026-07-27T09:00:00Z",
                    "url_or_document": "provider://akshare/quote/X",
                    "language": "zh",
                },
            ],
            "company": {
                "source_id": "SRC-001",
                "name_zh": "测试公司",
                "name_en": None,
                "industry": None,
                "listing_date": None,
            },
            "metrics": [],
        }
        chunks = build_evidence_chunks(evidence)
        assert len(chunks) == 1
        assert "公司名称：测试公司。" in chunks[0]["text"]

    def test_candidate_mapping_drops_and_holds(self) -> None:
        s1 = {
            "candidate_claims": [
                {
                    "candidate_id": "CCLM-001",
                    "type": "fact",
                    "text_original_language": "A",
                    "source_ids": ["SRC-001"],
                    "quote": "A",
                },
                {
                    "candidate_id": "CCLM-002",
                    "type": "fact",
                    "text_original_language": "B",
                    "source_ids": ["SRC-001"],
                    "quote": "B",
                },
                {
                    "candidate_id": "CCLM-003",
                    "type": "fact",
                    "text_original_language": "C",
                    "source_ids": ["SRC-001"],
                    "quote": "C",
                },
            ]
        }
        s2 = {
            "verdicts": [
                {"candidate_id": "CCLM-001", "verdict": "verified"},
                {"candidate_id": "CCLM-002", "verdict": "rejected"},
                {"candidate_id": "CCLM-003", "verdict": "needs_review"},
            ]
        }
        claims, next_number, held = map_verified_candidates(s1, s2, next_claim_number=1)
        assert [claim["claim_id"] for claim in claims] == ["CLM-001"]
        assert next_number == 2
        assert held == ["CCLM-003"]

    def test_sections_are_complete_and_ordered(self) -> None:
        sections = build_sections(
            section_assignments={"business_model_segments": ["CLM-020"]},
            fact_claim_ids=["CLM-001"],
            rating_claim_id="CLM-063",
            counterevidence_claim_ids=["CLM-064"],
            scenario_claim_ids=["CLM-060"],
            catalyst_claim_ids=["CLM-070"],
            risk_claim_ids=["CLM-071"],
            key_metric_ids={"valuation": ["MET-004"]},
        )
        assert [section["section_id"] for section in sections] == [
            "cover",
            "investment_thesis",
            "company_snapshot",
            "industry_value_chain",
            "business_model_segments",
            "competition_moat",
            "historical_financials",
            "forecast_drivers",
            "valuation",
            "catalysts",
            "risks",
            "conclusion_sources_disclaimer",
        ]
        by_id = {section["section_id"]: section for section in sections}
        assert "CLM-064" in by_id["investment_thesis"]["claim_ids"]
        assert "CLM-064" in by_id["risks"]["claim_ids"]
        assert by_id["valuation"]["key_metric_ids"] == ["MET-004"]


class TestRealPipeline:
    @pytest.mark.anyio
    async def test_full_real_run_produces_draft_package(self, tmp_path: Path) -> None:
        llm = FakeRealLLM()
        presentation = NullPresentation()
        orchestrator = RealResearchOrchestrator(
            ROOT, llm=llm, akshare_client=EvidenceClient(), presentation=presentation
        )
        artifacts = await orchestrator.run("600519", tmp_path / "run")
        package = load_json(artifacts.research_package)

        assert package["status"] == "draft"
        assert package["company"]["is_mock"] is False
        assert package["company"]["name"]["en_AU"] == "Test Manufacturing Co., Ltd."
        assert package["package_id"].startswith("RPK-600519-")
        # structural gate holds for the written artifact too
        validate_real_package(ROOT, package)
        # deterministic calc metrics present with full audit trail
        calc_metrics = [
            metric
            for metric in package["metrics"]
            if metric["computed_by"] == "deterministic_calc"
        ]
        assert len(calc_metrics) == 4
        # QC computed: QC-06 needs_human keeps this a draft, nothing failed
        checks = {c["check_id"]: c["result"] for c in package["quality"]["checks"]}
        assert checks["QC-06"] == "needs_human"
        assert "fail" not in checks.values()
        # missing gross margin surfaced as warning, not zero
        assert any(
            "gross_margin" in note
            for note in [package["generation_metadata"]["notes"]]
        )
        # both editions rendered and manifest written
        assert sorted(presentation.rendered) == ["en-AU", "zh-CN"]
        manifest = load_json(artifacts.manifest)
        assert manifest["network"] == "live"
        assert manifest["status"] == "draft"

    @pytest.mark.anyio
    async def test_uploads_become_secondary_sources_with_locators(
        self, tmp_path: Path
    ) -> None:
        uploads: list[JsonDict] = [
            {
                "upload_id": "u1",
                "filename": "annual-report.pdf",
                "created_at": "2026-07-27T08:00:00+00:00",
                "blocks": [
                    {"locator": "page=3", "kind": "text", "text": "公司主营高端制造产品。"}
                ],
            }
        ]
        orchestrator = RealResearchOrchestrator(
            ROOT,
            llm=FakeRealLLM(),
            akshare_client=EvidenceClient(),
            presentation=NullPresentation(),
        )
        artifacts = await orchestrator.run(
            "600519", tmp_path / "run", uploads=uploads
        )
        package = load_json(artifacts.research_package)
        upload_sources = [
            source for source in package["sources"] if source["type"] == "user_upload"
        ]
        assert len(upload_sources) == 1
        assert upload_sources[0]["url_or_document"] == "upload://u1"
        assert upload_sources[0]["reliability_tier"] == "secondary"
        validate_real_package(ROOT, package)

    @pytest.mark.anyio
    async def test_resume_reuses_disk_checkpoints(self, tmp_path: Path) -> None:
        out = tmp_path / "run"
        first = FakeRealLLM()
        orchestrator = RealResearchOrchestrator(
            ROOT, llm=first, akshare_client=EvidenceClient(), presentation=NullPresentation()
        )
        await orchestrator.run("600519", out)
        assert first.calls

        class ExplodingLLM(FakeRealLLM):
            async def run(self, *args: Any, **kwargs: Any) -> LLMResult:
                raise AssertionError("resume must not re-invoke the model")

        resumed = RealResearchOrchestrator(
            ROOT,
            llm=ExplodingLLM(),
            akshare_client=EvidenceClient(),
            presentation=NullPresentation(),
        )
        artifacts = await resumed.run("600519", out, resume=True)
        package = load_json(artifacts.research_package)
        assert package["status"] == "draft"
        checkpoint_files = sorted(
            path.name for path in (out / "checkpoints").glob("*.json")
        )
        assert "00-evidence.json" in checkpoint_files
        assert "07-deck-zh-CN.json" in checkpoint_files

    @pytest.mark.anyio
    async def test_no_verified_fact_aborts_run(self, tmp_path: Path) -> None:
        class RejectingLLM(FakeRealLLM):
            def _output(self, task_name: str, data: dict[str, Any]) -> dict[str, Any]:
                output = super()._output(task_name, data)
                if task_name == "source_verification":
                    for verdict in output["verdicts"]:
                        verdict["verdict"] = "needs_review"
                        verdict["checks"]["entity_known"] = False
                        verdict["reasons"] = ["cannot verify"]
                return output

        orchestrator = RealResearchOrchestrator(
            ROOT,
            llm=RejectingLLM(),
            akshare_client=EvidenceClient(),
            presentation=NullPresentation(),
        )
        with pytest.raises(SemanticValidationError, match="no candidate fact"):
            await orchestrator.run("600519", tmp_path / "run")

    def test_cli_requires_symbol_and_output_dir(self) -> None:
        def wiring(root: Path) -> Any:
            raise AssertionError("argument parsing happens before wiring")

        with pytest.raises(SystemExit):
            real_main(["--symbol"], wiring=wiring)


class TestValidationGates:
    def test_real_gate_rejects_mock_flag(self) -> None:
        package = load_json(ROOT / "packages/presentation/fixtures/mock-package.json")
        with pytest.raises(SemanticValidationError, match="is_mock"):
            validate_real_package(ROOT, package)

    def test_renderable_gate_blocks_approved_mock(self) -> None:
        package = load_json(ROOT / "packages/presentation/fixtures/mock-package.json")
        package["status"] = "approved"
        with pytest.raises(SemanticValidationError, match="never be approved"):
            validate_renderable_package(ROOT, package)
