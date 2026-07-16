# prompts — research prompt catalogue v0.1.0

Versioned, schema-grounded prompt contracts that turn parsed evidence into verifiable bilingual
research packages and slide-deck specifications. Prompts are contracts, not free-form instructions:
every stage declares its structured input, its structured output, and the validator assertions that
gate progression to the next stage. All numeric computation happens in code; the model extracts,
classifies, explains and compresses — it never does arithmetic.

## Pipeline order and dependencies

```text
parsed evidence chunks (DocumentProvider / market-data provider)
  │
  ▼
 S1 extraction.md                 candidate metrics + candidate fact claims
  │
  ▼
 S2 source-verification.md        verified / rejected / needs_review verdicts
  │
  ├──────────────┬───────────────┬───────────────┐
  ▼              ▼               ▼               ▼
 S3a company-    S3b industry-   S3c financial-  S3d competition.md
     analysis.md     analysis.md     analysis.md     (parallel, independent)
  │
  ▼  (plus code-computed valuation metrics & assumptions from the deterministic calc service)
 S4 valuation-narrative.md        assumption rationales, scenarios, rating, counterevidence
  │
  ▼
 S5 catalysts-risks.md            catalysts[] and risks[] with linked claims
  │
  ▼
 S6 translation.md  (uses glossary.md)   completes every localizedText pair
  │
  ▼
 [code] package assembly + validation    → research-package.schema.json
  │
  ▼
 S7 slide-compression.md           one deck per edition
  │
  ▼
 [code] deck validation + rendering      → slide-deck.schema.json → renderer
```

`glossary.md` is a reference document consumed by S6 and S7, not an executable stage.

## Stage table

| Stage | Prompt | Consumes | Produces | Claim types allowed |
|---|---|---|---|---|
| S1 | `extraction.md` | evidence chunks | candidate metrics, candidate fact claims | fact (candidate) |
| S2 | `source-verification.md` | S1 output + source registry | verdicts per candidate | none (verdicts only) |
| S3a | `company-analysis.md` | verified S2 output | claims for company_snapshot, business_model_segments | fact, inference, opinion |
| S3b | `industry-analysis.md` | verified S2 output | claims for industry_value_chain + value-chain nodes | fact, inference, opinion |
| S3c | `financial-analysis.md` | verified metrics (incl. deterministic_calc) | claims for historical_financials, forecast_drivers | fact, inference |
| S3d | `competition.md` | verified S2 output | claims for competition_moat + comparison entities | fact, inference, opinion |
| S4 | `valuation-narrative.md` | code-computed valuation metrics + assumptions | rationale/scenario claims, rating, counterevidence | inference, opinion |
| S5 | `catalysts-risks.md` | all prior claims | catalysts[], risks[] | inference, opinion (facts by reference) |
| S6 | `translation.md` | assembled package, one language filled | both `zh_CN` and `en_AU` sides | none (no new claims) |
| S7 | `slide-compression.md` | validated research package | slide-deck JSON per edition | none (no new claims) |

## Versioning

- Each prompt file carries frontmatter `prompt_id` and semver `version`.
- The catalogue version (this README) bumps when the pipeline shape changes.
- `generation_metadata.prompt_versions` in every research package records the exact versions used.
- Breaking output-shape changes require a schema Issue first; prompts never redefine schema fields.

## Failure and missing-data behaviour

- **Missing evidence is declared, never filled.** The standard forms are `资料不足` /
  "insufficient information", or `null` cells where the schema allows them. A stage that fabricates
  a value to complete its output has failed, even if the JSON validates.
- **Retryable errors** (LLMProvider re-runs the stage with the validator's error paths appended):
  invalid JSON, JSON Schema validation failure, dangling `MET-/CLM-/SRC-/ASM-` references,
  over-limit text lengths, missing mandatory sections of the output.
- **Non-retryable errors** (halt the stage, surface to human review): insufficient evidence for a
  mandatory element (e.g. fewer than 3 supportable risks), contradictory sources that verification
  cannot resolve, and any hallucination-rule breach detected twice consecutively — retrying a
  fabrication invites a different fabrication.
- Stages are checkpointed: a failed stage re-runs alone; upstream verified output is never mutated
  by a downstream retry.

## Hard rules inherited by every prompt

1. Output must validate against the referenced schema (`packages/research-schema/`).
2. Only IDs present in the stage input may be referenced; inventing IDs, numbers, entities,
   events, citations or locators is a contract breach.
3. Facts require ≥1 valid `source_id` of tier `primary` or `secondary`; inferences require a
   resolvable support chain (`source_ids`, `metric_ids` or `based_on_claim_ids`); everything
   unsupported is at most an `opinion` and must be worded as one.
4. No arithmetic: growth rates, ratios, valuations and ranges come from the deterministic calc
   service as metrics with `computed_by: deterministic_calc`.
5. A-share and US market-specific fields stay under `company.market_specific.cn|us`; prompts must
   not blend the two conventions.
6. Mock/demo runs use fictional companies only (`company.is_mock: true`).

## Validation

```bash
python3 -m pip install jsonschema
python3 packages/prompts/tests/validate.py
```

The validator checks: catalogue completeness (11 files, consistent section contract), fixture JSON
against both schemas, cross-stage reference resolution, bilingual numeric/ID consistency (QC-03
prototype), and the no-unbound-numbers rule for slide narrative fields (QC-01 prototype). See
`tests/validate.py` for the exact assertions; end-to-end fixtures live in `examples/`.
