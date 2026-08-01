"""Runtime validator for a social-card-series against its research package.

This is the single enforcement point for the "no invented figures or evidence" invariant. The
renderer calls it fail-closed (an invalid series is never rendered), the pipeline scheduler calls
it before rendering, and the CI contract validator delegates to it — so the model, the schema and
the renderer are all held to exactly one set of rules.

Semantic checks are pure-Python and defensive (they do not assume schema-valid input). JSON-Schema
structural validation is layered on when ``jsonschema`` is importable.
"""

from __future__ import annotations

import re
from pathlib import Path

from .tokens import (
    CARD_TEXT_CAPS,
    ROLE_ORDER,
    TRANSFORM_DIVISOR,
    TRANSFORM_SUFFIX,
)

SCHEMA_PATH = (Path(__file__).resolve().parents[2]
               / "research-schema" / "social-card-series.schema.json")

RENDERABLE_STATUS = frozenset({"verified", "approved"})

# Tokens exempt from number binding: years, quarters, half-years, fiscal-year and section markers.
# Compound period forms (2026Q4, 2026H1) must be matched before the bare four-digit year, since
# "2026Q4" has no word boundary between the year and the quarter.
_DATE_EXEMPT = re.compile(
    r"\bFY\d{4}\b|\d{4}Q[1-4]|\d{4}H[12]|\b\d{4}\b|Q[1-4]|H[12]|[一二三四]季度|上半年|下半年")
# A numeric token with its immediate sign and unit — sign and unit are validated, not just value.
_NUM_TOKEN = re.compile(r"([+\-]?)(\d[\d,]*(?:\.\d+)?)\s*(%|倍|亿元|亿|万元|万|千|百万|十亿|x)?")
# An interim period must be named on the latest_quarter card (never a full-year figure).
_INTERIM = re.compile(r"Q[1-4]|[一二三四]季度|H[12]|上半年|下半年|中报")
_SUFFIX_SYNONYM = {"亿元": "亿", "万元": "万", "倍": "x"}


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def _formatted_allowed(card: dict, metrics: dict) -> list[tuple[float, str, int]]:
    """Allowed (magnitude, unit-suffix, value-sign) triples from the card's declared numbers.

    Only inline displayNumbers justify a narrative numeral — a bare metric_ref is provenance, not
    a licence to print an arbitrary figure. This mirrors format_number exactly.
    """
    out: list[tuple[float, str, int]] = []
    for dn in card.get("inline_numbers", []):
        metric = metrics.get(dn.get("metric_id"))
        if metric is None:
            continue  # dangling inline metric is reported separately
        transform = dn.get("display_transform")
        if transform not in TRANSFORM_DIVISOR:
            continue
        scaled = metric["value"] / TRANSFORM_DIVISOR[transform]
        mag = round(abs(scaled), dn.get("decimals", 1))
        out.append((mag, TRANSFORM_SUFFIX[transform], _sign(metric["value"])))
    return out


def _unbound_numbers(text: str, allowed: list[tuple[float, str, int]]) -> list[str]:
    bad: list[str] = []
    cleaned = _DATE_EXEMPT.sub(" ", text)
    for sign_char, num, suffix in _NUM_TOKEN.findall(cleaned):
        if not num:
            continue
        mag = abs(float(num.replace(",", "")))
        unit = _SUFFIX_SYNONYM.get(suffix, suffix)
        matched = False
        for a_mag, a_suffix, a_sign in allowed:
            if abs(mag - a_mag) > 1e-6:
                continue
            if unit != a_suffix:
                continue  # unit must match the declared transform
            if sign_char == "-" and a_sign >= 0:
                continue  # a positive metric may not be shown negative
            if sign_char == "+" and a_sign < 0:
                continue
            matched = True
            break
        if not matched:
            bad.append(f"{sign_char}{num}{suffix}")
    return bad


