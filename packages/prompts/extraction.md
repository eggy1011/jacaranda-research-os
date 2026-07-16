---
prompt_id: extraction
version: 0.1.0
stage: S1
consumes: parsed evidence chunks
produces: candidate metrics and candidate fact claims
---

# S1 — Evidence extraction

## Purpose and non-goals

Extract every research-relevant numeric datum and directly stated fact from parsed evidence chunks
into structured candidates for verification. Non-goals: judging importance, computing derived
values (growth, ratios), verifying correctness (S2's job), writing narrative, or translating.

## Required inputs

```json
{
  "company_context": { "name": "...", "ticker": "...", "market": "CN-A|US" },
  "evidence_chunks": [
    {
      "source_id": "SRC-001",
      "type": "annual_report",
      "locator": "p.102, consolidated income statement",
      "published_date": "2026-04-20",
      "retrieved_at": "2026-07-10T09:00:00+08:00",
      "url_or_document": "upload://...",
      "language": "zh",
      "text": "…verbatim parsed content…"
    }
  ]
}
```

## Required output

```json
{
  "candidate_metrics": [
    {
      "candidate_id": "CMET-001",
      "name_verbatim": "营业收入",
      "value": 4520000000,
      "unit": "CNY",
      "currency": "CNY",
      "period": "FY2025",
      "as_of_date": "2025-12-31",
      "source_id": "SRC-001",
      "source_url_or_document": "upload://...#p102",
      "retrieved_at": "2026-07-10T09:00:00+08:00",
      "quote": "exact sentence or table cell the value came from",
      "unit_conversion_note": "source said 45.20亿元; canonical value stored in CNY"
    }
  ],
  "candidate_claims": [
    {
      "candidate_id": "CCLM-001",
      "type": "fact",
      "text_original_language": "…",
      "source_ids": ["SRC-001"],
      "quote": "exact supporting sentence"
    }
  ],
  "extraction_gaps": ["net profit by segment not present in provided chunks"]
}
```

Candidate IDs (`CMET-/CCLM-`) are temporary; the assembler assigns final `MET-/CLM-` IDs after S2.

## Schema reference

**Output contract (machine-readable): `schemas/stage-envelopes.schema.json#/$defs/s1_output`** — bound to `task_name: extraction` in `registry.json`.

Field semantics follow `packages/research-schema/research-package.schema.json#/properties/metrics`
(the 8 provenance fields) and `#/properties/claims`. Candidates add `quote` and `candidate_id`.

## Hard constraints

- Every candidate metric carries all 8 provenance fields plus a verbatim `quote`.
- `value` is the canonical raw number: 45.2亿元 → `4520000000` with `unit: "CNY"`, and the
  conversion recorded in `unit_conversion_note`. Scale words (万/亿/million/billion) are the ONLY
  arithmetic-adjacent transformation permitted, and it must be documented in the note.
- No derived values: do not extract "growth of 20.2%" as a metric unless the source states 20.2%
  verbatim — in that case extract it with its quote; never compute it yourself.
- Only `fact` candidates. Anything requiring interpretation is out of scope for S1.
- `source_id` must be one of the input chunks' IDs; `quote` must appear verbatim in that chunk.

## Missing-data behaviour

Values you expected but did not find go in `extraction_gaps` as plain statements. Never emit a
candidate with a guessed value, an averaged value, or a value from memory of the real world.

## Hallucination and citation rules

- The `quote` field is the anti-hallucination anchor: a candidate whose quote does not appear in
  the cited chunk is rejected by the validator and counts as a fabrication.
- Entities (subsidiaries, products, people) may only appear in candidates if named in a chunk.
- Do not "helpfully" complete partial numbers, dates or names.

## Positive example

Input chunk (SRC-001, annual report p.102): 「公司2025年度实现营业收入45.20亿元，较上年同期的
37.60亿元增长20.2%。」

```json
{
  "candidate_metrics": [
    { "candidate_id": "CMET-001", "name_verbatim": "营业收入（2025年度）", "value": 4520000000,
      "unit": "CNY", "currency": "CNY", "period": "FY2025", "as_of_date": "2025-12-31",
      "source_id": "SRC-001", "source_url_or_document": "upload://mock-annual-report-2025.pdf#p102",
      "retrieved_at": "2026-07-10T09:00:00+08:00",
      "quote": "公司2025年度实现营业收入45.20亿元",
      "unit_conversion_note": "45.20亿元 → 4520000000 CNY" },
    { "candidate_id": "CMET-002", "name_verbatim": "营业收入同比增速", "value": 20.2,
      "unit": "%", "currency": null, "period": "FY2025", "as_of_date": "2025-12-31",
      "source_id": "SRC-001", "source_url_or_document": "upload://mock-annual-report-2025.pdf#p102",
      "retrieved_at": "2026-07-10T09:00:00+08:00",
      "quote": "较上年同期的37.60亿元增长20.2%",
      "unit_conversion_note": "percentage stated verbatim in source, not computed" }
  ],
  "candidate_claims": [],
  "extraction_gaps": []
}
```

The 20.2% is extractable because the source states it; the extractor did not compute it.

## Negative example

```json
{
  "candidate_metrics": [
    { "candidate_id": "CMET-003", "name_verbatim": "净利率", "value": 11.3,
      "unit": "%", "currency": null, "period": "FY2025", "as_of_date": "2025-12-31",
      "source_id": "SRC-001", "source_url_or_document": "upload://mock-annual-report-2025.pdf#p102",
      "retrieved_at": "2026-07-10T09:00:00+08:00",
      "quote": "公司2025年度实现营业收入45.20亿元",
      "unit_conversion_note": "computed from net profit 5.12亿 / revenue 45.2亿" }
  ]
}
```

Rejected for two violations: the value was **computed** by the model (净利率 appears nowhere in the
source), and the `quote` does not contain the extracted value. Ratio metrics are produced by the
deterministic calc service, never by extraction.

## Acceptance notes

Machine checks: all 8 provenance fields present; `source_id` ∈ input chunk IDs; `quote` is a
substring of the cited chunk's `text`; `type` == "fact" for all candidate claims; `value` numeric;
`currency` null only when `unit` ∈ {%, x, shares, counts}; no candidate duplicates an existing ID.
