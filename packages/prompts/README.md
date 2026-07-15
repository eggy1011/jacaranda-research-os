# prompts

Placeholder — prompt files are the next Claude Code task (Task Board #4), to begin after the Phase 0 schemas are confirmed.

Planned catalogue (one file per task, versioned, each with ≥1 positive and ≥1 negative example):

| File (planned) | Task |
|---|---|
| `extraction.md` | Evidence extraction from parsed filings/uploads into candidate metrics + facts |
| `source-verification.md` | Source/claim cross-checking; flags unverifiable entities and stale dates |
| `company-analysis.md` | Company overview and business model claims |
| `industry-analysis.md` | Industry and value-chain claims |
| `financial-analysis.md` | Interpretation (not computation) of provider metrics |
| `competition.md` | Competitive landscape and moat |
| `valuation-narrative.md` | Assumption rationales and scenario narratives around code-computed values |
| `catalysts-risks.md` | Catalysts and risks with severity/likelihood |
| `translation.md` | zh↔en conversion preserving values, units, source IDs and conclusion strength |
| `slide-compression.md` | Research package → slide-deck JSON within layout limits |
| `glossary.md` | Approved zh/en financial terminology mapping |

Shared rules that will apply to every prompt: output must validate against the relevant schema in `packages/research-schema/`; no invented numbers, entities or citations; missing data is declared missing; all key statements carry `source_ids`/`metric_ids`; fact/inference/opinion labelling is mandatory.
