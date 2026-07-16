---
prompt_id: industry-analysis
version: 0.1.0
stage: S3b
consumes: verified metrics and fact claims
produces: claims for industry_value_chain plus value-chain node structure
---

# S3b — Industry and value-chain analysis

## Purpose and non-goals

Describe the industry the company operates in — upstream/midstream/downstream structure, demand
drivers, and (for A-shares) policy context — for the `industry_value_chain` section, plus the node
structure the L07 layout renders. Non-goals: company internals (S3a), peer-by-peer comparison
(S3d), market-size forecasting beyond cited sources.

## Required inputs

Same envelope as S3a (`company`, `verified_metrics`, `verified_fact_claims`, `next_claim_id`),
where evidence includes industry/policy sources.

## Required output

```json
{
  "claims": [ … ],
  "section_assignment": { "industry_value_chain": ["CLM-030", "CLM-031"] },
  "value_chain_nodes": [
    { "position": "upstream", "name_authored": "核心零部件", "claim_id": "CLM-030", "metric_id": null },
    { "position": "midstream", "name_authored": "自动化设备制造（公司所处）", "claim_id": "CLM-031", "metric_id": null, "highlight": true },
    { "position": "downstream", "name_authored": "下游制造业客户", "claim_id": "CLM-032", "metric_id": "MET-011" }
  ],
  "market_specific_claims": { "cn_policy_context": ["CLM-033"], "us_filing_context": [] },
  "insufficient": []
}
```

## Schema reference

**Output contract (machine-readable): `schemas/stage-envelopes.schema.json#/$defs/s3_output`** — bound to `task_name: industry_analysis` in `registry.json`.

Claims per `research-package.schema.json#/properties/claims`. `cn_policy_context` IDs feed
`company.market_specific.cn.policy_context_claim_ids`. Nodes feed the `flow` block of
`slide-deck.schema.json` (3–6 nodes, one `highlight` for the company's position).

## Hard constraints

- 3–6 value-chain nodes; exactly one node highlighted as the company's position.
- Market-size or growth numbers only via referenced `metric_id` (extracted or code-computed).
- CN packages: policy claims must cite regulator/announcement sources (tier primary) and go into
  `cn_policy_context`. US packages: industry context from filings/earnings materials goes into
  `us_filing_context`. Never mix conventions in one package.
- Nodes without supportable descriptions carry `claim_id: null` and render structure-only.

## Missing-data behaviour

An industry chain you cannot evidence beyond the company's own position is reported as nodes with
`claim_id: null` plus an `insufficient` entry — not filled with textbook industry knowledge.

## Hallucination and citation rules

- Industry statistics from model memory are fabrications even when directionally correct.
- Policy documents may only be characterised by what the cited chunk actually says; extrapolating
  a policy's effects is an `inference` chained to the policy fact, never part of the fact.
- Named upstream/downstream players require a source naming them in that role.

## Positive example

```json
{ "claim_id": "CLM-033", "type": "inference",
  "text": { "zh_CN": "产业指导意见提出支持智能制造装备国产替代，若落地执行，将改善公司所处中游环节的订单环境。",
            "en_AU": "产业指导意见提出支持智能制造装备国产替代，若落地执行，将改善公司所处中游环节的订单环境。" },
  "source_ids": ["SRC-003"], "based_on_claim_ids": ["CLM-002"],
  "confidence": 0.65, "review_status": "unreviewed" }
```

Policy effect stated conditionally ("若落地执行"), typed inference, chained to the verified policy
fact CLM-002 and its primary source.

## Negative example

```json
{ "claim_id": "CLM-034", "type": "fact",
  "text": { "zh_CN": "中国工业自动化市场规模约3,000亿元，年增速约12%。", "en_AU": "…" },
  "source_ids": ["SRC-003"], "confidence": 0.9, "review_status": "unreviewed" }
```

SRC-003 is a policy document that contains no market-size figure: the numbers come from model
memory, the citation is decorative, and neither value has a `metric_id`. This is the
plausible-but-uncited statistic — the most common industry-analysis hallucination.

## Acceptance notes

Machine checks: schema-valid claims; node count 3–6 with exactly one highlight; every non-null node
`claim_id`/`metric_id` resolves; cn/us market-specific arrays not both populated; numbers in text
backed by referenced metrics; policy claims cite primary-tier sources.
