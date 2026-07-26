from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator


class SemanticValidationError(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _validate_structure(repository_root: Path, package: dict[str, Any]) -> None:
    """Shared structural gate: schema, resolvable references, 12 sections,
    counterevidence surfaced in the thesis, and fact-tier requirements."""
    schema = load_json(repository_root / "packages/research-schema/research-package.schema.json")
    Draft202012Validator(schema).validate(package)
    _assert_references(package)
    section_ids = [section["section_id"] for section in package["sections"]]
    if len(section_ids) != 12 or len(set(section_ids)) != 12:
        raise SemanticValidationError("all 12 unique research sections are required")
    counter = {claim["claim_id"] for claim in package["claims"] if claim.get("is_counterevidence")}
    thesis = next(s for s in package["sections"] if s["section_id"] == "investment_thesis")
    if not counter.intersection(thesis["claim_ids"]):
        raise SemanticValidationError("investment thesis must surface counterevidence")
    source_tiers = {
        source["source_id"]: source["reliability_tier"] for source in package["sources"]
    }
    for claim in package["claims"]:
        if claim["type"] == "fact" and any(
            source_tiers.get(source_id) not in {"primary", "secondary"}
            for source_id in claim["source_ids"]
        ):
            raise SemanticValidationError("facts require primary or secondary evidence")


def validate_package(repository_root: Path, package: dict[str, Any]) -> None:
    """Mock-slice gate: fixture packages must stay mock, stop at verified, and
    pass every automated QC check."""
    if package["company"]["is_mock"] is not True or package["status"] != "verified":
        raise SemanticValidationError("mock packages must stop at verified")
    _validate_structure(repository_root, package)
    checks = {check["check_id"]: check["result"] for check in package["quality"]["checks"]}
    if any(checks.get(f"QC-{index:02d}") != "pass" for index in range(1, 11)):
        raise SemanticValidationError("existing bilingual and research QC checks must pass")


def validate_renderable_package(repository_root: Path, package: dict[str, Any]) -> None:
    """Render-time gate: structural completeness plus the one status rule that
    must hold everywhere — a mock package can never be approved."""
    if package["company"]["is_mock"] is True and package["status"] == "approved":
        raise SemanticValidationError("mock packages can never be approved")
    _validate_structure(repository_root, package)


def validate_real_package(repository_root: Path, package: dict[str, Any]) -> None:
    """Real-run gate for a freshly assembled draft: structurally complete, honest
    about being unreviewed. QC checks may be needs_human/not_run/warning (that is
    what human review is for) but a hard QC fail blocks even the draft."""
    if package["company"]["is_mock"] is not False:
        raise SemanticValidationError("real packages must set company.is_mock to false")
    if package["status"] != "draft":
        raise SemanticValidationError(
            "a freshly generated real package must be a draft until human review"
        )
    _validate_structure(repository_root, package)
    failed = [
        check["check_id"]
        for check in package["quality"]["checks"]
        if check["result"] == "fail"
    ]
    if failed:
        raise SemanticValidationError(f"quality checks failed: {failed}")


def validate_decks(
    repository_root: Path, package: dict[str, Any], decks: dict[str, dict[str, Any]]
) -> None:
    schema = load_json(repository_root / "packages/research-schema/slide-deck.schema.json")
    package_ids = _id_sets(package)
    deck_refs: dict[str, tuple[set[str], set[str], set[str], set[str]]] = {}
    for edition, deck in decks.items():
        Draft202012Validator(schema).validate(deck)
        if deck["edition"] != edition or deck["package_id"] != package["package_id"]:
            raise SemanticValidationError("deck identity does not match the research package")
        refs = _collect_reference_values(deck)
        if (
            not refs[0] <= package_ids[0]
            or not refs[1] <= package_ids[1]
            or not refs[2] <= package_ids[2]
            or not refs[3] <= package_ids[3]
        ):
            raise SemanticValidationError("deck contains unresolved package references")
        deck_refs[edition] = refs
    if deck_refs["zh-CN"] != deck_refs["en-AU"]:
        raise SemanticValidationError("edition identifier parity failed")


def _id_sets(package: dict[str, Any]) -> tuple[set[str], set[str], set[str], set[str]]:
    return (
        {item["metric_id"] for item in package["metrics"]},
        {item["claim_id"] for item in package["claims"]},
        {item["source_id"] for item in package["sources"]},
        {item["assumption_id"] for item in package["valuation"]["assumptions"]},
    )


def _collect_reference_values(value: Any) -> tuple[set[str], set[str], set[str], set[str]]:
    refs: tuple[set[str], set[str], set[str], set[str]] = (set(), set(), set(), set())

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                target = {
                    "metric_id": refs[0],
                    "claim_id": refs[1],
                    "source_id": refs[2],
                    "assumption_id": refs[3],
                }.get(key)
                if target is not None and isinstance(child, str):
                    target.add(child)
                if key in {
                    "metric_ids",
                    "claim_ids",
                    "source_ids",
                    "assumption_ids",
                } and isinstance(child, list):
                    target = {
                        "metric_ids": refs[0],
                        "claim_ids": refs[1],
                        "source_ids": refs[2],
                        "assumption_ids": refs[3],
                    }[key]
                    target.update(entry for entry in child if isinstance(entry, str))
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return refs


def _assert_references(package: dict[str, Any]) -> None:
    metric_ids, claim_ids, source_ids, assumption_ids = _id_sets(package)
    all_ids = metric_ids | claim_ids | source_ids | assumption_ids
    unresolved: set[str] = set()

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, child_key)
        elif isinstance(value, list):
            for child in value:
                visit(child, key)
        elif isinstance(value, str):
            for identifier in re.findall(r"(?:MET|CLM|SRC|ASM)-[0-9]{3}", value):
                if identifier not in all_ids:
                    unresolved.add(identifier)

    visit(package)
    if unresolved:
        raise SemanticValidationError(f"unresolved identifiers: {sorted(unresolved)}")
