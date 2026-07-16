---
prompt_id: translation
version: 0.1.0
stage: S6
consumes: assembled package with one authoritative language per localizedText
produces: completed zh_CN and en_AU pairs
---

# S6 — Bilingual translation

## Purpose and non-goals

Complete every `localizedText` pair in the package so the zh-CN and en-AU editions read natively
while remaining *the same research*. Non-goals: editing content, improving arguments, adding or
dropping hedges, re-deriving numbers, renaming IDs, summarising.

## Required inputs

```json
{
  "authoritative_language": "zh_CN",
  "glossary": "packages/prompts/glossary.md",
  "texts": [
    { "path": "claims[3].text", "zh_CN": "…authored…", "en_AU": "…placeholder copy of zh…" }
  ]
}
```

## Required output

The same `texts` array with the non-authoritative side replaced by the translation. No other field
of the package is touched.

## Schema reference

`research-package.schema.json#/$defs/localizedText` (both keys required, minLength 1). Terminology
authority: `glossary.md` — rating scale, financial statement terms, valuation terms, unit display
conventions, date formats, en-AU spellings.

## Hard constraints

- Preserve exactly: every numeric value, unit, currency, period, percentage, date, and every
  `MET-/CLM-/SRC-/ASM-/RSK-/CAT-` ID that appears in text.
- Preserve conclusion strength: 增持 ↦ Accumulate (never Buy); "可能/或将" ↦ "may/could" (never
  "will"); hedges and conditionals survive translation unchanged in force.
- Scale conversions follow the glossary display rules (45.2亿元 ↦ CNY 4.52 billion) — a display
  transformation of the same stored value, with the arithmetic already defined by the glossary
  table, never ad-hoc rounding beyond it.
- en_AU uses Australian spelling (capitalise, analyse, labour); zh uses full-width punctuation and
  the date/number conventions in the glossary.
- Claim classification words must keep their register: 反方证据 ↦ "counterevidence", 资料不足 ↦
  "insufficient information" (fixed vocabulary, not paraphrase).

## Missing-data behaviour

A text you cannot translate faithfully (ambiguous antecedent, untranslatable citation fragment)
is returned unchanged with a `translation_flags` entry naming the path and the problem — human
review resolves it. Never guess an interpretation to complete the batch.

## Hallucination and citation rules

- Translation adds zero information: no explanatory glosses, no "(a major Chinese holiday)"-style
  insertions, no unit clarifications beyond the glossary mapping.
- IDs are opaque tokens: never localise, renumber or expand them.
- If source text contains an error, translate the error and flag it — do not silently fix.

## Positive example

zh_CN (authoritative): 「公司2025财年营业收入45.2亿元，同比增长20.2%。」
→ en_AU: "The company reported FY2025 revenue of CNY 4.52 billion, up 20.2% year on year."

Same value via glossary scale mapping (亿 → billion table), same period, same growth figure, same
factual register.

## Negative example

zh_CN: 「我们认为公司是国产替代的主要受益者之一，给予"增持"评级。」
→ en_AU: "We are confident the company will be the biggest winner of domestic substitution and
rate it a Buy."

Four breaches: 认为→"are confident" (strengthened), 主要受益者之一→"the biggest winner" (superlative
added, "one of" dropped), 增持→"Buy" (rating upgraded across the glossary mapping), 将/"will"
(hedge removed). Every one of these changes the investment meaning — the consistency checker
(QC-03) and glossary audit reject this output.

## Acceptance notes

Machine checks: numeric token sets match across languages after glossary scale normalisation;
ID tokens identical on both sides; rating/severity terms map exactly per glossary; both keys
non-empty for every path; flagged paths listed when unchanged.
