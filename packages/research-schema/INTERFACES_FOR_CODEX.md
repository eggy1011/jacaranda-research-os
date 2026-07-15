# Interface requirements for Codex (Phase 0)

Requests from Claude Code, to be turned into Issues. No implementation is prescribed — only contract behaviour the research/presentation layer depends on.

## 1. LLMProvider

```text
run(task_name, structured_input, output_json_schema) ->
  { output, requested_model, returned_model, latency_ms, input_tokens, output_tokens }
```

- Validate `output` against the given schema; on failure, retry per policy, then surface an explicit retryable error state (never a silently truncated object).
- Development routing fixed to OpenRouter `openrouter/free`; record `returned_model` verbatim into `generation_metadata.llm_calls`.
- Never pass secrets into prompt text or logs.

## 2. MarketDataProvider

- Every numeric value returned must arrive with the 8 provenance fields required by `research-package.schema.json#/properties/metrics` (value, unit, currency, period, as_of_date, source_id, source_url_or_document, retrieved_at).
- The provider registers its own `sources[]` entries (type `market_data_api`) and assigns `source_id`s from the package's sequence.
- Symbol normalisation: `market` (`CN-A`/`US`) + exchange enum per the schema; A-share display-unit conventions are handled at render time, so always return raw CNY/USD values.

## 3. Source registry

- Allocate `SRC-###` IDs per package; look-up by ID; immutable once referenced by a metric or claim.
- Uploaded documents get `url_or_document: upload://{file_id}` plus a `locator` (page/section) from Docling output.

## 4. Deterministic calculation service

- Ratios, growth rates, DCF outputs and comps ranges are computed in code and registered as metrics with `computed_by: deterministic_calc` and a populated `calculation` object. The research layer will reference, never compute.

## 5. Package validation endpoint

- JSON Schema validation of research packages and slide decks.
- Semantic checks: all `MET-/CLM-/SRC-/ASM-` references resolve; fact claims cite `primary` or `secondary` sources; ≥3 risks; counterevidence present; all 12 sections present.
- Returns machine-readable failures keyed by JSON path, so prompts can be re-run per stage (checkpointed jobs).

## 6. PresentationProvider

```text
render(slide_deck_json) -> { pptx_url, pdf_url, overflow_report }
```

- Accept only decks that validate against `slide-deck.schema.json` and whose `package_id` refers to a `verified`/`approved` package.
- Resolve `display_transform` (raw/percent/万/亿/thousand/million/billion/multiple) at render time from the package's metric values — the deck never contains literal numbers.
- Apply `packages/presentation/design-tokens.json`; enforce per-layout limits in `packages/presentation/layouts.md`; run the text-overflow check and return `overflow_report` (slide_no, block, action taken or failure).
- Render `null` cells as `暂无数据` / `N/A` per edition.

## 7. Bilingual consistency checker (can be shared code)

- Given a package: assert every `localizedText` has both languages; extract inline numbers from zh/en claim texts and compare against referenced metrics (tolerance = displayed decimals); assert rating/valuation terms map via the approved glossary (to be delivered with prompts in the next task).
