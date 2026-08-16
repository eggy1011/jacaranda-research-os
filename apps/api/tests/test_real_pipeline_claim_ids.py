from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from jacaranda_api.pipeline.models import JsonDict
from jacaranda_api.pipeline.real_orchestrator import RealResearchOrchestrator

ROOT = Path(__file__).resolve().parents[3]


def _orchestrator() -> RealResearchOrchestrator:
    # The claim-id helpers never touch the model or the market client, so bare
    # stand-ins are enough to exercise them.
    return RealResearchOrchestrator(
        ROOT, llm=cast(Any, object()), akshare_client=cast(Any, object())
    )


def _claim(claim_id: str, **extra: Any) -> JsonDict:
    return {"claim_id": claim_id, "type": "inference", **extra}


def test_next_claim_id_is_running_max_plus_one() -> None:
    assert RealResearchOrchestrator._next_claim_id([]) == "CLM-001"
    claims = [_claim("CLM-001"), _claim("CLM-031"), _claim("CLM-020")]
    assert RealResearchOrchestrator._next_claim_id(claims) == "CLM-032"


def test_rebase_leaves_collision_free_stage_untouched() -> None:
    existing = [_claim("CLM-001"), _claim("CLM-020")]
    output: JsonDict = {
        "claims": [_claim("CLM-021"), _claim("CLM-022")],
        "section_assignment": {"company_snapshot": ["CLM-021", "CLM-022"]},
    }
    rebased = _orchestrator()._rebase_stage_claims(output, "claims", existing)
    assert rebased is output


def test_rebase_relocates_colliding_stage_and_remaps_references() -> None:
    # Facts CLM-001..008 plus an S3c block ending at CLM-037 already exist; the
    # next stage mis-numbered its first claim as CLM-037 (a live-model hazard).
    existing = [_claim(f"CLM-{n:03d}") for n in (1, 8, 32, 33, 34, 35, 36, 37)]
    output: JsonDict = {
        "claims": [
            _claim("CLM-037", based_on_claim_ids=["CLM-008"]),  # references a prior fact
            _claim("CLM-038", based_on_claim_ids=["CLM-037"]),  # references its sibling
        ],
        "section_assignment": {"competition_moat": ["CLM-037", "CLM-038"]},
        "comparison_entities": [{"entity_authored": "X", "claim_ids": ["CLM-037"]}],
    }
    rebased = _orchestrator()._rebase_stage_claims(output, "claims", existing)

    ids = [claim["claim_id"] for claim in rebased["claims"]]
    assert ids == ["CLM-038", "CLM-039"]  # fresh contiguous block after CLM-037
    # The prior-fact reference is untouched; the sibling reference tracks the move.
    assert rebased["claims"][0]["based_on_claim_ids"] == ["CLM-008"]
    assert rebased["claims"][1]["based_on_claim_ids"] == ["CLM-038"]
    assert rebased["section_assignment"]["competition_moat"] == ["CLM-038", "CLM-039"]
    assert rebased["comparison_entities"][0]["claim_ids"] == ["CLM-038"]
