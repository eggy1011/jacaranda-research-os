---
prompt_id: social-card
version: 0.1.0
stage: S8
consumes: verified or approved research package
produces: social-card-series JSON (seven fixed-role knowledge cards)
---

# S8 — Social card plan

## Purpose and non-goals

Compile a verified or approved research package into a `social-card-series`: seven fixed-role
9:16 knowledge cards (`cover`, `full_year`, `driver_1`, `driver_2`, `profit_quality`,
`latest_quarter`, `counter_conclusion`) that a deterministic code renderer turns into
1080×1920 PNGs. The model selects which claims and metrics each card carries and writes short
Chinese copy; it does not write new analysis, invent numbers, choose styling (design tokens own
that), or render anything (the renderer's job). This stage is the only retryable model stage in
the v2 card flow and may use only free models; if none is available it stops at
`waiting_for_model` rather than falling back to a paid model.

## Required inputs

The full verified/approved package plus the series envelope:

```json
{
  "package": { "…full verified research package…": true },
  "series_id": "SCS-600XXX-2026-001",
  "locale": "zh-CN",
  "style_version": "jacaranda-brand-v1"
}
```

The model reads only long-form evidence already in the package (claims, metrics, sources,
valuation, catalysts, risks). It may not read or reconstruct whole-report prose. End-to-end
example of the expected output: `../research-schema/examples/example-social-card-series.zh-CN.json`.

## Required output

A complete document conforming to `../research-schema/social-card-series.schema.json`: exactly
seven cards, `card_no` 1..7 contiguous, roles in the canonical order above, each card carrying a
non-empty `source_ids` line, and `status` set to `planning` (the scheduler advances status). No
literal numerals in `hook`/`body`; numbers are declared in `inline_numbers` only.

## Schema reference

Output contract (machine-readable), one bound task in `registry.json`:
`task_name: social_card_plan` → `../research-schema/social-card-series.schema.json` (the whole
series document). `social-card-series.schema.json` is authoritative for structure; every number
appears **only** through a `displayNumber` in `inline_numbers` (`metric_id` + `display_transform`
+ `decimals`), and every reference (`claim_refs`, `metric_refs`, `source_ids`) must resolve
against the input package. The scheduler validates the assembled series against the schema and the
QC-01 binding rule before any card is rendered — assembly and rendering are code, not model calls.

## Hard constraints

- **Exactly seven cards in fixed roles**, one of each, in the canonical order — never add, drop,
  reorder or duplicate a role.
- **No unbound numbers**: any digit sequence in `hook` or `body` must be the rendered form of a
  metric declared in that card's `inline_numbers`, at the same value and displayed precision.
  Years, quarter labels and card numbers are exempt.
- **`latest_quarter`** must name an explicit interim period (e.g. `2026Q1`) and carry an
  `audit_note` stating the data is unaudited; it must never present an interim figure as a
  full-year result.
- **`counter_conclusion`** must carry a `caveat` and the full source union of the series, and must
  surface at least one genuine counterevidence claim — never a reassuring paraphrase.
- **`profit_quality`** figures that are `computed_by = deterministic_calc` are shown with the
  「计算值」 marker; the model never computes a value itself.
- `claim_type` on a card mirrors the dominant referenced claim's type exactly
  (`fact`/`inference`/`opinion`).
- Copy stays within the renderer's per-card character caps; compress by choosing fewer, stronger
  points — never by dropping hedges, sources or counterevidence.

## Missing-data behaviour

A card whose evidence is thin still renders: omit the optional figure rather than invent one, and
say what is not yet known (e.g. 「最新一期尚未披露」) instead of filling a placeholder. If a fixed
role has no supporting claim at all, the plan fails with the gap reported — the card set is never
padded with fabricated content, and a failed plan is retried, not silently emptied.

## Hallucination and citation rules

- Only IDs from the input package; the model adds no facts, no smoothing sentences and no
  transition text that carries content.
- A `hook` is a compression of the card's claims, not a new assertion (「营收首次微降」is fine when a
  claim says exactly that; 「即将反转」is a new claim and banned).
- Numbers are never re-scaled or re-rounded outside the declared `display_transform`/`decimals`.

## Positive example

`full_year` card from CLM-001 (营收 45.2亿元 / 净利 5.12亿元 / 同比 +20.2%):

```json
{
  "card_no": 2, "role": "full_year",
  "hook": "全年营收 45.2 亿、净利 5.12 亿",
  "body": "营收同比 +20.2%，仍在增长通道内，盈利同步兑现。",
  "claim_type": "fact", "claim_refs": ["CLM-001"],
  "metric_refs": ["MET-001", "MET-004", "MET-003"],
  "inline_numbers": [
    { "metric_id": "MET-001", "display_transform": "yi", "decimals": 1 },
    { "metric_id": "MET-004", "display_transform": "yi", "decimals": 2 },
    { "metric_id": "MET-003", "display_transform": "percent", "decimals": 1, "show_sign_colour": true }
  ],
  "source_ids": ["SRC-001"], "status": "planning"
}
```

Every digit in `hook`/`body` resolves to a bound metric at the stated precision.

## Negative example

```json
{
  "card_no": 6, "role": "latest_quarter",
  "hook": "全年营收 60 亿创新高",
  "body": "最新一期延续强势。",
  "claim_type": "fact", "metric_refs": [],
  "source_ids": ["SRC-001"], "status": "planning"
}
```

Four breaches: `60` is unbound (no such metric); an interim card presents a **full-year** figure;
no `audit_note` marks it unaudited; and 「创新高」is a new claim the package never makes. The
scheduler rejects the series and the plan is retried.

## Acceptance notes

Machine checks: series validates against `social-card-series.schema.json`; seven cards with
contiguous `card_no` and the exact role order; every reference resolves and none is duplicated;
every numeric token in `hook`/`body` matches a bound metric's displayed value (QC-01);
`latest_quarter` names a period and carries an `audit_note`; `counter_conclusion` carries a
`caveat` and the full source union. These mirror `check_card_series` in the validator.
