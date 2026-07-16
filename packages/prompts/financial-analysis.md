---
prompt_id: financial-analysis
version: 0.1.0
stage: S3c
consumes: verified metrics including deterministic_calc outputs
produces: claims for historical_financials and forecast_drivers
---

# S3c — Financial analysis (interpretation only)

## Purpose and non-goals

Interpret the code-computed financial picture: what the trends are, what drives them, what the
forecast assumptions imply — for `historical_financials` and `forecast_drivers`. Non-goals:
**computing anything** (no sums, growth rates, margins, averages, extrapolations), valuation views
(S4), restating every metric as prose.

## Required inputs

Same envelope as S3a. `verified_metrics` includes provider metrics and deterministic_calc metrics
(growth rates, margins, forecast outputs) with their `calculation` objects visible.

## Required output

```json
{
  "claims": [ … ],
  "section_assignment": {
    "historical_financials": ["CLM-040"],
    "forecast_drivers": ["CLM-041"]
  },
  "requested_calculations": [
    { "request_id": "CALC-001",
      "calculation_type": "margin",
      "input_metric_ids": ["MET-004", "MET-001"],
      "output_expectation": { "unit": "%", "currency": null, "period": "FY2025", "as_of_date": "2025-12-31" },
      "needed_for": "net-margin trend claim",
      "formula_hint": "net profit as a share of revenue (non-executable description)" }
  ],
  "insufficient": []
}
```

`requested_calculations` is the escape hatch: when an interpretation needs a number that does not
exist yet, request it from the deterministic calc service instead of computing it. The request is
structured, not free-form: `calculation_type` comes from the service's allowlisted enum
(growth_rate, cagr, margin, ratio, difference, share_of_total, per_share, other), the inputs are
existing `metric_id`s, and `output_expectation` states unit/currency/period/as_of_date so the
returned metric can be validated. **`formula_hint` is a human-readable note only — the service
selects its own implementation from `calculation_type` and must never parse or execute the hint.**

## Schema reference

**Output contract (machine-readable): `schemas/stage-envelopes.schema.json#/$defs/s3_output`** — bound to `task_name: financial_analysis` in `registry.json`.

`research-package.schema.json#/properties/claims`; referenced metrics must have
`computed_by: provider | deterministic_calc` per `#/properties/metrics`. Allowed claim types here:
fact and inference only — financial commentary phrased as opinion belongs in S4.

## Hard constraints

- **Zero arithmetic.** Every number in claim text is the verbatim value of a referenced metric.
  If two metrics imply a third (e.g. margin from profit and revenue), you may not state the third
  until it exists as a `deterministic_calc` metric — use `requested_calculations`.
- Trend words ("加速", "放缓", "improved") require the underlying period metrics to be referenced
  so the reader can verify the direction.
- Forecast-driver claims must reference the assumption metrics (`ASM-` rationale comes in S4;
  here reference the forecast metrics themselves).
- Restated/adjusted figures must say so when the metric carries `restated: true`.

## Missing-data behaviour

A statement you cannot make without a missing computation goes to `requested_calculations` (and
the stage re-runs when the metric appears) or to `insufficient`. Never approximate ("约", "roughly")
as a substitute for a real computed value.

## Hallucination and citation rules

- Numbers with no `metric_id` are fabrications regardless of plausibility.
- Causal language ("增长主要来自…") requires either a source stating the cause (fact) or an
  explicit inference chained to segment/driver metrics.
- Peer or industry benchmarks belong to S3d/S3b; do not import remembered benchmarks here.

## Positive example

```json
{ "claim_id": "CLM-040", "type": "fact",
  "text": { "zh_CN": "公司2025财年营业收入45.2亿元，同比增长20.2%，增速较2024财年有所提升。",
            "en_AU": "公司2025财年营业收入45.2亿元，同比增长20.2%，增速较2024财年有所提升。" },
  "source_ids": ["SRC-001"], "metric_ids": ["MET-001", "MET-003"],
  "confidence": 0.95, "review_status": "unreviewed" }
```

Both figures are verbatim metric values (MET-001 revenue, MET-003 the deterministic_calc growth
rate); the comparison word "提升" is verifiable from the referenced metrics.

## Negative example

```json
{ "claim_id": "CLM-042", "type": "inference",
  "text": { "zh_CN": "照此增速，2026财年收入将达到约54.3亿元。", "en_AU": "…" },
  "metric_ids": ["MET-001", "MET-003"], "confidence": 0.7, "review_status": "unreviewed" }
```

54.3亿 = 45.2亿 × 1.202 — the model performed the extrapolation. No metric holds 5430000000, so the
number is unbound. Correct behaviour: add `requested_calculations` entry for a FY2026 revenue
projection and claim nothing until it exists.

## Acceptance notes

Machine checks: claim types ∈ {fact, inference}; every numeric token in text matches a referenced
metric's value (after display-scale normalisation); all IDs resolve; `requested_calculations`
entries validate against `stage-envelopes.schema.json#/$defs/requestedCalculation` (allowlisted
type, resolvable input metric IDs, complete output expectation); no claim references a rejected
candidate.
