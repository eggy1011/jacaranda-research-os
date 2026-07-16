#!/usr/bin/env python3
"""Validator for the prompt catalogue and its end-to-end fixtures (Issue #13).

Run from anywhere:  python3 packages/prompts/tests/validate.py [--json]
Requires: pip install jsonschema

Failures are structured records — {code, stage, path, retryable, detail} — so the same
labels can serve as LLMProvider retry feedback. --json emits them as a JSON document.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
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
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

failures: list[dict] = []
pass_count = 0


def check(ok: bool, code: str, path: str, retryable: bool = True,
          stage: str = "validator", detail: str = "") -> None:
    global pass_count
    if ok:
        pass_count += 1
    else:
        failures.append({"code": code, "stage": stage, "path": path,
                         "retryable": retryable, "detail": detail})


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        check(False, "invalid_json", str(path.relative_to(ROOT)), True, "loader", str(e))
        return {}


# ---------- 1. Catalogue completeness, frontmatter, section contract ----------

def check_catalogue() -> None:
    seen_ids: dict[str, str] = {}
    for name in PROMPT_FILES:
        p = PROMPTS / name
        rel = f"packages/prompts/{name}"
        if not p.exists():
            check(False, "missing_required_block", rel, False, "catalogue", "file missing")
            continue
        text = p.read_text(encoding="utf-8")
        fm = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        check(bool(fm), "missing_required_block", f"{rel}#frontmatter", False, "catalogue")
        if fm:
            fields = dict(
                (k.strip(), v.strip()) for k, v in
                (line.split(":", 1) for line in fm.group(1).splitlines() if ":" in line)
            )
            pid, ver = fields.get("prompt_id", ""), fields.get("version", "")
            check(bool(pid), "missing_required_block", f"{rel}#prompt_id", False, "catalogue")
            check(bool(SEMVER_RE.match(ver)), "schema_validation_failed",
                  f"{rel}#version", False, "catalogue", f"not semver: {ver!r}")
            check(pid not in seen_ids, "internal_contradiction", f"{rel}#prompt_id", False,
                  "catalogue", f"duplicate of {seen_ids.get(pid, '')}")
            seen_ids[pid] = name
        missing = [s for s in REQUIRED_SECTIONS if s not in text]
        check(not missing, "missing_required_block", f"{rel}#sections", False,
              "catalogue", f"missing {missing}")

    registry = load(PROMPTS / "registry.json")
    tasks = {t["task_name"]: t for t in registry.get("tasks", [])}
    # every schema pointer in the registry must resolve to a real definition
    for t in registry.get("tasks", []):
        for field in ("output_schema", "input_schema"):
            if field not in t:
                continue
            ptr = t[field]
            fpath, _, frag = ptr.partition("#")
            target = (PROMPTS / fpath).resolve()
            if not target.exists():
                check(False, "dangling_reference", f"registry.json#{t['task_name']}/{field}",
                      False, "catalogue", f"file not found: {fpath}")
                continue
            doc = load(target)
            node = doc
            ok = True
            for part in [p for p in frag.split("/") if p]:
                part = part.replace("~1", "/").replace("~0", "~")
                if isinstance(node, dict) and part in node:
                    node = node[part]
                else:
                    ok = False
                    break
            check(ok, "dangling_reference", f"registry.json#{t['task_name']}/{field}",
                  False, "catalogue", f"pointer does not resolve: {ptr}")
    check("glossary" not in {t.get("prompt_file") for t in tasks.values()} and
          "glossary.md" not in {t.get("prompt_file") for t in tasks.values()},
          "internal_contradiction", "registry.json#glossary-excluded", False, "catalogue")
    executable = [f for f in PROMPT_FILES if f != "glossary.md"]
    registered = {t["prompt_file"] for t in tasks.values()}
    check(set(executable) == registered, "missing_required_block",
          "registry.json#task-coverage", False, "catalogue",
          f"unregistered={set(executable) - registered} unknown={registered - set(executable)}")
    for t in tasks.values():
        check("output_schema" in t and "prompt_version" in t, "missing_required_block",
              f"registry.json#{t['task_name']}", False, "catalogue")


# ---------- 2. Schema validation: final artefacts AND stage fixtures ----------

def make_validators():
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    pkg_schema = load(SCHEMA_DIR / "research-package.schema.json")
    deck_schema = load(SCHEMA_DIR / "slide-deck.schema.json")
    env_schema = load(PROMPTS / "schemas" / "stage-envelopes.schema.json")
    registry = Registry().with_resources([
        (pkg_schema["$id"], Resource.from_contents(pkg_schema)),
        (deck_schema["$id"], Resource.from_contents(deck_schema)),
        (env_schema["$id"], Resource.from_contents(env_schema)),
    ])

    def validator_for(schema_doc, pointer=None):
        schema = schema_doc if pointer is None else {"$ref": f"{schema_doc['$id']}#{pointer}"}
        return Draft202012Validator(schema, registry=registry)

    return pkg_schema, deck_schema, env_schema, validator_for


def check_schemas(validator_for, pkg_schema, deck_schema, env_schema) -> None:
    for schema_doc, inst_f, stage in [
        (pkg_schema, SCHEMA_EXAMPLES / "example-research-package.json", "assembly"),
        (deck_schema, SCHEMA_EXAMPLES / "example-slide-deck.zh-CN.json", "S7"),
        (deck_schema, SCHEMA_EXAMPLES / "example-slide-deck.en-AU.json", "S7"),
    ]:
        errs = list(validator_for(schema_doc).iter_errors(load(inst_f)))
        for e in errs[:5]:
            check(False, "schema_validation_failed", f"{inst_f.name}/{e.json_path}", True,
                  stage, e.message[:120])
        check(not errs, "schema_validation_failed", inst_f.name, True, stage)

    stage_targets = [
        ("02-extraction-output.json", None, "/$defs/s1_output", "S1"),
        ("03-source-verification-output.json", None, "/$defs/s2_output", "S2"),
        ("04-analysis-claims.json", "s3a", "/$defs/s3a_output", "S3a"),
        ("04-analysis-claims.json", "s3b", "/$defs/s3b_output", "S3b"),
        ("04-analysis-claims.json", "s3c", "/$defs/s3c_output", "S3c"),
        ("04-analysis-claims.json", "s3d", "/$defs/s3d_output", "S3d"),
        ("05-valuation-catalysts-risks.json", "s4_valuation_narrative", "/$defs/s4_output", "S4"),
        ("05-valuation-catalysts-risks.json", "s5_catalysts_risks", "/$defs/s5_output", "S5"),
        ("06-translation-output.json", None, "/$defs/s6_output", "S6"),
        ("07-slide-plan.json", None, "/$defs/s7_plan_output", "S7"),
        ("08-slide-call.json", "input", "/$defs/s7_slide_input", "S7"),
    ]
    for fname, key, pointer, stage in stage_targets:
        doc = load(EXAMPLES / fname)
        inst = doc.get(key, {}) if key else doc
        errs = list(validator_for(env_schema, pointer).iter_errors(inst))
        for e in errs[:5]:
            check(False, "schema_validation_failed",
                  f"{fname}{'/' + key if key else ''}/{e.json_path}", True, stage, e.message[:120])
        check(not errs, "schema_validation_failed", f"{fname}{'/' + key if key else ''}",
              True, stage)

    # slide-call output is a single deck slide
    slide_out = load(EXAMPLES / "08-slide-call.json").get("output", {})
    errs = list(validator_for(deck_schema, "/$defs/slide").iter_errors(slide_out))
    for e in errs[:5]:
        check(False, "schema_validation_failed", f"08-slide-call.json/output/{e.json_path}",
              True, "S7", e.message[:120])
    check(not errs, "schema_validation_failed", "08-slide-call.json/output", True, "S7")


def check_slide_plan(pkg: dict) -> None:
    """Semantic S7 plan rules that JSON Schema cannot express."""
    plan = load(EXAMPLES / "07-slide-plan.json")
    call = load(EXAMPLES / "08-slide-call.json")
    stubs = plan["slide_stubs"]
    nos = [s["slide_no"] for s in stubs]
    check(nos == list(range(1, len(nos) + 1)), "internal_contradiction",
          "07/slide_no-contiguous-unique", True, "S7", f"got {nos}")
    check(stubs[0]["layout"] == "L01_cover", "internal_contradiction", "07/first-is-cover",
          True, "S7")
    check(stubs[-1]["layout"] == "L11_conclusion_sources", "internal_contradiction",
          "07/last-is-conclusion", True, "S7")
    sections = {s["section_id"] for s in stubs}
    mandatory = {"cover", "investment_thesis", "risks", "conclusion_sources_disclaimer"}
    check(mandatory <= sections, "missing_required_block", "07/mandatory-sections", False,
          "S7", f"missing {mandatory - sections}")
    known_c = {c["claim_id"] for c in pkg["claims"]}
    known_m = {m["metric_id"] for m in pkg["metrics"]}
    for s in stubs:
        for cid in s["claim_ids"]:
            check(cid in known_c, "dangling_reference", f"07/slide{s['slide_no']}/{cid}", True, "S7")
        for mid in s["metric_ids"]:
            check(mid in known_m, "dangling_reference", f"07/slide{s['slide_no']}/{mid}", True, "S7")

    stub, out = call["input"]["slide_stub"], call["output"]
    check(out["slide_no"] == stub["slide_no"] and out["layout"] == stub["layout"],
          "internal_contradiction", "08/output-matches-stub", True, "S7")
    excerpt = call["input"]["package_excerpt"]
    given_ids = {m["metric_id"] for m in excerpt["metrics"]} | \
                {c["claim_id"] for c in excerpt["claims"]} | \
                {s["source_id"] for s in excerpt["sources"]} | \
                {a["assumption_id"] for a in excerpt.get("assumptions", [])}
    used = set(re.findall(r"(?:MET|CLM|SRC|ASM)-\d{3}", json.dumps(out)))
    check(used <= given_ids, "dangling_reference", "08/output-cites-only-excerpt", True, "S7",
          f"cited outside excerpt: {used - given_ids}")


# ---------- 3. Fixture pipeline consistency and full cross-reference audit ----------

ID_PATTERNS = {"MET": r"MET-\d{3}", "CLM": r"CLM-\d{3}", "SRC": r"SRC-\d{3}",
               "ASM": r"ASM-\d{3}", "RSK": r"RSK-\d{3}", "CAT": r"CAT-\d{3}"}


def check_fixtures(pkg: dict) -> None:
    ev = load(EXAMPLES / "01-parsed-evidence.json")
    ex = load(EXAMPLES / "02-extraction-output.json")
    sv = load(EXAMPLES / "03-source-verification-output.json")
    an = load(EXAMPLES / "04-analysis-claims.json")
    vc = load(EXAMPLES / "05-valuation-catalysts-risks.json")
    tr = load(EXAMPLES / "06-translation-output.json")

    chunks = {c["source_id"]: c for c in ev["evidence_chunks"]}
    for m in ex["candidate_metrics"]:
        cid = m["candidate_id"]
        check(m["source_id"] in chunks, "dangling_reference", f"02/{cid}/source_id", True, "S1")
        if m["source_id"] in chunks:
            check(m["quote"] in chunks[m["source_id"]]["text"], "internal_contradiction",
                  f"02/{cid}/quote", False, "S1", "quote not verbatim in cited chunk")
    for c in ex["candidate_claims"]:
        check(c["quote"] in chunks[c["source_ids"][0]]["text"], "internal_contradiction",
              f"02/{c['candidate_id']}/quote", False, "S1")

    cand_ids = {m["candidate_id"] for m in ex["candidate_metrics"]} | \
               {c["candidate_id"] for c in ex["candidate_claims"]}
    verdicts = {v["candidate_id"]: v for v in sv["verdicts"]}
    check(cand_ids == set(verdicts), "dangling_reference", "03/verdict-coverage", True, "S2",
          f"missing={cand_ids - set(verdicts)} unknown={set(verdicts) - cand_ids}")
    check(len(sv["verdicts"]) == len(verdicts), "internal_contradiction",
          "03/duplicate-verdicts", True, "S2")
    check(verdicts.get("CMET-090", {}).get("verdict") == "rejected",
          "internal_contradiction", "03/CMET-090", False, "S2",
          "the planted bad candidate must be rejected")

    # ID universes
    pkg_metrics = {m["metric_id"]: m for m in pkg.get("metrics", [])}
    pkg_sources = {s["source_id"] for s in pkg.get("sources", [])}
    pkg_assumptions = {a["assumption_id"]: a for a in pkg.get("valuation", {}).get("assumptions", [])}
    stage_claims: dict[str, dict] = {}
    dup_paths = []
    envelopes = [("04/" + k, an[k]) for k in ("s3a", "s3b", "s3c", "s3d")] + \
                [("05/s4", vc["s4_valuation_narrative"])]
    for path, env in envelopes:
        for c in env.get("claims", []):
            if c["claim_id"] in stage_claims:
                dup_paths.append(f"{path}/{c['claim_id']}")
            stage_claims[c["claim_id"]] = c
    for c in vc["s5_catalysts_risks"].get("supporting_claims", []):
        if c["claim_id"] in stage_claims:
            dup_paths.append(f"05/s5/{c['claim_id']}")
        stage_claims[c["claim_id"]] = c
    check(not dup_paths, "internal_contradiction", "fixtures/duplicate-claim-ids", True,
          "assembly", str(dup_paths))
    for coll, key, label in [(pkg.get("metrics", []), "metric_id", "metrics"),
                             (pkg.get("claims", []), "claim_id", "claims"),
                             (pkg.get("sources", []), "source_id", "sources")]:
        ids = [x[key] for x in coll]
        check(len(ids) == len(set(ids)), "internal_contradiction",
              f"package/duplicate-{label}", True, "assembly")

    known_claims = set(stage_claims) | {"CLM-002", "CLM-008"}  # S1-promoted facts
    known_metrics = set(pkg_metrics)
    known_sources = set(chunks) | pkg_sources

    def audit_claim(c: dict, path: str, stage: str) -> None:
        if c["type"] == "fact":
            check(bool(c.get("source_ids")), "schema_validation_failed",
                  f"{path}/source_ids", True, stage, "fact without sources")
        elif c["type"] == "inference":
            check(bool(c.get("source_ids") or c.get("metric_ids") or c.get("based_on_claim_ids")),
                  "dangling_reference", f"{path}/support-chain", True, stage)
        for s in c.get("source_ids", []):
            check(s in known_sources, "dangling_reference", f"{path}/source_ids/{s}", True, stage)
        for m in c.get("metric_ids", []):
            check(m in known_metrics, "dangling_reference", f"{path}/metric_ids/{m}", True, stage)
        for b in c.get("based_on_claim_ids", []):
            check(b in known_claims, "dangling_reference", f"{path}/based_on/{b}", True, stage)

    for path, env in envelopes:
        for c in env.get("claims", []):
            audit_claim(c, f"{path}/{c['claim_id']}", path.split("/")[-1])
        for section, ids in env.get("section_assignment", {}).items():
            for cid in ids:
                check(cid in known_claims, "dangling_reference",
                      f"{path}/section_assignment/{section}/{cid}", True, "assembly")
        for node in env.get("value_chain_nodes", []):
            if node.get("claim_id"):
                check(node["claim_id"] in known_claims, "dangling_reference",
                      f"{path}/value_chain/{node['claim_id']}", True, "S3b")
        for ent in env.get("comparison_entities", []):
            for m in ent["metric_ids"]:
                check(m in known_metrics, "dangling_reference",
                      f"{path}/comparison/{m}", True, "S3d")
            for cid in ent["claim_ids"]:
                check(cid in known_claims, "dangling_reference",
                      f"{path}/comparison/{cid}", True, "S3d")
            check(bool(ent["metric_ids"]) or ent["limited_data"], "internal_contradiction",
                  f"{path}/comparison/{ent['entity_authored']}", True, "S3d",
                  "no metrics but limited_data is false")
        for rc in env.get("requested_calculations", []):
            for m in rc["input_metric_ids"]:
                check(m in known_metrics, "dangling_reference",
                      f"{path}/requested_calculations/{rc['request_id']}/{m}", True, "S3c")

    s4 = vc["s4_valuation_narrative"]
    for ar in s4["assumption_rationales"]:
        check(ar["assumption_id"] in pkg_assumptions, "dangling_reference",
              f"05/s4/assumption_rationales/{ar['assumption_id']}", True, "S4")
        check(ar["rationale_claim_id"] in known_claims, "dangling_reference",
              f"05/s4/assumption_rationales/{ar['rationale_claim_id']}", True, "S4")
    mapped = [ar["assumption_id"] for ar in s4["assumption_rationales"]]
    check(len(mapped) == len(set(mapped)), "internal_contradiction",
          "05/s4/assumption_rationales/duplicates", True, "S4")
    check(set(mapped) == set(pkg_assumptions), "missing_required_block",
          "05/s4/assumption_rationales/completeness", True, "S4",
          f"unmapped={set(pkg_assumptions) - set(mapped)} unknown={set(mapped) - set(pkg_assumptions)}")
    for ar in s4["assumption_rationales"]:
        pkg_a = pkg_assumptions.get(ar["assumption_id"])
        if pkg_a:
            check(pkg_a["rationale_claim_id"] == ar["rationale_claim_id"],
                  "internal_contradiction",
                  f"05/s4/assumption_rationales/{ar['assumption_id']}/rationale-match", True, "S4",
                  "stage mapping disagrees with the final package")
    check(s4["rating_claim_id"] in known_claims, "dangling_reference",
          "05/s4/rating_claim_id", True, "S4")
    ce = set(s4["counterevidence_claim_ids"])
    for cid in ce:
        check(cid in known_claims, "dangling_reference", f"05/s4/counterevidence/{cid}", True, "S4")
        flagged = stage_claims.get(cid, {}).get("is_counterevidence", False)
        check(flagged, "internal_contradiction", f"05/s4/counterevidence/{cid}/flag", True, "S4")

    s5 = vc["s5_catalysts_risks"]
    for r in s5["risks"]:
        check(r["claim_id"] in known_claims, "dangling_reference",
              f"05/s5/{r['risk_id']}/claim_id", True, "S5")
    for cat in s5["catalysts"]:
        check(cat["claim_id"] in known_claims, "dangling_reference",
              f"05/s5/{cat['catalyst_id']}/claim_id", True, "S5")
        claim = stage_claims.get(cat["claim_id"])
        if claim:
            check(claim["type"] in {"inference", "opinion"}, "internal_contradiction",
                  f"05/s5/{cat['catalyst_id']}/future-typed", False, "S5")
    check(any(r["claim_id"] in ce for r in s5["risks"]), "missing_required_block",
          "05/s5/risk-chains-counterevidence", False, "S5")

    for t in tr["texts"]:
        for ref in re.findall(r"(?:MET|CLM|SRC|ASM|RSK|CAT)-\d{3}", t["path"]):
            pool = known_claims | known_metrics | known_sources | set(pkg_assumptions) | \
                   {r["risk_id"] for r in s5["risks"]} | {c["catalyst_id"] for c in s5["catalysts"]}
            check(ref in pool, "dangling_reference", f"06/{t['path']}/{ref}", True, "S6")


# ---------- 4. Bilingual consistency (QC-03 prototype) ----------

SCALES = {"亿": 1e8, "万": 1e4, "billion": 1e9, "million": 1e6, "bn": 1e9, "m": 1e6}
NUM_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(亿|万|billion|million|bn)?", re.I)
DATE_RE = re.compile(
    r"\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}\s+[A-Z][a-z]+\s+\d{4}|\bFY\d{4}\b"
    r"|\d{4}-\d{4}|\d{4}(?=[财年])|\b\d{4}\b|Q[1-4]|H[12]"
)
RATING_MAP = {"买入": "Buy", "增持": "Accumulate", "持有": "Hold", "减持": "Reduce", "卖出": "Sell"}
# unit words that must correspond 1:1 across editions (counted per text pair)
UNIT_PAIRS = [
    (["元/股", "每股"], [r"per share"]),
    (["亿"], [r"billion", r"\bbn\b"]),
    (["万"], [r"ten[- ]thousand", r"\bwan\b"]),
    (["倍"], [r"\btimes\b", r"\d+(?:\.\d+)?x\b"]),
    (["吨"], [r"tonne", r"\btons?\b"]),
]
ZH_HEDGES = ["可能", "或将", "有望", "预计", "若", "大概率"]
EN_HEDGES = ["may", "could", "likely", "expected", "if ", "should", "potential"]


def numeric_multiset(text: str, apply_scale: bool) -> Counter:
    cleaned = DATE_RE.sub(" ", text)
    out: Counter = Counter()
    for m in NUM_RE.finditer(cleaned):
        val = float(m.group(1).replace(",", ""))
        if apply_scale and m.group(2):
            val *= SCALES[m.group(2).lower()]
        out[round(val, 6)] += 1
    return out


def check_bilingual(pkg: dict) -> None:
    tr = load(EXAMPLES / "06-translation-output.json")
    paths = [t["path"] for t in tr["texts"]]
    check(len(paths) == len(set(paths)), "internal_contradiction",
          "06/duplicate-paths", True, "S6")
    zh_q = {"一季度": "Q1", "二季度": "Q2", "三季度": "Q3", "四季度": "Q4"}
    for t in tr["texts"]:
        path, zh, en = t["path"], t["zh_CN"], t["en_AU"]
        # period/date protection: years, quarters and FY markers must survive translation
        check(Counter(re.findall(r"\d{4}", zh)) == Counter(re.findall(r"\d{4}", en)),
              "internal_contradiction", f"06/{path}/year-parity", True, "S6")
        zq = Counter(v for k, v in zh_q.items() for _ in range(zh.count(k)))
        zq.update(re.findall(r"Q[1-4]", zh))
        check(zq == Counter(re.findall(r"Q[1-4]", en)), "internal_contradiction",
              f"06/{path}/quarter-parity", True, "S6")
        check(zh.count("财年") == len(re.findall(r"\bFY\d{4}", en)), "internal_contradiction",
              f"06/{path}/fiscal-year-parity", True, "S6")
        zt, et = numeric_multiset(zh, True), numeric_multiset(en, True)
        check(zt == et, "internal_contradiction", f"06/{path}/numbers", True, "S6",
              f"zh={dict(zt)} en={dict(et)} (multiset compare)")
        zh_ids = sorted(re.findall(r"(?:MET|CLM|SRC|ASM|RSK|CAT)-\d{3}", zh))
        en_ids = sorted(re.findall(r"(?:MET|CLM|SRC|ASM|RSK|CAT)-\d{3}", en))
        check(zh_ids == en_ids, "internal_contradiction", f"06/{path}/ids", True, "S6")
        check(("元" in zh or "人民币" in zh) == ("CNY" in en), "internal_contradiction",
              f"06/{path}/currency-parity", True, "S6")
        check(zh.count("%") == en.count("%"), "internal_contradiction",
              f"06/{path}/percent-parity", True, "S6")
        if any(h in zh for h in ZH_HEDGES):
            check(any(h in en.lower() for h in EN_HEDGES), "internal_contradiction",
                  f"06/{path}/hedge-preserved", True, "S6",
                  "zh hedged but en reads unconditional")
        # unit terms must correspond 1:1 (a unit swapped, dropped or invented fails)
        for zh_units, en_pats in UNIT_PAIRS:
            zc = sum(zh.count(u) for u in zh_units)
            ec = sum(len(re.findall(p, en, re.I)) for p in en_pats)
            check(zc == ec, "internal_contradiction", f"06/{path}/unit-parity", True, "S6",
                  f"zh {zh_units}×{zc} vs en {en_pats}×{ec}")
        # rating strength: the multiset of rating terms must match exactly — adding a
        # stronger rating alongside the correct one ("Accumulate / Buy") is a breach
        zh_ratings = Counter()
        for zh_term, en_term in RATING_MAP.items():
            zh_ratings[en_term] += zh.count(zh_term)
        en_ratings = Counter(m.capitalize() for m in re.findall(
            r"\b(Buy|Accumulate|Hold|Reduce|Sell)\b", en))
        zh_ratings, en_ratings = +zh_ratings, +en_ratings  # drop zero counts
        check(zh_ratings == en_ratings, "internal_contradiction",
              f"06/{path}/rating-strength", False, "S6",
              f"zh implies {dict(zh_ratings)} but en carries {dict(en_ratings)}")

    def walk(obj):
        if isinstance(obj, dict):
            if set(obj) >= {"zh_CN", "en_AU"}:
                yield obj
            for v in obj.values():
                yield from walk(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from walk(v)

    both = all(lt["zh_CN"].strip() and lt["en_AU"].strip() for lt in walk(pkg))
    check(both, "missing_required_block", "package/localizedText-both-sides", True, "S6")


# ---------- 5. No unbound numbers in slide narrative fields (QC-01 prototype) ----------

TRANSFORM = {"raw": 1, "percent": 1, "multiple": 1, "wan": 1e4, "yi": 1e8,
             "thousand": 1e3, "million": 1e6, "billion": 1e9}


def metric_displays(metric: dict) -> set[float]:
    out = set()
    for scale in TRANSFORM.values():
        for d in range(5):
            out.add(round(metric["value"] / scale, d))
    return out


# Block types whose free text is checked, plus structurally-numeric types where every number is
# already a displayNumber ref. Anything NOT listed fails closed (new blocks must be added here).
STRUCTURED_BLOCKS = {"kpi_cards", "chart", "table", "source_table"}
NARRATIVE_BLOCKS = {"bullets", "text_panel", "football_field", "comparison_cards",
                    "paired_columns", "flow", "timeline", "cover_meta"}


def check_deck_numbers(pkg: dict) -> None:
    metrics = {m["metric_id"]: m for m in pkg["metrics"]}
    claims = {c["claim_id"]: c for c in pkg["claims"]}
    assumptions = {a["assumption_id"]: a for a in pkg["valuation"]["assumptions"]}
    ticker = pkg["company"]["ticker"]
    cover_metric_ids = [mid for mid in (pkg["valuation"].get("target_price_metric_id"),
                                        pkg["valuation"].get("current_price_metric_id")) if mid]

    for deck_name in ["example-slide-deck.zh-CN.json", "example-slide-deck.en-AU.json"]:
        deck = load(SCHEMA_EXAMPLES / deck_name)
        for slide in deck["slides"]:
            for block in slide["blocks"]:
                bt = block["block_type"]
                if bt in STRUCTURED_BLOCKS:
                    continue
                check(bt in NARRATIVE_BLOCKS, "missing_required_block",
                      f"{deck_name}/slide{slide['slide_no']}/unknown-block/{bt}", False, "S7",
                      "block type not covered by the unbound-number check — fail closed")
                if bt not in NARRATIVE_BLOCKS:
                    continue
                for text, refs, inline in narrative_units(block, cover_metric_ids):
                    allowed: set[float] = set()
                    for dn in inline:
                        scale = TRANSFORM[dn["display_transform"]]
                        allowed.add(round(metrics[dn["metric_id"]]["value"] / scale,
                                          dn.get("decimals", 1)))
                    for ref in refs:
                        if "metric_id" in ref:
                            allowed |= metric_displays(metrics[ref["metric_id"]])
                        if "claim_id" in ref:
                            # ONLY the claim's bound metrics count — never its raw text numbers
                            for mid in claims[ref["claim_id"]].get("metric_ids", []):
                                allowed |= metric_displays(metrics[mid])
                        if "assumption_id" in ref:
                            allowed |= set(numeric_multiset(
                                assumptions[ref["assumption_id"]]["value_text"], False))
                    toks = numeric_multiset(text.replace(ticker, " "), False)
                    unbound = {t for t in toks if not any(abs(t - a) < 1e-6 for a in allowed)}
                    check(not unbound, "dangling_reference",
                          f"{deck_name}/slide{slide['slide_no']}/unbound-numbers", True, "S7",
                          f"{sorted(unbound)} in '{text[:40]}…'")


def narrative_units(block: dict, cover_metric_ids: list):
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
    elif bt == "flow":
        # flow nodes have no refs field; any numeral must come from the node's displayNumber
        for node in block["flow"]:
            inline = [node["number"]] if node.get("number") else []
            yield node["node_name"] + " " + node.get("description", ""), [], inline
    elif bt == "timeline":
        for ev in block["timeline"]:
            yield ev["label"] + " " + ev.get("description", ""), ev["refs"], []
    elif bt == "cover_meta":
        # cover lines carry no refs; rating/target figures are implicitly bound to the
        # valuation target/current price metrics (see slide-compression.md cover rule)
        cm = block["cover_meta"]
        implicit = [{"metric_id": mid} for mid in cover_metric_ids]
        for key in ("company_line", "rating_line", "date_line", "edition_line", "prepared_by"):
            if cm.get(key):
                yield cm[key], implicit, []


# ---------- main ----------

def main() -> int:
    as_json = "--json" in sys.argv
    try:
        pkg_schema, deck_schema, env_schema, validator_for = make_validators()
        pkg = load(SCHEMA_EXAMPLES / "example-research-package.json")
        check_catalogue()
        check_schemas(validator_for, pkg_schema, deck_schema, env_schema)
        check_fixtures(pkg)
        check_slide_plan(pkg)
        check_bilingual(pkg)
        check_deck_numbers(pkg)
    except Exception as e:  # surface as structured error, never a bare traceback
        failures.append({"code": "validator_crash", "stage": "validator", "path": "-",
                         "retryable": False, "detail": f"{type(e).__name__}: {e}"})

    if as_json:
        print(json.dumps({"passed": pass_count, "failed": len(failures),
                          "failures": failures}, ensure_ascii=False, indent=2))
    else:
        print(f"PASS {pass_count} checks")
        if failures:
            print(f"FAIL {len(failures)} checks:")
            for f in failures:
                print(f"  - [{f['code']}|{f['stage']}|retryable={f['retryable']}] "
                      f"{f['path']}  {f['detail']}")
        else:
            print("All validation checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
