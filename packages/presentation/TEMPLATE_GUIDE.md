# Jacaranda PPT Template System v0.1 (Issue #24)

Reproducible, editable, renderer-ready purple equity-research template. One command turns a
validated `slide-deck.schema.json` document plus its research package into a 16:9 PPTX whose
charts, tables and diagrams are native PowerPoint objects.

```bash
python3 -m pip install -r packages/presentation/requirements.txt
python3 packages/presentation/tools/make_fixtures.py    # regenerate fixtures (deterministic)
python3 packages/presentation/tools/build_and_qa.py     # build template + zh/en decks + QA battery
```

Outputs land in `packages/presentation/qa/`: `jacaranda-template.pptx` (all L01–L11),
`sample-report.zh-CN.pptx`, `sample-report.en-AU.pptx`, per-slide PNG/PDF previews,
`overflow-report.json`.

## Architecture

```text
deck JSON (slide-deck.schema.json)  ─┐
                                     ├─ template/deck.py → PPTX → qa_check() → report
research package (mock-package.json)─┘
        template/theme.py    tokens → colours/fonts/geometry (single styling source)
        template/layouts.py  slide chrome (header rule, footer, logo) + L01/L02 specials
        template/blocks.py   one builder per schema block type + metric Resolver
        template/charts.py   native chart parts (incl. waterfall & football-field technique)
```

A future PresentationProvider implements `render(slide_deck_json)` by calling
`template.deck.build_deck(deck_json, package_json, out_path)` and returning the produced file
plus the report dict — the module has no CLI/state dependencies.

## Theme and typography

All styling reads `design-tokens.json`. Latin: Georgia (headings) / Calibri (body & all numerals).
CJK: 思源宋体 (headings) / 思源黑体 (body), written as latin+eastAsian typefaces on every run;
systems without Source Han fall back per tokens (Microsoft YaHei / SimSun). Sizes come from the
token scale; the overflow policy never shrinks below it. zh line-height 1.35, en 1.2.

## Layout mapping (L01–L11)

| Layout | Visual |
|---|---|
| L01 | Dark-purple cover; full lockup centred on a white safe-area card; title, kicker, rating/target, date/edition lines |
| L02 | Light canvas, full-width purple band with section title + kicker |
| L03 | 4–6 tinted KPI cards (label+unit, value, period) + typed thesis bullets |
| L04 | One editable chart (line/bar/stacked/waterfall/donut…) + commentary bullets; chart caption carries title·unit·source |
| L05 | Purple-header table, mid-purple label column, zebra body; null ⇒ 暂无数据/N/A; unit+source caption |
| L06 | 2–4 comparison cards (entity, key numbers, qualitative bullets, limited-data flag) |
| L07 | Chevron value-chain flow; the company's node highlighted in primary purple |
| L08 | Horizontal timeline; future events hollow-dotted and only inference/opinion-backed |
| L09 | Football-field (hidden-base horizontal stacked bars, axis clamped to the value range) + price panel + assumption lines |
| L10 | Catalysts/risks twin columns with severity·likelihood chips + 3×3 risk matrix (dots placed from machine-readable chips `S:high L:medium`) |
| L11 | Conclusion panel (incl. counterevidence), full source table, disclaimer panel |

Every content slide: dark-purple title top-left + thin primary rule + shield top-right (0.45in);
footer band with page number, data as-of date, source IDs and the disclaimer reference.

## Chart & table rules

Native chart parts only (editable in PowerPoint); no 3D/gradients/shadows; series colours follow
the token order; green/red exclusively for financial signals (waterfall increase/decrease,
sign-coloured deltas). Waterfall = hidden-base stacked column with purple totals and a colour key
in the caption. Football field = hidden-base stacked horizontal bar. Every numeric visual carries
unit, period and source note; every number resolves through a `MET-###` reference — the builder
has no path that accepts a literal number.

## Logo rules

Masters live in `assets/brand/` (`jacaranda-logo-full.png` supplied by the owner;
`jacaranda-shield.png` is a mechanical crop of its shield region — no redrawing). The supplied
master is a vertical lockup with transparent cutouts, therefore: cover uses the full lockup on a
white safe-area card (cutouts stay legible on the dark cover); content slides use the shield-only
fallback permitted by the tokens (a vertical lockup is unreadable at 0.45in). A horizontal lockup
master remains a wanted brand asset. Decks embed downscaled working copies (~220dpi) so files stay
small; masters are never modified.

## Missing data, sources, integrity

Null table cells render 暂无数据/N/A in muted colour; nothing is imputed. Footers and captions are
assembled from the deck JSON's `source_ids` — a slide without its required sources fails schema
validation upstream. The fictional package (`fixtures/mock-package.json`) validates against
`research-package.schema.json`; both sample decks validate against `slide-deck.schema.json` and
share identical MET/CLM/SRC/ASM references.

## Overflow policy

Three levels, per `layouts.md`: (1) drop lowest-priority blocks, (2) continuation/appendix slide,
(3) fail with a machine-readable report. The build always emits `qa/overflow-report.json`
(geometry bounds + unresolved-placeholder checks on the reopened file); text caps are enforced
upstream by the deck compiler (S7 contract) and estimated again at build time via the
`theme.est_lines` heuristics. Fonts are never shrunk below token sizes.

## QA battery

`tools/build_and_qa.py` runs the Issue #24 checks: schema validation of all fixtures, zh/en ID
parity, cross-reference resolution, L01–L11 coverage, 16:9 dimensions, reopenability, native
chart/table counts, logo placement, 暂无数据/N/A rendering, disclaimer presence, geometry bounds,
placeholder scan, and LibreOffice PDF/PNG preview rendering for visual inspection. Current run:
**32/32 pass** — see `qa/QA_REPORT.md`.
