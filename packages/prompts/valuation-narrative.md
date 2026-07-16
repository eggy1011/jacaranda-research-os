---
prompt_id: valuation-narrative
version: 0.1.0
stage: S4
consumes: code-computed valuation metrics, assumptions, all S3 claims
produces: assumption rationales, scenario narratives, rating, counterevidence
---

# S4 — Valuation narrative

## Purpose and non-goals

Explain the valuation the deterministic calc service produced: why the assumptions are reasonable,
what each scenario means, what rating follows, and — mandatorily — what argues against it. This
fills `valuation` (rationale claims, scenarios, rating, counterevidence) in the research package.
Non-goals: computing or adjusting any valuation number, choosing assumption values (code + human
set them), summarising the whole report.

## Required inputs

```json
{
  "valuation_metrics": [ …MET- objects: target/current price, method low/high, computed_by=deterministic_calc… ],
  "assumptions": [ { "assumption_id": "ASM-001", "name_authored": "WACC", "value_text": "9.5%" } ],
  "scenario_metrics": { "base": "MET-006" },
  "prior_claims": [ …all S3 claims… ],
  "next_claim_id": "CLM-060"
}
```

## Required output

```json
{
  "assumption_rationales": [ { "assumption_id": "ASM-001", "rationale_claim_id": "CLM-060" } ],
  "scenario_narratives": { "base": "CLM-061" },
  "rating": "accumulate",
  "rating_claim_id": "CLM-062",
  "counterevidence_claim_ids": ["CLM-063"],
  "claims": [ … ],
  "insufficient": []
}
```

## Schema reference

`research-package.schema.json#/properties/valuation` — note `counterevidence_claim_ids` has
`minItems: 1` and rating enum is {buy, accumulate, hold, reduce, sell, not_rated}. Scenario
narratives feed `$defs/scenario.narrative_claim_id`.

## Hard constraints

- Allowed claim types: inference and opinion. The rating claim is always `opinion`.
- Every valuation figure mentioned comes verbatim from a `valuation_metrics` entry.
- Each assumption gets exactly one rationale claim explaining *why this value*, chained to
  evidence (sector data, company leverage, etc.) — not restating the number.
- ≥1 counterevidence claim with `is_counterevidence: true`, substantive (a real bear argument
  grounded in prior claims), not a token disclaimer.
- Rating must be consistent with target vs current price direction; if evidence cannot support a
  view, output `not_rated` — that is a legitimate result.

## Missing-data behaviour

Missing scenario metrics (e.g. no bull/bear computed) mean those scenarios are omitted — never
sketch an uncomputed scenario narratively. If assumptions arrive without evidence context, the
rationale claim states 资料不足 and flags `needs_review`.

## Hallucination and citation rules

- No new numbers, no sensitivity musings with invented deltas ("每±0.5% WACC影响约…" is banned
  unless that sensitivity exists as a metric).
- Counterevidence must chain to real prior claims; inventing a strawman bear case to knock down
  is a fabrication.
- Analyst-consensus or street-view references require sources; there is no "market expects".

## Positive example

```json
{ "claim_id": "CLM-063", "type": "inference", "is_counterevidence": true,
  "text": { "zh_CN": "反方证据：行业产能扩张较快，若下游资本开支放缓，基准情景的收入假设可能过于乐观。",
            "en_AU": "反方证据：行业产能扩张较快，若下游资本开支放缓，基准情景的收入假设可能过于乐观。" },
  "based_on_claim_ids": ["CLM-051"], "source_ids": ["SRC-004"],
  "confidence": 0.6, "review_status": "unreviewed" }
```

A real bear argument that attacks the base-case assumption specifically, chained to the S3d
competitive-pressure inference and its source.

## Negative example

```json
{ "claim_id": "CLM-064", "type": "opinion",
  "text": { "zh_CN": "我们微调WACC至9.0%后目标价可达36.1元，性价比更高，维持买入。", "en_AU": "…" },
  "metric_ids": ["MET-006"], "confidence": 0.8, "review_status": "unreviewed" }
```

Triple breach: the model re-ran the DCF in its head (36.1元 exists in no metric), it *changed an
assumption* (9.0% vs ASM-001's 9.5%), and the rating word (买入/buy) contradicts the pipeline's
rating field (accumulate). S4 explains the model's valuation; it never operates the model.

## Acceptance notes

Machine checks: rating enum valid; rating claim type == opinion; ≥1 counterevidence claim with
flag set and resolvable chain; every assumption in input has exactly one rationale mapping; all
numeric tokens match `valuation_metrics` values; scenario narrative refs resolve; no claim
alters an assumption `value_text`.
