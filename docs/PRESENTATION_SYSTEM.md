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

## Brand usage

- Cover: logo centred with generous safe area.
- Content slides: small logo at the top right.
- Never stretch, recolour or distort the logo.
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

