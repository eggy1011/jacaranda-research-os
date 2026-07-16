---
prompt_id: glossary
version: 0.1.0
stage: reference
consumes: n/a
produces: n/a (terminology authority for S6 and S7)
---

# Glossary — approved zh/en terminology and formatting

## Purpose and non-goals

The single terminology authority for translation (S6) and slide compression (S7). If a mapping is
missing here, the correct behaviour is to flag it, not to improvise one. Non-goals: style guidance
beyond terminology (tokens/layouts own visuals), covering every finance term pre-emptively — the
table grows via PRs when flags accumulate.

## Required inputs

Not an executable stage. Consumers reference this file by path and version.

## Required output

Not an executable stage. The tables below are the output.

## Schema reference

Rating terms must match `research-package.schema.json#/properties/valuation/properties/rating`;
severity/likelihood terms match `#/properties/risks`; timeframe chips match
`#/properties/catalysts`.

## Hard constraints

### Rating scale (bidirectional, exact)

| zh-CN | en-AU | schema value |
|---|---|---|
| 买入 | Buy | buy |
| 增持 | Accumulate | accumulate |
| 持有 | Hold | hold |
| 减持 | Reduce | reduce |
| 卖出 | Sell | sell |
| 未评级 | Not rated | not_rated |

### Grading and chips

| zh-CN | en-AU | context |
|---|---|---|
| 高 / 中 / 低 | high / medium / low | severity, likelihood |
| 0-3个月 / 3-12个月 / 12个月以上 | 0-3m / 3-12m / 12m+ | catalyst timeframe |
| 反方证据 | counterevidence | fixed vocabulary |
| 资料不足 | insufficient information | fixed vocabulary |
| 暂无数据 | N/A | rendered missing value |

### Financial statement terms (core set)

| zh-CN | en-AU |
|---|---|
| 营业收入 | revenue |
| 归母净利润 | net profit attributable to shareholders |
| 毛利率 | gross margin |
| 经营活动现金流 | operating cash flow |
| 资产负债率 | gearing (debt-to-asset ratio) |
| 同比 / 环比 | year on year (YoY) / quarter on quarter (QoQ) |
| 前五大客户收入占比 | top-five customer revenue concentration |

### Valuation terms

| zh-CN | en-AU |
|---|---|
| 现金流折现 | discounted cash flow (DCF) |
| 可比公司估值 | peer multiples |
| 加权平均资本成本 | weighted average cost of capital (WACC) |
| 目标价 / 现价 | target price / current price |
| 基准/乐观/悲观情景 | base / bull / bear case |
| 复合增速 | CAGR |

### Number and unit display

| stored value | zh display | en display |
|---|---|---|
| 4520000000 CNY | 45.2亿元 | CNY 4.52 billion |
| 45200000 CNY | 4,520万元 | CNY 45.2 million |
| 0.202 (ratio) → stored as 20.2 `%` | 20.2% | 20.2% |
| per-share CNY | 34.00元 | CNY 34.00 |

Scale mapping is fixed: 万 = 10^4, 亿 = 10^8, million = 10^6, billion = 10^9. Display transforms
(`wan|yi|million|billion|…`) are declared per `displayNumber`, never improvised in text.

### Dates and punctuation

- zh: 2026年7月15日; full-width punctuation; no line starting with 。，、；：）
- en-AU: 15 Jul 2026; sentence case titles; Australian spellings (analyse, capitalise,
  labour, centre, programme for initiatives / program for software).

## Missing-data behaviour

Unmapped term encountered → S6/S7 emit a `glossary_flags` entry with the term, path and proposed
mapping; the batch continues with the term left in the authoritative language. Flags convert to
glossary PRs.

## Hallucination and citation rules

Consumers may not invent mappings, may not use near-synonyms of rating/grading terms (增持 is
never "Overweight" in our house style), and may not localise IDs or schema enum values.

## Positive example

「维持"增持"评级，目标价34.00元」 → "We maintain an Accumulate rating with a CNY 34.00 target
price." — rating via the exact table, per-share format per display rules.

## Negative example

「增持」 → "Overweight" — a real-world synonym, but not this catalogue's mapping; breaks the
bidirectional guarantee that zh↔en editions state the same rating. Validator string-matches
rating terms against this table and rejects.

## Acceptance notes

Machine checks: rating/grading tables cover every schema enum value exactly once; fixture texts'
rating and grading terms appear in the tables; scale table consistent with `displayNumber`
transform enum in `slide-deck.schema.json`.
