---
prompt_id: slide-compression
version: 0.1.0
stage: S7
consumes: validated research package
produces: slide-deck JSON per edition
---

# S7 — Slide compression

## Purpose and non-goals

Compile a validated research package into a slide-deck specification for one edition (`zh-CN`,
`en-AU`, or `bilingual-summary`), selecting layouts, distributing claims into blocks, and binding
every number to a metric reference. Non-goals: writing new analysis, restyling (tokens own all
styling), rendering (the renderer's job), exceeding layout limits and hoping the renderer shrinks
text (it will reject instead).

## Required inputs

```json
{
  "edition": "zh-CN",
  "package": { …full validated research package… },
  "layout_limits": "packages/presentation/layouts.md (L01–L11 caps, per-language)",
  "deck_id": "DCK-…"
}
```

## Required output

A complete document conforming to `packages/research-schema/slide-deck.schema.json`: 12–18 slides
(≤6 for bilingual-summary), section order per the 12-section structure, every block carrying
`priority`, every footer carrying `data_as_of` and consolidated `source_ids`.

## Schema reference

`slide-deck.schema.json` is authoritative for structure; `layouts.md` for the section→layout
mapping, per-language character/word caps, and overflow policy. Numbers appear **only** through
`displayNumber` objects (`metric_id` + `display_transform` + `decimals`) — in `kpi_cards`,
`chart.series`, `table.rows`, `football_field`, or `inline_numbers` alongside narrative text.

## Hard constraints

- **No unbound numbers**: any digit sequence in a narrative field (`bullets[].text`,
  `text_panel.text`, `assumption_lines[].text`, card descriptions) must be the rendered form of a
  metric bound in that block's `inline_numbers`/`refs` — same value, same displayed precision.
  Years, quarter labels and section numbers are exempt.
- Text length within the per-language caps of the target layout; compress by selecting fewer,
  stronger claims — never by stripping hedges, sources or counterevidence.
- The thesis slide must include the counterevidence bullet; the risks slide keeps ≥3 risks; L11
  (conclusion/sources/disclaimer) is never dropped or truncated of its source table.
- `claim_type` tags on bullets mirror the underlying claim's type exactly.
- Every slide's footer `source_ids` is the union of sources referenced by its blocks.
- bilingual-summary blocks stack zh above en for the same content; both from the same claims.

## Missing-data behaviour

A slide whose mandatory data is missing (e.g. L09 with <2 valuation methods) falls back per
layouts.md (single-method L04) or is omitted with the gap reported — never populated with
placeholder bars. `null` table cells stay `null` (renderer prints 暂无数据/N/A).

## Hallucination and citation rules

- Only IDs from the input package; the compiler adds no facts, no smoothing sentences, no
  transition text carrying content.
- Chart `x_labels` and series must correspond one-to-one with the referenced metrics' periods;
  no interpolated points.
- Titles are compressions of section claims, not new assertions ("收入保持双位数增长" is fine when
  a claim says exactly that; "收入即将爆发" is a new claim and banned).

## Positive example

From CLM-001 (45.2亿元, +20.2%, refs MET-001/MET-003), zh-CN edition, L04 bullet:

```json
{ "text": "2025财年营业收入45.2亿元，同比增长20.2%。",
  "refs": [{ "claim_id": "CLM-001" }],
  "claim_type": "fact",
  "inline_numbers": [
    { "metric_id": "MET-001", "display_transform": "yi", "decimals": 1 },
    { "metric_id": "MET-003", "display_transform": "raw", "decimals": 1 }
  ] }
```

Every digit in the text resolves to a bound metric at the stated precision.

## Negative example

```json
{ "text": "公司收入45.2亿元，净利率约11.3%，明显优于同行平均8%。",
  "refs": [{ "claim_id": "CLM-001" }],
  "claim_type": "fact",
  "inline_numbers": [ { "metric_id": "MET-001", "display_transform": "yi", "decimals": 1 } ] }
```

Three unbound numbers: 11.3% (no metric exists), 8% (invented peer average), and the comparison
"明显优于同行" (a new claim the referenced CLM-001 never makes). The QC-01 validator flags every
digit token without a matching bound metric; this block fails.

## Acceptance notes

Machine checks: full deck validates against `slide-deck.schema.json`; slide count in range;
section coverage complete (all 12 present, L11 last); every numeric token in narrative fields
matches a bound metric's displayed value; per-language caps respected; footer source unions
correct; counterevidence present on thesis slide; risks ≥3 on the risks slide.
