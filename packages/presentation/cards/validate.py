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
LOCALE = "zh-CN"

_MONETARY = frozenset({"CNY", "USD", "HKD", "AUD", "EUR", "JPY", "GBP"})
_SCALE_TRANSFORMS = frozenset({"raw", "thousand", "wan", "million", "yi", "billion"})


def _transform_ok(unit: str, transform: str) -> bool:
    """A display transform must be compatible with the metric's canonical unit.

    A CNY revenue may be shown raw/万/亿/…, never as a percentage or a multiple; a "%" metric may
    only be shown as percent, and an "x" metric only as a multiple. Without this a model could
    label an amount metric `percent` and print a nonsense "%" value that still "binds".
    """
    if unit == "%":
        return transform == "percent"
    if unit == "x":
        return transform == "multiple"
    if unit in _MONETARY:
        return transform in _SCALE_TRANSFORMS
    return transform in _SCALE_TRANSFORMS  # counts/shares/etc. scale but are not percent/multiple


# Tokens exempt from number binding: ISO dates, years, quarters, half-years, fiscal years.
# Compound period forms (2026Q4, 2026H1) are matched before the bare year, since "2026Q4" has no
# word boundary between the year and the quarter.
_DATE_EXEMPT = re.compile(
    r"\d{4}-\d{2}-\d{2}|\bFY\d{4}\b|\d{4}Q[1-4]|\d{4}H[12]|\b\d{4}\b|Q[1-4]|H[12]"
    r"|[一二三四]季度|上半年|下半年")
# A numeric token with its immediate sign and unit — sign and unit are validated, not just value.
_NUM_TOKEN = re.compile(r"([+\-]?)(\d[\d,]*(?:\.\d+)?)\s*(%|倍|亿元|亿|万元|万|千|百万|十亿|x)?")
_SUFFIX_SYNONYM = {"亿元": "亿", "万元": "万", "倍": "x"}

# Datable reporting periods, used to reject a "latest quarter" that is actually in the future.
_PERIOD_PATTERNS = (
    (re.compile(r"(\d{4})Q([1-4])"), lambda y, q: _period_end(y, {1: 3, 2: 6, 3: 9, 4: 12}[q])),
    (re.compile(r"(\d{4})H([12])"), lambda y, h: _period_end(y, 6 if h == 1 else 12)),
    (re.compile(r"FY(\d{4})|(\d{4})\s*财年|(\d{4})\s*年报"), lambda y, *_: _period_end(y, 12)),
)


def _period_end(year: int, month: int) -> str:
    last = {3: 31, 6: 30, 9: 30, 12: 31}[month]
    return f"{year:04d}-{month:02d}-{last:02d}"


def _latest_period_end(text: str) -> str | None:
    """The end date of the newest datable reporting period named in the text, or None."""
    ends: list[str] = []
    for pattern, to_end in _PERIOD_PATTERNS:
        for m in pattern.finditer(text):
            groups = [g for g in m.groups() if g]
            ends.append(to_end(int(groups[0]), *(int(g) for g in groups[1:])))
    return max(ends) if ends else None


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
        if not _transform_ok(metric.get("unit", ""), transform):
            continue  # unit-incompatible transform is reported separately
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

    # -- lifecycle + identity gate -------------------------------------------
    status = package.get("status")
    is_mock = package.get("company", {}).get("is_mock", False)
    if require_status is not None and status not in require_status:
        bad(f"package status {status!r} is not renderable (need {sorted(require_status)})")
    if is_mock and status == "approved":
        bad("mock package must never be rendered as approved")
    if series.get("package_id") != package.get("package_id"):
        bad("series/package id mismatch")
    if series.get("locale") != LOCALE or package.get("locale") != LOCALE:
        bad(f"series and package must both declare locale {LOCALE!r} "
            f"(series={series.get('locale')!r}, package={package.get('locale')!r})")
    if series.get("as_of_date") != package.get("as_of_date"):
        bad("series as_of_date must equal the package as_of_date")
    as_of = package.get("as_of_date", "")

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
            mid = dn.get("metric_id")
            if mid not in metrics:
                bad(f"{where}: inline number cites unknown metric {mid}")
            elif not _transform_ok(metrics[mid].get("unit", ""), dn.get("display_transform", "")):
                bad(f"{where}: transform {dn.get('display_transform')!r} is incompatible with "
                    f"{mid} unit {metrics[mid].get('unit')!r}")
        for field in ("claim_refs", "metric_refs", "source_ids"):
            vals = card.get(field, [])
            if len(vals) != len(set(vals)):
                bad(f"{where}: duplicate {field}")

        # every card must carry provenance: a non-cover card needs at least one claim reference;
        # the cover may lead with a metric instead. A card with no refs is an unsupported assertion.
        if not card.get("claim_refs"):
            if role != "cover":
                bad(f"{where}: must reference at least one claim (no unsupported assertions)")
            elif not card.get("metric_refs"):
                bad(f"{where}: cover must reference at least one claim or metric")

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
    lq_period = _latest_period_end(f"{lq.get('hook', '')} {lq.get('body', '')}")
    if lq_period is None:
        bad("latest_quarter: must name a datable reporting period (e.g. 2026Q1 or FY2025)")
    elif as_of and lq_period > as_of:
        bad(f"latest_quarter: period ends {lq_period}, after the data cutoff {as_of} — a future "
            f"period is a forward catalyst, not the latest disclosed period")
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
