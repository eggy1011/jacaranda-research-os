---
prompt_id: company-analysis
version: 0.1.0
stage: S3a
consumes: verified metrics and fact claims
produces: claims for company_snapshot and business_model_segments
---

# S3a — Company analysis

## Purpose and non-goals

Produce the claims that describe what the company is, how it makes money, and how its segments
behave, for the `company_snapshot` and `business_model_segments` sections. Non-goals: industry
structure (S3b), financial trend interpretation (S3c), competitive positioning (S3d), valuation
views (S4), translation (S6).

## Required inputs

```json
{
  "company": { …research-package company object… },
  "verified_metrics": [ …metrics with final MET- ids… ],
  "verified_fact_claims": [ …claims with final CLM- ids, type=fact… ],
  "next_claim_id": "CLM-020"
}
```

## Required output

```json
{
  "claims": [ …objects conforming to research-package claims[], ids allocated from next_claim_id… ],
  "section_assignment": {
    "company_snapshot": ["CLM-020", "CLM-021"],
    "business_model_segments": ["CLM-022"]
  },
  "insufficient": ["segment gross margins: 资料不足 / insufficient information"]
}
```

## Schema reference

**Output contract (machine-readable): `schemas/stage-envelopes.schema.json#/$defs/s3_output`** — bound to `task_name: company_analysis` in `registry.json`.

`packages/research-schema/research-package.schema.json#/properties/claims` — including the
conditional requirements: fact ⇒ `source_ids` non-empty; inference ⇒ ≥1 of `source_ids`,
`metric_ids`, `based_on_claim_ids`. Analysis stages author in one language (the evidence's
dominant language). Because `localizedText` requires both keys, write the authored text into both
`zh_CN` and `en_AU`; S6 (translation) replaces the non-authored side. The assembler tracks which
side is authoritative per package.

## Hard constraints

- Allowed claim types: fact (restating verified facts with citation), inference, opinion.
- Every number in claim text must come from a referenced `metric_id` and match its value/unit.
- One claim = one assertion. Compound sentences that bundle a fact and a judgement must be split.
- Segment descriptions may only name segments that appear in verified evidence.
- Confidence: facts ≥0.9; inferences ≤0.8; opinions ≤0.7.

## Missing-data behaviour

Standard wording inside claim text is 资料不足 / "insufficient information". Topics you cannot
support go in `insufficient`, not into hedged filler claims ("the company likely has various
segments" is a contract breach, not caution).

## Hallucination and citation rules

- Only `MET-`/`CLM-`/`SRC-` IDs present in the input may be referenced.
- Founding dates, executive names, product launches: only if present in verified evidence.
- An inference's support chain must actually support it — citing an unrelated claim to satisfy the
  schema is a fabrication of the chain and fails human QA even when machine checks pass.

## Positive example

```json
{ "claim_id": "CLM-020", "type": "inference",
  "text": { "zh_CN": "公司收入以自动化设备销售为主，客户集中度较高（前五大客户占比约42%），大客户订单波动会直接影响收入节奏。",
            "en_AU": "公司收入以自动化设备销售为主，客户集中度较高（前五大客户占比约42%），大客户订单波动会直接影响收入节奏。" },
  "source_ids": ["SRC-001"], "based_on_claim_ids": ["CLM-008"],
  "confidence": 0.7, "review_status": "unreviewed" }
```

Builds on verified fact CLM-008 (42% concentration), draws a bounded operational implication, and
is typed `inference` with an explicit chain. Both language keys carry the authored language; S6
translates the `en_AU` side.

## Negative example

```json
{ "claim_id": "CLM-021", "type": "fact",
  "text": { "zh_CN": "公司是国内领先的智能制造企业，管理层执行力突出。",
            "en_AU": "…" },
  "source_ids": [], "confidence": 0.95, "review_status": "unreviewed" }
```

Three violations: `fact` with empty `source_ids` (schema-invalid); "领先/执行力突出" are judgements
dressed as facts (must be `opinion` with support); superlatives without a cited basis are the
signature hallucination this pipeline bans.

## Acceptance notes

Machine checks: claims validate against the schema including conditionals; all referenced IDs
resolve; claim IDs allocated sequentially from `next_claim_id` without collisions; every claim
assigned to exactly one of the two sections; numbers in text match referenced metric values;
confidence bands respected.
