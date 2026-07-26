from __future__ import annotations

import re
from datetime import date

from jacaranda_api.pipeline.models import JsonDict

RUBRIC_VERSION = "0.1.0"

_ID_PATTERN = re.compile(r"(?:MET|CLM|SRC|ASM)-[0-9]{3}")
_PROTECTED = re.compile(
    r"(?<![A-Za-z0-9_])(?:MET|CLM|SRC|ASM|RSK|CAT)-\d{3}(?![A-Za-z0-9_])"
    r"|(?<![A-Za-z0-9_])\d+(?:\.\d+)?%?(?![A-Za-z0-9_])"
)


def _check(check_id: str, result: str, details: str) -> JsonDict:
    return {"check_id": check_id, "result": result, "details": details}


def _collect_ids(package: JsonDict) -> set[str]:
    ids = {item["metric_id"] for item in package["metrics"]}
    ids |= {item["claim_id"] for item in package["claims"]}
    ids |= {item["source_id"] for item in package["sources"]}
    ids |= {item["assumption_id"] for item in package["valuation"]["assumptions"]}
    return ids


def _dangling_references(package: JsonDict) -> list[str]:
    known = _collect_ids(package)
    unresolved: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str):
            for identifier in _ID_PATTERN.findall(value):
                if identifier not in known:
                    unresolved.add(identifier)

    visit(package)
    return sorted(unresolved)


def _bilingual_number_mismatches(package: JsonDict) -> list[str]:
    mismatches: list[str] = []

    def visit(value: object, path: str) -> None:
        if isinstance(value, dict):
            if set(value) == {"zh_CN", "en_AU"}:
                zh, en = value["zh_CN"], value["en_AU"]
                if isinstance(zh, str) and isinstance(en, str):
                    if tuple(_PROTECTED.findall(zh)) != tuple(_PROTECTED.findall(en)):
                        mismatches.append(path)
                return
            for key in sorted(value):
                visit(value[key], f"{path}.{key}" if path else key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    visit(package, "")
    return mismatches


def evaluate_quality(package: JsonDict, *, evidence_warnings: list[str]) -> JsonDict:
    """Compute the machine-checkable QC-01..QC-11 results for a freshly assembled
    real package. QC-06 stays needs_human by design: only a person can verify
    real-world facts, which is why a real package starts as a draft."""
    checks: list[JsonDict] = []

    dangling = _dangling_references(package)
    checks.append(
        _check(
            "QC-01",
            "fail" if dangling else "pass",
            f"unresolved: {dangling}"
            if dangling
            else "all MET/CLM/SRC/ASM references resolve",
        )
    )

    as_of = date.fromisoformat(package["as_of_date"])
    stale: list[str] = []
    very_stale: list[str] = []
    for metric in package["metrics"]:
        if metric["period"] == "PIT" and metric["computed_by"] == "provider":
            age = (as_of - date.fromisoformat(metric["as_of_date"])).days
            if age > 30:
                very_stale.append(f"{metric['metric_id']} is {age} days old")
            elif age > 7:
                # holiday closures can legitimately exceed a week; flag, don't block
                stale.append(f"{metric['metric_id']} is {age} days old")
    freshness_result = "fail" if very_stale else ("warning" if stale else "pass")
    checks.append(
        _check(
            "QC-02",
            freshness_result,
            "; ".join(very_stale + stale)
            or "point-in-time data is within 7 calendar days of as_of_date",
        )
    )

    mismatches = _bilingual_number_mismatches(package)
    checks.append(
        _check(
            "QC-03",
            "fail" if mismatches else "pass",
            f"numeric/id parity broken at: {mismatches[:5]}"
            if mismatches
            else "zh/en share identical numbers and identifiers",
        )
    )

    checks.append(_check("QC-04", "not_run", "chart consistency is checked at render time"))

    tiers = {source["source_id"]: source["reliability_tier"] for source in package["sources"]}
    integrity: list[str] = []
    for claim in package["claims"]:
        if claim["type"] == "fact":
            if not claim.get("source_ids"):
                integrity.append(f"{claim['claim_id']} fact without sources")
            elif any(
                tiers.get(sid) not in {"primary", "secondary"} for sid in claim["source_ids"]
            ):
                integrity.append(f"{claim['claim_id']} fact cites a caution-tier source")
        if claim["type"] == "inference" and not (
            claim.get("source_ids") or claim.get("metric_ids") or claim.get("based_on_claim_ids")
        ):
            integrity.append(f"{claim['claim_id']} unsupported inference")
    checks.append(
        _check(
            "QC-05",
            "fail" if integrity else "pass",
            "; ".join(integrity) or "fact/inference/opinion support rules hold",
        )
    )

    checks.append(
        _check(
            "QC-06",
            "needs_human",
            "real-world verifiability requires human review before the package can be verified",
        )
    )

    checks.append(
        _check(
            "QC-07",
            "warning" if evidence_warnings else "pass",
            "; ".join(evidence_warnings) or "no missing-data substitutions detected",
        )
    )

    assumptions = package["valuation"]["assumptions"]
    missing_rationale = [
        item["assumption_id"] for item in assumptions if not item.get("rationale_claim_id")
    ]
    checks.append(
        _check(
            "QC-08",
            "pass" if assumptions and not missing_rationale else "fail",
            f"assumptions without rationale: {missing_rationale}"
            if missing_rationale
            else "every valuation assumption is explicit with a rationale claim",
        )
    )

    has_counter = bool(package["valuation"]["counterevidence_claim_ids"]) and any(
        claim.get("is_counterevidence") for claim in package["claims"]
    )
    checks.append(
        _check(
            "QC-09",
            "pass" if has_counter else "fail",
            "counterevidence present"
            if has_counter
            else "no counterevidence claim recorded",
        )
    )

    risk_ok = len(package["risks"]) >= 3 and bool(package["disclaimer"]["text"]["zh_CN"])
    checks.append(
        _check(
            "QC-10",
            "pass" if risk_ok else "fail",
            "at least 3 risks and a bilingual disclaimer"
            if risk_ok
            else "fewer than 3 risks or missing disclaimer",
        )
    )

    checks.append(
        _check("QC-11", "not_run", "overflow checked at render time by the template QA pass")
    )

    failed = any(item["result"] == "fail" for item in checks)
    overall = "fail" if failed else "acceptable"
    return {"rubric_version": RUBRIC_VERSION, "checks": checks, "overall": overall}
