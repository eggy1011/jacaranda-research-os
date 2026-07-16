---
prompt_id: catalysts-risks
version: 0.1.0
stage: S5
consumes: all prior claims and metrics
produces: catalysts[] and risks[] arrays
---

# S5 — Catalysts and risks

## Purpose and non-goals

Assemble the dated, direction-tagged catalysts and the categorised, graded risks for the package's
`catalysts` and `risks` arrays. Non-goals: discovering new evidence, re-arguing the thesis,
generic risk boilerplate ("宏观经济波动风险" with no company linkage).

## Required inputs

```json
{
  "as_of_date": "2026-07-10",
  "prior_claims": [ … ],
  "verified_metrics": [ … ],
  "next_ids": { "claim": "CLM-070", "catalyst": "CAT-001", "risk": "RSK-001" }
}
```

## Required output

`catalysts[]` and `risks[]` conforming exactly to the package schema, plus any new supporting
claims (each catalyst/risk needs a `claim_id`; reuse a prior claim or author a new one here).

## Schema reference

**Output contract (machine-readable): `schemas/stage-envelopes.schema.json#/$defs/s5_output`** — bound to `task_name: catalysts_risks` in `registry.json`.

`research-package.schema.json#/properties/catalysts` (timeframe ∈ {0-3m, 3-12m, 12m+}, direction,
optional expected_date) and `#/properties/risks` (`minItems: 3`; category enum; severity and
likelihood ∈ {low, medium, high}; optional mitigation).

## Hard constraints

- Every event with a date later than `as_of_date` is future-looking: its claim must be typed
  `inference` or `opinion`, never `fact` — even when a source announces the plan (the *plan* is a
  fact; the *occurrence* is not).
- ≥3 risks, each specific to this company/thesis and chained to evidence; at least one risk must
  correspond to the S4 counterevidence.
- Severity/likelihood grading needs a stated basis in the claim text (magnitude of exposure,
  historical frequency, dependency shares…), not vibes.
- Timeframe and expected_date must agree (an expected_date 5 months out cannot sit in 0-3m).

## Missing-data behaviour

Fewer than 3 supportable risks is a **non-retryable** failure: report it and stop rather than
padding with generic macro risks. Undated catalysts stay in the array without `expected_date` and
cannot appear on timeline layouts (L08 requires dates).

## Hallucination and citation rules

- Catalyst dates come only from sourced company statements (guidance, announcements); inferring a
  quarter from habit ("公司通常四季度发布…") is banned without a source establishing the pattern.
- Risk likelihoods must not present precise probabilities ("30%概率") unless a source or scenario
  metric provides them.
- Mitigations only if evidenced (announced hedges, contracts, diversification) — hopeful
  mitigations are omitted.

## Positive example

```json
{ "risk_id": "RSK-004",
  "title": { "zh_CN": "客户集中度较高", "en_AU": "客户集中度较高" },
  "claim_id": "CLM-008", "category": "operations",
  "severity": "medium", "likelihood": "medium" }
```

Reuses the verified concentration fact (42% top-five share) as its evidence chain; grading is
defensible from the cited magnitude; category matches the schema enum.

## Negative example

```json
{ "risk_id": "RSK-005",
  "title": { "zh_CN": "宏观经济下行风险", "en_AU": "…" },
  "claim_id": "CLM-071", "category": "macro", "severity": "low", "likelihood": "low" }
```

where CLM-071 reads 「宏观经济波动可能对公司产生一定影响」 with no source, no chain, no company
linkage. This is padding to reach `minItems: 3` — it survives JSON Schema validation but fails the
rubric (QC-05/QC-10): every risk must say *what specifically breaks for this company*.

## Acceptance notes

Machine checks: ≥3 risks; enums valid; every `claim_id` resolves; future-dated events typed
inference/opinion; timeframe/expected_date agreement; ≥1 risk chained to a counterevidence claim;
no two risks share a claim without distinct titles.
