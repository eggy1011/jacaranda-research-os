---
prompt_id: competition
version: 0.1.0
stage: S3d
consumes: verified metrics and fact claims (incl. competitor evidence)
produces: claims for competition_moat plus comparison entities
---

# S3d — Competition and moat

## Purpose and non-goals

Characterise the competitive landscape and the durability of the company's advantages for the
`competition_moat` section, and structure the 2–4 entities the L06 comparison layout renders.
Non-goals: industry chain structure (S3b), picking a winner (S4's rating), any peer financial
figure not present in verified evidence.

## Required inputs

Same envelope as S3a. Competitor evidence arrives as ordinary verified metrics/claims tagged to
competitor entities that appear in the sources.

## Required output

```json
{
  "claims": [ … ],
  "section_assignment": { "competition_moat": ["CLM-050", "CLM-051"] },
  "comparison_entities": [
    { "entity_authored": "公司", "metric_ids": ["MET-001"], "claim_ids": ["CLM-050"], "limited_data": false },
    { "entity_authored": "竞争对手A（虚构）", "metric_ids": [], "claim_ids": ["CLM-051"], "limited_data": true }
  ],
  "moat_assessment": { "claim_id": "CLM-052", "durability": "moderate" },
  "insufficient": []
}
```

## Schema reference

**Output contract (machine-readable): `schemas/stage-envelopes.schema.json#/$defs/s3d_output`** — bound to `task_name: competition` in `registry.json`.

Claims per `research-package.schema.json#/properties/claims`. Entities feed
`slide-deck.schema.json` `comparison_cards` (2–4 cards, `limited_data` flag). `durability` ∈
{weak, moderate, strong} and must be carried by an `opinion` claim with a support chain.

## Hard constraints

- Competitors may only be named if a source names them as competitors. Entity count rule, in
  precedence order: (1) if the evidence names no competitive set, output exactly 1 entity (the
  company) and record the gap in `insufficient` — the schema rejects a single-entity output with
  an empty `insufficient`; (2) otherwise output 2–4 entities including the company. Never pad to
  reach 2.
- **Ordering convention: `comparison_entities[0]` is always the covered company** — schedulers and
  renderers rely on this position; the schema documents it and reviewers enforce it.
- An entity with no sourced metrics keeps `metric_ids: []` and `limited_data: true` — qualitative
  bullets only.
- Moat conclusions are `opinion` claims chained to the facts/inferences that support them.
- Share/size comparisons require metrics for **both** sides; one-sided comparisons are banned.

## Missing-data behaviour

The competitive set being unknown is a valid, reportable state: emit the company as the sole
entity, `insufficient: ["competitive set not evidenced"]`, and let human review decide whether to
gather more evidence. Never populate cards with remembered real-world competitors.

## Hallucination and citation rules

- Peer financials from model memory are the highest-risk fabrication in this stage; every peer
  number needs its own extraction → verification trail.
- "市场份额第一/leading market share" requires a cited ranking source, else it is at most an
  opinion and must read as one.
- Moat labels (network effects, switching costs…) must tie to specific evidenced behaviour, not
  category boilerplate.

## Positive example

```json
{ "claim_id": "CLM-051", "type": "inference",
  "text": { "zh_CN": "行业内同类厂商产能扩张较快，若价格竞争加剧，公司毛利率可能承压。",
            "en_AU": "行业内同类厂商产能扩张较快，若价格竞争加剧，公司毛利率可能承压。" },
  "source_ids": ["SRC-004"], "confidence": 0.65, "review_status": "unreviewed" }
```

Competitive pressure grounded in the cited industry report, stated conditionally, typed inference.

## Negative example

```json
{ "entity_authored": "竞争对手A（虚构）", 
  "metric_ids": ["MET-098"], "claim_ids": ["CLM-053"], "limited_data": false }
```

with claim text 「竞争对手A收入约30亿元，市占率约15%」 — MET-098 does not exist in the input
(dangling reference) and no source states either figure. Correct form: `metric_ids: []`,
`limited_data: true`, and only source-supported qualitative bullets.

## Acceptance notes

Machine checks: entity count is 1 (with a competitive-set gap recorded in `insufficient`) or 2–4,
always including the company; entity with empty `metric_ids` ⇒ `limited_data: true`; all IDs
resolve; if `moat_assessment` is present its durability enum is valid and its claim is type
`opinion` with a chain (omit `moat_assessment` when evidence cannot support an opinion); no
numeric token in claim text without a matching referenced metric.
