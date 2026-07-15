# Research Methodology

## Standard 12-slide structure

1. Cover.
2. Investment thesis.
3. Company snapshot.
4. Industry and value chain.
5. Business model and segments.
6. Competition and moat.
7. Historical financials.
8. Forecast drivers.
9. Valuation.
10. Catalysts.
11. Risks.
12. Conclusion, sources and disclaimer.

The structure may adapt to the company, but sources, risks and disclaimer cannot be removed.

## Evidence rules

Every key numeric fact must include:

- `value`
- `unit`
- `currency`
- `period`
- `as_of_date`
- `source_id`
- `source_url_or_document`
- `retrieved_at`

Every claim must be classified as:

- `fact`: directly supported by a cited source;
- `inference`: derived from cited facts;
- `opinion`: an analyst judgement.

Missing data remains missing. The system must not guess values or invent citations.

## Market-specific considerations

### A-shares

- Exchange/symbol normalization.
- Chinese announcements and annual/semi-annual/quarterly reports.
- CNY units and ten-thousand/one-hundred-million display conversions.
- Industry classification and policy/regulatory context.

### US equities

- SEC accession/form metadata.
- GAAP/non-GAAP distinction.
- USD reporting and fiscal-year variation.
- Earnings-call and segment disclosures where available.

## Schemas (Phase 0)

The rules above are enforced by two contracts in `packages/research-schema/`:

- `research-package.schema.json` — single source of truth per report. Shared fields cover company, sources, metrics, claims, 12 sections, valuation (with mandatory counterevidence), catalysts, ≥3 risks, quality results and disclaimer. Market-specific fields live under `company.market_specific.cn` (证监会/申万分类, share classes, actual controller, 万/亿 display convention, policy context) and `company.market_specific.us` (CIK, fiscal year end, GAAP/non-GAAP, filing accession metadata).
- `slide-deck.schema.json` — renderer input; every displayed number is a metric reference with a render-time display transform.

Validated examples live in `packages/research-schema/examples/`.

## Bilingual generation rules

Three outputs are compiled from one research package:

1. `report_zh-CN.pptx` — full Chinese edition.
2. `report_en-AU.pptx` — full English edition (Australian spelling).
3. `executive-summary-bilingual.pptx` — optional ≤6-slide condensed deck; zh and en stacked per block, zh first.

Rules:

- All narrative text in the package is a `{zh_CN, en_AU}` pair; both languages are always populated before deck compilation.
- The two full editions share metric IDs, source IDs, charts, valuation assumptions, catalysts, risks and rating. Only narrative language and typography differ.
- Translation must not alter facts, values, units, currencies, periods, or the strength of the investment conclusion (e.g. 增持 ↔ Accumulate via the approved glossary; never upgrade/downgrade in translation).
- Display units may differ per edition (亿元 vs CNY bn) but always derive from the same stored raw value via `display_transform`.
- The consistency check below (QC-03) blocks rendering on mismatch.

## Research quality rubric v0.1

Recorded per package in `quality.checks` (`QC-01`…`QC-11`). M = machine-checkable, H = needs human.

| ID | Check | Mode | Fail condition |
|---|---|---|---|
| QC-01 | Every number has provenance | M | Any metric missing one of the 8 fields; any displayed number not resolving to a metric; any dangling MET/CLM/SRC/ASM reference |
| QC-02 | Source freshness | M | Price/market data older than 5 trading days; financials superseded by a newer filing; any source `retrieved_at` missing |
| QC-03 | zh/en numeric consistency | M | Numbers extracted from zh and en claim texts disagree with each other or with the referenced metric (beyond displayed rounding) |
| QC-04 | Chart-vs-text consistency | M | A chart series value contradicts a bullet/table using the same metric |
| QC-05 | Fact/inference/opinion integrity | M+H | A `fact` without a primary/secondary source; an `inference` without support chain; opinions stated as facts (H) |
| QC-06 | Verifiability | H | Company, person, event or market datum that cannot be located in any registered source (mock packages exempt via `is_mock`) |
| QC-07 | No imputed data | M+H | Missing values filled with estimates not registered as assumptions; text claiming data that no source contains |
| QC-08 | Valuation assumptions explicit | M | Any valuation method without linked `ASM-` assumptions and rationale claims |
| QC-09 | Counterevidence present | M | `valuation.counterevidence_claim_ids` empty, or counterevidence absent from thesis/conclusion sections |
| QC-10 | Risks & disclaimer complete | M | Fewer than 3 risks; missing disclaimer; conclusion/sources section absent |
| QC-11 | No overflow / overload | M | Renderer overflow report contains failures; any slide exceeding layout limits in `packages/presentation/layouts.md` |

Overall grade: `excellent` (all pass), `acceptable` (warnings only, no fails, human sign-off), `fail` (any fail — package cannot reach `approved`).

### Hallucination rules

- The generation prompts may only reference `source_id`/`metric_id` values that exist in the package; validators reject unknown IDs.
- Entities (companies, people, products, policies) mentioned in claims must appear in at least one cited source (QC-06).
- Dates in the future relative to `as_of_date` are only allowed in claims typed `inference`/`opinion` (e.g. catalysts).
- If evidence is insufficient, the required wording is 资料不足 / "insufficient information" — a package stating this passes QC-07; a package papering over it fails.

## Human review

Before publication, a human reviewer verifies major figures, valuation assumptions, source coverage, material counterarguments, risks and disclaimer. Only packages with status `approved` may be published; `is_mock` packages can never be approved for publication.

