#!/usr/bin/env python3
"""Validator for the prompt catalogue and its end-to-end fixtures (Issue #13).

Run from the repository root:  python3 packages/prompts/tests/validate.py
Requires: pip install jsonschema
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROMPTS = ROOT / "packages" / "prompts"
EXAMPLES = PROMPTS / "examples"
SCHEMA_DIR = ROOT / "packages" / "research-schema"
SCHEMA_EXAMPLES = SCHEMA_DIR / "examples"

PROMPT_FILES = [
    "extraction.md", "source-verification.md", "company-analysis.md", "industry-analysis.md",
    "financial-analysis.md", "competition.md", "valuation-narrative.md", "catalysts-risks.md",
    "translation.md", "slide-compression.md", "glossary.md",
]
REQUIRED_SECTIONS = [
    "## Purpose and non-goals", "## Required inputs", "## Required output", "## Schema reference",
    "## Hard constraints", "## Missing-data behaviour", "## Hallucination and citation rules",
    "## Positive example", "## Negative example", "## Acceptance notes",
]

failures: list[str] = []
passes: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    if ok:
        passes.append(label)
    else:
        failures.append(f"{label}{': ' + detail if detail else ''}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------- 1. Catalogue completeness and section contract ----------

def check_catalogue() -> None:
    for name in PROMPT_FILES:
        p = PROMPTS / name
        if not p.exists():
            check(False, f"catalogue/{name}", "file missing")
            continue
        text = p.read_text(encoding="utf-8")
        fm = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        check(bool(fm), f"catalogue/{name}/frontmatter")
        if fm:
            check("prompt_id:" in fm.group(1) and "version:" in fm.group(1),
                  f"catalogue/{name}/frontmatter-fields")
        missing = [s for s in REQUIRED_SECTIONS if s not in text]
        check(not missing, f"catalogue/{name}/sections", f"missing {missing}")


# ---------- 2. Schema validation of final artefacts ----------

def check_schemas() -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        check(False, "schemas/jsonschema-installed", "pip install jsonschema")
        return
    pairs = [
        ("research-package.schema.json", "example-research-package.json"),
        ("slide-deck.schema.json", "example-slide-deck.zh-CN.json"),
        ("slide-deck.schema.json", "example-slide-deck.en-AU.json"),
    ]
    for schema_f, inst_f in pairs:
        schema = load(SCHEMA_DIR / schema_f)
        Draft202012Validator.check_schema(schema)
        errs = list(Draft202012Validator(schema).iter_errors(load(SCHEMA_EXAMPLES / inst_f)))
        check(not errs, f"schemas/{inst_f}", "; ".join(e.message[:80] for e in errs[:3]))


# ---------- 3. Fixture pipeline consistency ----------

def check_fixtures() -> None:
    ev = load(EXAMPLES / "01-parsed-evidence.json")
    ex = load(EXAMPLES / "02-extraction-output.json")
    sv = load(EXAMPLES / "03-source-verification-output.json")
    an = load(EXAMPLES / "04-analysis-claims.json")
    vc = load(EXAMPLES / "05-valuation-catalysts-risks.json")

    chunks = {c["source_id"]: c for c in ev["evidence_chunks"]}
    prov_fields = ["value", "unit", "currency", "period", "as_of_date", "source_id",
                   "source_url_or_document", "retrieved_at"]

    for m in ex["candidate_metrics"]:
        cid = m["candidate_id"]
        check(all(f in m for f in prov_fields), f"fixtures/{cid}/provenance-fields")
        check(m["source_id"] in chunks, f"fixtures/{cid}/source-known")
        check(m["quote"] in chunks[m["source_id"]]["text"], f"fixtures/{cid}/quote-verbatim")
    for c in ex["candidate_claims"]:
        check(c["type"] == "fact", f"fixtures/{c['candidate_id']}/fact-only")
        check(c["quote"] in chunks[c["source_ids"][0]]["text"],
              f"fixtures/{c['candidate_id']}/quote-verbatim")

    cand_ids = {m["candidate_id"] for m in ex["candidate_metrics"]} | \
               {c["candidate_id"] for c in ex["candidate_claims"]}
    verdict_ids = {v["candidate_id"] for v in sv["verdicts"]}
    check(cand_ids == verdict_ids, "fixtures/verdict-coverage",
          f"missing={cand_ids - verdict_ids} unknown={verdict_ids - cand_ids}")
    for v in sv["verdicts"]:
        if v["verdict"] == "verified":
            check(all(v["checks"].values()), f"fixtures/{v['candidate_id']}/verified-checks-true")
        else:
            check(len(v["reasons"]) >= 1, f"fixtures/{v['candidate_id']}/rejection-reasoned")
    rejected = [v["candidate_id"] for v in sv["verdicts"] if v["verdict"] == "rejected"]
    check("CMET-090" in rejected, "fixtures/bad-candidate-rejected")

    known_sources = set(chunks) | {"SRC-002"}  # SRC-002 = market-data API source in the package
    all_claims = list(an["claims"]) + list(vc["s4_valuation_narrative"]["claims"]) + \
        list(vc["s5_catalysts_risks"]["supporting_claims"])
    claim_ids = {c["claim_id"] for c in all_claims} | {"CLM-002", "CLM-008"}  # promoted S1 facts
    for c in all_claims:
        t = c["type"]
        if t == "fact":
            check(bool(c.get("source_ids")), f"fixtures/{c['claim_id']}/fact-sourced")
        elif t == "inference":
            check(bool(c.get("source_ids") or c.get("metric_ids") or c.get("based_on_claim_ids")),
                  f"fixtures/{c['claim_id']}/inference-chained")
        for s in c.get("source_ids", []):
            check(s in known_sources, f"fixtures/{c['claim_id']}/source-resolves", s)
        for b in c.get("based_on_claim_ids", []):
            check(b in claim_ids, f"fixtures/{c['claim_id']}/chain-resolves", b)

    s4 = vc["s4_valuation_narrative"]
    check(s4["rating"] in {"buy", "accumulate", "hold", "reduce", "sell", "not_rated"},
          "fixtures/s4/rating-enum")
    check(len(s4["counterevidence_claim_ids"]) >= 1, "fixtures/s4/counterevidence-present")
    s5 = vc["s5_catalysts_risks"]
    check(len(s5["risks"]) >= 3, "fixtures/s5/min-3-risks")
    ce = set(s4["counterevidence_claim_ids"])
    check(any(r["claim_id"] in ce for r in s5["risks"]), "fixtures/s5/risk-chains-counterevidence")
    for r in s5["risks"]:
        check(r["severity"] in {"low", "medium", "high"} and r["likelihood"] in {"low", "medium", "high"},
              f"fixtures/{r['risk_id']}/grading-enum")
    for cat in s5["catalysts"]:
        claim = next((c for c in all_claims if c["claim_id"] == cat["claim_id"]), None)
        if claim:
            check(claim["type"] in {"inference", "opinion"}, f"fixtures/{cat['catalyst_id']}/future-typed")


# ---------- 4. Bilingual numeric/ID/terminology consistency (QC-03 prototype) ----------

SCALES = {"亿": 1e8, "万": 1e4, "billion": 1e9, "million": 1e6, "bn": 1e9, "m": 1e6}
NUM_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(亿|万|billion|million|bn)?", re.I)
DATE_RE = re.compile(
    r"\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}\s+[A-Z][a-z]+\s+\d{4}|\bFY\d{4}\b"
    r"|\d{4}-\d{4}|\d{4}(?=[财年])|\b\d{4}\b|Q[1-4]|H[12]"
)
RATING_MAP = {"买入": "Buy", "增持": "Accumulate", "持有": "Hold", "减持": "Reduce", "卖出": "Sell"}


def numeric_tokens(text: str) -> set[float]:
    cleaned = DATE_RE.sub(" ", text)
    out = set()
    for m in NUM_RE.finditer(cleaned):
        val = float(m.group(1).replace(",", ""))
        if m.group(2):
            val *= SCALES[m.group(2).lower()]
        out.add(round(val, 6))
    return out


def check_bilingual() -> None:
    tr = load(EXAMPLES / "06-translation-output.json")
    for t in tr["texts"]:
        path = t["path"]
        zh, en = t["zh_CN"], t["en_AU"]
        zt, et = numeric_tokens(zh), numeric_tokens(en)
        check(zt == et, f"bilingual/{path}/numbers", f"zh={sorted(zt)} en={sorted(et)}")
        zh_ids = set(re.findall(r"(?:MET|CLM|SRC|ASM|RSK|CAT)-\d{3}", zh))
        en_ids = set(re.findall(r"(?:MET|CLM|SRC|ASM|RSK|CAT)-\d{3}", en))
        check(zh_ids == en_ids, f"bilingual/{path}/ids")
        for zh_term, en_term in RATING_MAP.items():
            if zh_term in zh and ("评级" in zh or "维持" in zh):
                check(en_term in en, f"bilingual/{path}/rating-term", f"{zh_term}→{en_term}")

    pkg = load(SCHEMA_EXAMPLES / "example-research-package.json")

    def walk(obj):
        if isinstance(obj, dict):
            if set(obj) >= {"zh_CN", "en_AU"}:
                yield obj
            for v in obj.values():
                yield from walk(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from walk(v)

    for lt in walk(pkg):
        check(bool(lt["zh_CN"].strip()) and bool(lt["en_AU"].strip()), "bilingual/package/both-sides")


# ---------- 5. No unbound numbers in slide narrative fields (QC-01 prototype) ----------

def displayed_values(metric: dict, transform: str) -> set[float]:
    v = metric["value"]
    table = {"raw": 1, "percent": 1, "multiple": 1, "wan": 1e4, "yi": 1e8,
             "thousand": 1e3, "million": 1e6, "billion": 1e9}
    return {round(v / table[transform], 6)}


def check_deck_numbers() -> None:
    pkg = load(SCHEMA_EXAMPLES / "example-research-package.json")
    metrics = {m["metric_id"]: m for m in pkg["metrics"]}
    claims = {c["claim_id"]: c for c in pkg["claims"]}
    assumptions = {a["assumption_id"]: a for a in pkg["valuation"]["assumptions"]}

    for deck_name in ["example-slide-deck.zh-CN.json", "example-slide-deck.en-AU.json"]:
        deck = load(SCHEMA_EXAMPLES / deck_name)
        for slide in deck["slides"]:
            for block in slide["blocks"]:
                for text, refs, inline in narrative_units(block):
                    allowed: set[float] = set()
                    for dn in inline:
                        allowed |= displayed_values(metrics[dn["metric_id"]], dn["display_transform"])
                    for ref in refs:
                        if "metric_id" in ref:
                            m = metrics[ref["metric_id"]]
                            for tr in ("raw", "wan", "yi", "million", "billion"):
                                allowed |= displayed_values(m, tr)
                        if "claim_id" in ref:
                            c = claims[ref["claim_id"]]
                            allowed |= numeric_tokens(c["text"]["zh_CN"]) | numeric_tokens(c["text"]["en_AU"])
                        if "assumption_id" in ref:
                            allowed |= numeric_tokens(assumptions[ref["assumption_id"]]["value_text"])
                    toks = numeric_tokens(text)
                    unbound = {t for t in toks if not any(abs(t - a) < 1e-6 or
                               (a and abs(t / a - 1) < 5e-3) for a in allowed)}
                    check(not unbound, f"deck/{deck_name}/slide{slide['slide_no']}/unbound-numbers",
                          f"{sorted(unbound)} in '{text[:40]}…'")


def narrative_units(block: dict):
    bt = block["block_type"]
    if bt == "bullets":
        for b in block["bullets"]:
            yield b["text"], b["refs"], b.get("inline_numbers", [])
    elif bt == "text_panel":
        tp = block["text_panel"]
        if tp.get("style") != "disclaimer":
            yield tp["text"], tp["refs"], []
    elif bt == "football_field":
        for line in block["football_field"].get("assumption_lines", []):
            yield line["text"], line["refs"], []
    elif bt == "comparison_cards":
        for card in block["comparison_cards"]:
            for b in card["bullets"]:
                yield b["text"], b["refs"], []
    elif bt == "paired_columns":
        pc = block["paired_columns"]
        for item in pc["left_items"] + pc["right_items"]:
            if "description" in item:
                yield item["description"], item["refs"], []


# ---------- main ----------

def main() -> int:
    check_catalogue()
    check_schemas()
    check_fixtures()
    check_bilingual()
    check_deck_numbers()
    print(f"PASS {len(passes)} checks")
    if failures:
        print(f"FAIL {len(failures)} checks:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All validation checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