def validate_series(series: dict, package: dict, *,
                    require_status: frozenset[str] | None = RENDERABLE_STATUS,
                    schema: dict | None = None) -> list[str]:
    """Return a list of human-readable issues; empty means the series is safe to render.

    ``require_status`` gates the package lifecycle (a mock package is never renderable as
    ``approved``); pass ``None`` to skip the lifecycle gate (e.g. contract fixture checks).
    """
    issues: list[str] = []

    def bad(msg: str) -> None:
        issues.append(msg)

    # -- structural (JSON-Schema, best-effort) --------------------------------
    try:
        import json

        from jsonschema import Draft202012Validator
        doc = schema if schema is not None else json.loads(SCHEMA_PATH.read_text("utf-8"))
        for e in sorted(Draft202012Validator(doc).iter_errors(series),
                        key=lambda e: list(e.path)):
            bad(f"schema: {'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}")
        if issues:
            return issues  # structural failures make semantic checks meaningless
    except ImportError:
        pass  # jsonschema unavailable — semantic checks below still run defensively

    cards = series.get("cards")
    if not isinstance(cards, list) or len(cards) != 7:
        bad(f"cards: expected exactly 7, got {len(cards) if isinstance(cards, list) else 'none'}")
        return issues
    if [c.get("card_no") for c in cards] != list(range(1, 8)):
        bad("cards: card_no must be 1..7 contiguous in order")
    if [c.get("role") for c in cards] != ROLE_ORDER:
        bad(f"cards: roles must be exactly {ROLE_ORDER} in order")

    # -- lifecycle gate -------------------------------------------------------
    status = package.get("status")
    is_mock = package.get("company", {}).get("is_mock", False)
    if require_status is not None and status not in require_status:
        bad(f"package status {status!r} is not renderable (need {sorted(require_status)})")
    if is_mock and status == "approved":
        bad("mock package must never be rendered as approved")
    if series.get("package_id") != package.get("package_id"):
        bad("series/package id mismatch")

    metrics = {m["metric_id"]: m for m in package.get("metrics", [])}
    claims = {c["claim_id"]: c for c in package.get("claims", [])}
    sources = {s["source_id"] for s in package.get("sources", [])}
    counter_ids = set(package.get("valuation", {}).get("counterevidence_claim_ids", []))

    for card in cards:
        role = card.get("role", "?")
        where = f"card {card.get('card_no', '?')} ({role})"

        # references resolve, and are not duplicated
        for cid in card.get("claim_refs", []):
            if cid not in claims:
                bad(f"{where}: dangling claim {cid}")
        for mid in card.get("metric_refs", []):
            if mid not in metrics:
                bad(f"{where}: dangling metric {mid}")
        for sid in card.get("source_ids", []):
            if sid not in sources:
                bad(f"{where}: dangling source {sid}")
        for dn in card.get("inline_numbers", []):
            if dn.get("metric_id") not in metrics:
                bad(f"{where}: inline number cites unknown metric {dn.get('metric_id')}")
        for field in ("claim_refs", "metric_refs", "source_ids"):
            vals = card.get(field, [])
            if len(vals) != len(set(vals)):
                bad(f"{where}: duplicate {field}")

        # number binding (value + unit + sign), the anti-fabrication core
        allowed = _formatted_allowed(card, metrics)
        text = f"{card.get('hook', '')} {card.get('body', '')}"
        for token in _unbound_numbers(text, allowed):
            bad(f"{where}: unbound number {token!r} (not a declared inline figure)")

        # claim_type mirrors the referenced claim(s)
        ref_types = {claims[c]["type"] for c in card.get("claim_refs", []) if c in claims}
        if card.get("claim_type") and ref_types and card["claim_type"] not in ref_types:
            bad(f"{where}: claim_type {card['claim_type']!r} not in referenced {sorted(ref_types)}")

        # every card's source line must cover the sources its evidence cites
        need = {s for cid in card.get("claim_refs", []) if cid in claims
                for s in claims[cid].get("source_ids", [])}
        need |= {metrics[m]["source_id"] for m in card.get("metric_refs", []) if m in metrics}
        need |= {metrics[dn["metric_id"]]["source_id"]
                 for dn in card.get("inline_numbers", []) if dn.get("metric_id") in metrics}
        missing = need - set(card.get("source_ids", []))
        if missing:
            bad(f"{where}: source line missing {sorted(missing)} cited by its evidence")

        # text within caps (over-limit copy is a planning failure, never a silent truncation)
        caps = CARD_TEXT_CAPS["cover" if role == "cover" else "default"]
        if len(card.get("hook", "")) > caps["hook"]:
            bad(f"{where}: hook exceeds {caps['hook']} chars (would truncate)")
        if len(card.get("body", "")) > caps["body"]:
            bad(f"{where}: body exceeds {caps['body']} chars (would truncate)")
        if card.get("caveat") and len(card["caveat"]) > caps["caveat"]:
            bad(f"{where}: caveat exceeds {caps['caveat']} chars (would truncate)")

    by_role = {c.get("role"): c for c in cards}

    lq = by_role.get("latest_quarter", {})
    if not _INTERIM.search(f"{lq.get('hook', '')} {lq.get('body', '')}"):
        bad("latest_quarter: must name an explicit interim period (e.g. 2026Q4), not a full year")
    if not (lq.get("audit_note") or "").strip():
        bad("latest_quarter: must carry an audit_note")

    concl = by_role.get("counter_conclusion", {})
    if not (concl.get("caveat") or "").strip():
        bad("counter_conclusion: must carry a caveat")
    if set(concl.get("source_ids", [])) != sources:
        bad("counter_conclusion: must carry the full source union")
    concl_claims = concl.get("claim_refs", [])
    cites_counter = (any(claims.get(c, {}).get("is_counterevidence") for c in concl_claims)
                     or bool(set(concl_claims) & counter_ids))
    if not cites_counter:
        bad("counter_conclusion: must reference a genuine counterevidence claim")

    return issues
