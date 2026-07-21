# Presentation System

## Design direction

- Format: 16:9.
- Style: institutional equity research; concise, analytical and chart-led.
- Primary purple: `#563F7C`.
- Dark purple: `#34234F`.
- Light purple: `#B7A3CB`.
- Background: `#F7F5FA`.
- Body: `#25232A`.
- Green/red are reserved for positive/negative financial signals.

Design tokens (colours, typography scale, spacing, table/chart styles, logo sizing) are codified in `packages/presentation/design-tokens.json`. Renderers must consume tokens, not restyle per slide.

## Brand usage

The official logo is a purple shield containing a white jacaranda tree and the emblem text "THE JACARANDA SOCIETY", with the "Jacaranda Stock Market Society" wordmark beneath.

- Cover: full lockup (shield + wordmark) centred upper-middle on the dark-purple cover, max height 2.4in, clear space of 0.5× shield width.
- Content slides: horizontal lockup (shield + wordmark, optional chapter tag such as "Sydney") top right, 0.45in high, matching the legacy deck header; shield-only as a space-constrained fallback.
- Content-slide header: dark-purple title top-left with a thin purple rule underneath (legacy pattern, kept).
- Page background is white; `#F7F5FA` is reserved for divider/appendix slides.

Calibration status: v1.1, based on the official logo plus legacy report screenshots. Owner decision (2026-07-15): keep the logo and the purple/white system; legacy layouts are reference only and are not replicated exactly.
- Never stretch, recolour, outline or distort the logo; use the supplied white-on-purple master as-is.
- Store the approved transparent asset under `assets/brand/` in a later brand-assets PR.

## Slide rules

- One core message per slide.
- Prefer charts, tables, timelines and comparison cards over long paragraphs.
- Include page number, data date and source footer.
- Render missing values as `N/A` or an approved localized equivalent.
- Use design tokens rather than hard-coded per-slide styling.
- Detect text overflow before export.

## Bilingual editions

- `report_zh-CN.pptx`: full Chinese report.
- `report_en-AU.pptx`: full English report.
- `executive-summary-bilingual.pptx`: optional condensed bilingual deck.

The two complete editions must use identical data, charts and source IDs. Layout may adapt for text length.

## Required layout families

1. Cover.
2. Section divider.
3. KPI/company snapshot.
4. Chart plus commentary.
5. Financial table.
6. Three-column competitor comparison.
7. Value-chain/process diagram.
8. Timeline.
9. Valuation range/football field.
10. Catalysts and risks.
11. Conclusion and sources.

Each layout definition must specify inputs, title/body limits, overflow behaviour, source position and language-specific typography.

Full per-layout specifications (L01–L11), the mapping from the 12 report sections to layouts, per-language character/word caps, missing-data rendering and the three-step overflow policy (drop by priority → appendix → fail, never shrink below token sizes) are defined in `packages/presentation/layouts.md`. The renderer consumes decks validating against `packages/research-schema/slide-deck.schema.json`.

## Template system (Issue #24)

`packages/presentation/template/` renders validated slide-deck JSON + research package into
editable 16:9 PPTX via python-pptx (native charts/tables, no rasterised content). See
`packages/presentation/TEMPLATE_GUIDE.md` for theme, layout mapping, chart/table/logo rules,
overflow behaviour and the PresentationProvider entry point (`template.deck.build_deck`).
Sample zh-CN and en-AU fictional decks, an all-layouts template deck and the visual QA report
live under `packages/presentation/qa/`. Brand masters: `assets/brand/`.
