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

## Bilingual consistency

Translation must preserve values, units, currencies, periods, source IDs, valuation assumptions, catalysts, risks and conclusion strength. A consistency check runs before rendering.

## Human review

Before publication, a human reviewer verifies major figures, valuation assumptions, source coverage, material counterarguments, risks and disclaimer.

