---
prompt_id: source-verification
version: 0.1.0
stage: S2
consumes: S1 candidates + source registry
produces: per-candidate verdicts
---

# S2 — Source verification

## Purpose and non-goals

Cross-check every S1 candidate against its cited source and the source registry, and issue a
verdict. Non-goals: fixing candidates (a wrong candidate is rejected, not repaired), fetching new
evidence, ranking importance, or producing claims.

## Required inputs

```json
{
  "as_of_date": "2026-07-10",
  "sources": [ { "source_id": "SRC-001", "type": "annual_report", "reliability_tier": "primary",
                 "published_date": "2026-04-20", "title": "...", "text_by_locator": { "p.102": "…" } } ],
  "candidates": { "candidate_metrics": [ … ], "candidate_claims": [ … ] }
}
```

## Required output

```json
{
  "verdicts": [
    {
      "candidate_id": "CMET-001",
      "verdict": "verified",
      "checks": {
        "quote_found": true,
        "value_matches_quote": true,
        "source_tier_sufficient": true,
        "date_fresh": true,
        "entity_known": true
      },
      "reasons": []
    },
    {
      "candidate_id": "CCLM-004",
      "verdict": "rejected",
      "checks": { "quote_found": true, "value_matches_quote": false,
                  "source_tier_sufficient": true, "date_fresh": true, "entity_known": true },
      "reasons": ["candidate states 21.2% but the quoted sentence says 20.2%"]
    }
  ],
  "unverifiable_entities": ["names mentioned in candidates but absent from all sources"]
}
```

Allowed verdicts: `verified`, `rejected`, `needs_review` (use `needs_review` only for genuine
ambiguity — e.g. two primary sources conflict — never as a soft pass).

## Schema reference

Verdicts feed `claims[].review_status` and metric acceptance in
`packages/research-schema/research-package.schema.json`. Tier rules follow
`#/properties/sources` (`reliability_tier`): facts need `primary` or `secondary`; `caution`
sources alone cannot verify a fact.

## Hard constraints

- Verify against the provided source text only; your own knowledge of the real world is not a
  source and must not influence verdicts.
- A numeric mismatch of any size between candidate `value` and the quote is a rejection (after
  honouring the documented `unit_conversion_note`).
- Freshness: price/market data older than 5 trading days relative to `as_of_date`, or financials
  superseded by a newer filing in the registry, fail `date_fresh`.
- Every rejection and every `needs_review` must carry at least one machine-readable reason.

## Missing-data behaviour

A candidate citing a source or locator absent from the registry is `rejected` with reason
`unknown source`, not `needs_review`. Missing chunks are never assumed to contain the value.

## Hallucination and citation rules

- Never mark `verified` on trust: `quote_found` must be literally true against `text_by_locator`.
- Entities in `unverifiable_entities` must block any downstream fact that depends on them.
- Do not invent reasons; each reason must reference the concrete check that failed.

## Positive example

Candidate CMET-002 (20.2%, quote "较上年同期的37.60亿元增长20.2%") against SRC-001 p.102 text
containing that sentence, published 2026-04-20, tier primary, as_of 2026-07-10:

```json
{ "candidate_id": "CMET-002", "verdict": "verified",
  "checks": { "quote_found": true, "value_matches_quote": true, "source_tier_sufficient": true,
              "date_fresh": true, "entity_known": true }, "reasons": [] }
```

## Negative example

```json
{ "candidate_id": "CMET-005", "verdict": "verified",
  "checks": { "quote_found": false, "value_matches_quote": true, "source_tier_sufficient": true,
              "date_fresh": true, "entity_known": true },
  "reasons": ["value is plausible for a company of this size"] }
```

Invalid twice over: a `verified` verdict with `quote_found: false` is internally contradictory, and
"plausible" is model world-knowledge substituting for evidence — the exact failure S2 exists to
catch. The validator rejects any `verified` verdict whose checks are not all true.

## Acceptance notes

Machine checks: every candidate has exactly one verdict; verdict enum valid; `verified` ⇒ all five
checks true; `rejected`/`needs_review` ⇒ ≥1 reason; no verdict references an unknown candidate_id;
facts relying on `caution`-tier sources are not `verified`.
