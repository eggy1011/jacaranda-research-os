# research-schema

Phase 0 contracts owned by Claude Code. Two JSON Schemas (draft 2020-12) define the pipeline's structured hand-offs:

```text
evidence -> research-package.schema.json -> compiler -> slide-deck.schema.json -> renderer -> PPTX/PDF
```

## Files

| File | Purpose |
|---|---|
| `research-package.schema.json` | Single source of truth for one report: sources, metrics (8 provenance fields), typed claims (fact/inference/opinion), 12 sections, valuation, catalysts, risks, quality results, disclaimer. |
| `slide-deck.schema.json` | Renderer input. One deck per edition (`zh-CN`, `en-AU`, `bilingual-summary`). Every displayed number is a `metric_id` reference with a render-time `display_transform` — no literal numbers. |
| `examples/` | Handwritten fixtures using a **fictional** A-share company (`is_mock: true`). One research package + zh-CN and en-AU decks compiled from it. |

## Key invariants

1. Metrics always carry `value, unit, currency, period, as_of_date, source_id, source_url_or_document, retrieved_at`. `currency: null` only for non-monetary quantities.
2. LLMs never compute values: `computed_by` is `provider` or `deterministic_calc` (with formula + input metric IDs).
3. `fact` claims require ≥1 source; `inference` requires sources, metrics, or supporting claims; unsupported text can only be `opinion`.
4. All narrative text is a `{zh_CN, en_AU}` pair in the package; decks contain already-resolved single-language strings.
5. `valuation.counterevidence_claim_ids` (≥1) and ≥3 risks are mandatory; the conclusion/sources/disclaimer section cannot be removed.
6. Both language editions compile from the same package — same metric IDs, source IDs, assumptions, rating.

## Validating

```bash
python3 -m pip install jsonschema
python3 - <<'PY'
import json
from jsonschema import Draft202012Validator
for schema_f, inst_f in [
    ("research-package.schema.json", "examples/example-research-package.json"),
    ("slide-deck.schema.json", "examples/example-slide-deck.zh-CN.json"),
    ("slide-deck.schema.json", "examples/example-slide-deck.en-AU.json"),
]:
    v = Draft202012Validator(json.load(open(schema_f)))
    errs = list(v.iter_errors(json.load(open(inst_f))))
    print(("PASS " if not errs else "FAIL ") + inst_f)
    for e in errs[:5]: print("  -", e.message)
PY
```

Cross-reference integrity (every `MET-/CLM-/SRC-/ASM-` ref resolves) is a semantic check beyond JSON Schema; see quality rubric QC-01 in `docs/RESEARCH_METHODOLOGY.md`. Codex should implement it in the validation layer.

## Versioning

`schema_version` is pinned (`const`). Breaking changes bump the version and go through an Issue + PR reviewed by Codex.
