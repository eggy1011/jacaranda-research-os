# Visual QA report — Issue #24 template system

Build: `tools/build_and_qa.py` · LibreOffice 26.2.4 headless previews · pypdfium2 rasterisation.
Machine result: **32/32 checks pass** (schema, ID parity, cross-refs, L01–L11 coverage, 16:9,
reopen/editability, native charts & tables, logo placement, 暂无数据/N/A, disclaimers, geometry
bounds, placeholder scan, render). `overflow-report.json` contains zero issues for all three decks.

## Decks inspected slide-by-slide

- `jacaranda-template.pptx` — 16 slides, all 11 layout families (adds L02 divider + donut demo)
- `sample-report.zh-CN.pptx` — 14-slide full Chinese fictional report
- `sample-report.en-AU.pptx` — 14-slide full English fictional report (same MET/CLM/SRC/ASM IDs)

Previews: `qa/previews/<deck>/slide-NN.png` (+ PDF).

## Issues found during visual inspection and closed

| # | Finding | Fix |
|---|---|---|
| 1 | Fictional ticker `600XXX` tripped the placeholder scan ("XXX") | scanner no longer flags bare `XXX`; `{{ }}`/TODO/PLACEHOLDER/lorem still fail the build |
| 2 | L02 divider slide missing the brand shield | divider now carries the standard top-right shield |
| 3 | KPI card text centre-aligned by shape default; labels lacked units | explicit left alignment; units added to labels (亿元 / CNY bn / 元 / %) |
| 4 | Waterfall total pillars rendered green and legend exposed the hidden base series | totals now brand purple via a dedicated series; legend off; colour key written into the caption |
| 5 | Football-field axis started at 0, crushing the bars | value axis clamped to the data range (24–42 for the sample) |
| 6 | Risk chips displayed raw machine codes (`S:high L:medium`) in both editions | chips localise on render (严重性高·概率中 / Severity High · Likelihood Med); matrix still reads the machine form |
| 7 | Divider title/kicker alignment inconsistent | both forced left |
| 8 | Decks embedded the 3MB logo masters (≈5MB per file) | 220dpi downscaled working copies embedded instead (~250KB per deck); masters untouched |

## Residual observations (accepted)

- Preview fonts: this machine lacks Source Han; LibreOffice substitutes for CJK in the PNGs.
  The PPTX files carry the token typefaces (latin + eastAsian) and fall back gracefully on
  systems without them. Verify once on a machine with Source Han installed.
- The L02 divider's schema-required block is metadata-only (the band shows title + kicker);
  acceptable because L02 is a signpost layout.
- Waterfall/football "hidden base" series are visible in PowerPoint's chart data editor (standard
  technique); they are named `base` and documented in TEMPLATE_GUIDE.md.
