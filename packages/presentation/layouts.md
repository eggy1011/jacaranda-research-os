# Jacaranda Slide Layout Families v0.1

Status: Phase 0 draft. All values reference `design-tokens.json`. The renderer must reject a slide whose content exceeds these limits rather than shrink text below the token scale.

## Global rules (apply to every layout)

- Page size 16:9 (13.333in × 7.5in), margins per tokens.
- Footer band on every non-cover slide: `第 N 页 / Page N` · `数据截至 / Data as of {as_of_date}` · `来源 / Source: {source_ids}` · short disclaimer reference.
- Logo: horizontal lockup (shield + wordmark, optional chapter tag), top-right, 0.45in high on all content slides; full lockup centred on cover. Content slides carry the legacy header pattern: dark-purple title top-left + thin purple rule.
- Every number shown on a slide must resolve to a `metric_id` or a `metric_ref` inside a claim; the renderer never accepts literal numbers without provenance.
- Missing data renders as `暂无数据` (zh) / `N/A` (en) in muted colour — never blank, never guessed.
- Overflow: the exporter runs a text-fit check per placeholder. Resolution order: (1) drop lowest-priority block (each block carries `priority`), (2) move overflow to an appendix slide of the same family, (3) fail the export with a validation error. Never auto-shrink below token minimum sizes.

### Language limits convention

Chinese and English consume different space. Limits below are **hard caps** per language:
- `title zh` in characters (汉字), `title en` in characters incl. spaces.
- `body zh` in characters, `body en` in words.

### zh/en typography differences (all layouts)

| Aspect | zh-CN | en-AU |
|---|---|---|
| Heading font | 思源宋体 | Georgia |
| Body font | 思源黑体 | Calibri |
| Line height | 1.35 | 1.2 |
| Bullet marker | ・ | – |
| Numbers | 半角，千分位逗号；万/亿标注在表头或单位行 | tabular lining, thousands commas; m/bn stated in header |
| Date format | 2026年7月15日 | 15 Jul 2026 |

---

## L01 Cover 封面

- **Purpose**: identify report, company, edition, date, authorship, confidentiality.
- **Inputs**: `company.name`, `company.ticker`, `report_title`, `rating`, `target_price` (optional on cover), `as_of_date`, `edition`, analyst/society line.
- **Limits**: title zh ≤ 18 字 / en ≤ 60 chars; subtitle zh ≤ 24 字 / en ≤ 80 chars.
- **Chart**: none.
- **Missing data**: rating/target price omitted as a pair if absent — never show one without the other.
- **Source footnote**: none on cover; disclaimer pointer bottom-centre, 9pt muted.
- **Background**: dark purple `#34234F`, inverse text, full logo lockup centred upper-middle.
- **Overflow**: title wraps to max 2 lines, then fail.

## L02 Section divider 章节分隔

- **Purpose**: signpost the 12-section structure.
- **Inputs**: section number, section title (localized), optional one-line kicker.
- **Limits**: title zh ≤ 12 字 / en ≤ 40 chars; kicker zh ≤ 30 字 / en ≤ 15 words.
- **Missing data**: kicker optional.
- **Source footnote**: standard footer, no source line.
- **Overflow**: kicker dropped first.

## L03 KPI / company snapshot 关键指标卡

- **Purpose**: 4–6 headline metrics as cards (price, market cap, revenue, margin, PE, etc.).
- **Inputs**: 4–6 `metric_id` refs, each with label, value+unit+currency, period, optional YoY delta (signal colour), plus a 2–3 line company descriptor claim.
- **Limits**: card label zh ≤ 8 字 / en ≤ 20 chars; descriptor zh ≤ 90 字 / en ≤ 45 words.
- **Chart**: none (cards only) or one small 12-month price sparkline.
- **Missing data**: card renders `N/A / 暂无数据`; minimum 4 cards or the layout is rejected.
- **Source footnote**: consolidated source list in footer; per-card period shown under each value.
- **Overflow**: descriptor truncates at sentence boundary → appendix.

## L04 Chart + commentary 图表与解读

- **Purpose**: one chart carrying one message, with interpretation.
- **Inputs**: 1 chart spec (series bound to metric_ids), 2–4 commentary bullets (claim refs, each tagged fact/inference/opinion).
- **Limits**: title zh ≤ 15 字 / en ≤ 50 chars; each bullet zh ≤ 40 字 / en ≤ 20 words; max 4 bullets.
- **Chart types**: line, bar, stacked_bar, grouped_bar, area, waterfall.
- **Missing data**: if the chart cannot be built from validated metrics the slide is rejected — no placeholder charts.
- **Source footnote**: chart caption carries its own source + data date; footer repeats consolidated sources.
- **Overflow**: bullets capped at 4; excess bullets dropped by priority.

## L05 Financial table 财务表

- **Purpose**: historical statements / forecast tables.
- **Inputs**: table spec of ≤ 7 columns × ≤ 10 data rows, all cells metric refs; unit/currency caption; optional 2 highlight bullets.
- **Limits**: title zh ≤ 15 字 / en ≤ 50 chars; row label zh ≤ 10 字 / en ≤ 24 chars.
- **Missing data**: `N/A` per cell; a column with >50% missing cells must be dropped by the composer.
- **Source footnote**: table caption line (`单位：百万元人民币 / CNY m · 来源 Source: SRC-x`), plus standard footer.
- **zh/en note**: zh may use 亿/万 units with the divisor stated in the caption; en uses m/bn. Same underlying `value` — only display transform differs.
- **Overflow**: >10 rows → split across two slides at a statement boundary.

## L06 Comparison cards 对比卡（竞争格局）

- **Purpose**: compare 2–4 competitors or scenarios side by side.
- **Inputs**: 2–4 cards; each: entity name, 2–4 metric refs, 1–3 qualitative claim bullets.
- **Limits**: card title zh ≤ 10 字 / en ≤ 24 chars; bullet zh ≤ 30 字 / en ≤ 14 words.
- **Missing data**: a competitor with no sourced metrics shows qualitative bullets only, flagged `资料有限 / limited data`.
- **Source footnote**: per-card source chips + standard footer.
- **Overflow**: 5+ entities → keep top 3 by relevance + "others" appendix slide.

## L07 Value chain / process 产业链与流程

- **Purpose**: upstream–midstream–downstream or process flow.
- **Inputs**: 3–6 nodes; each node: name, 1-line description, optional metric ref; company position highlighted in primary purple.
- **Limits**: node name zh ≤ 8 字 / en ≤ 18 chars; node description zh ≤ 24 字 / en ≤ 12 words.
- **Chart**: horizontal chevron flow, or the legacy left-edge vertical spine with node dots (upstream/midstream/downstream stacked vertically, per `diagram.spine` tokens). Entity diagrams use dark-purple circles / light-purple cards / block arrows per `diagram` tokens.
- **Missing data**: nodes without sources render as structure-only (no numbers).
- **Source footnote**: standard footer.
- **Overflow**: >6 nodes → group into stages.

## L08 Timeline 时间线（历史/催化剂）

- **Purpose**: milestones or dated catalysts.
- **Inputs**: 3–7 events; each: date, label, 1-line description, claim ref; future events must be `inference`/`opinion`-tagged.
- **Limits**: label zh ≤ 12 字 / en ≤ 28 chars; description zh ≤ 30 字 / en ≤ 14 words.
- **Missing data**: undated items are not allowed on a timeline — move to bullets.
- **Source footnote**: standard footer + per-event source superscripts.
- **Overflow**: >7 events → split past/future.

## L09 Valuation range / football field 估值区间

- **Purpose**: show valuation methods, ranges, target vs current price.
- **Inputs**: 2–5 method bars (method name, low/high metric refs), current price line, target price marker, assumptions box (2–4 lines, each an assumption ref).
- **Limits**: method label zh ≤ 10 字 / en ≤ 24 chars; assumption line zh ≤ 36 字 / en ≤ 18 words.
- **Chart**: football_field (horizontal range bars).
- **Missing data**: a method without both bounds is excluded; if <2 methods remain, fall back to L04 with a single-method chart.
- **Source footnote**: assumptions box cites source/assumption IDs; standard footer.
- **Overflow**: assumptions >4 lines → dedicated assumptions appendix.

## L10 Catalysts & risks 催化剂与风险

- **Purpose**: paired positive/negative drivers. Used twice (catalysts page, risks page) or combined for the summary deck.
- **Inputs**: 3–6 items per column; each: title, 1-line description, timeframe/severity chip, claim ref.
- **Limits**: item title zh ≤ 12 字 / en ≤ 28 chars; description zh ≤ 36 字 / en ≤ 18 words.
- **Missing data**: minimum 3 risks — a package with fewer fails QA, not the renderer.
- **Source footnote**: standard footer + per-item superscripts.
- **Overflow**: rank by severity/probability; excess to appendix.

## L11 Conclusion & sources 结论与来源

- **Purpose**: restate thesis + counterevidence, list all sources, full disclaimer.
- **Inputs**: conclusion claim refs (incl. ≥1 counterevidence claim), rating + target price refs, full source table (id, title, publisher, date, retrieved), disclaimer text block.
- **Limits**: conclusion zh ≤ 120 字 / en ≤ 60 words; source rows ≤ 12 per slide, auto-continued.
- **Missing data**: this layout is mandatory and cannot be dropped; missing disclaimer fails export.
- **Source footnote**: the slide *is* the source list; footer shows page/date only.
- **Overflow**: source table continues on additional numbered slides.

---

## Mapping: 12-section report → layouts

| # | Section | Default layout | Notes |
|---|---|---|---|
| 1 | Cover 封面 | L01 | |
| 2 | Investment thesis 投资摘要 | L03 (rating/target variant) | thesis bullets + 4 KPI cards |
| 3 | Company snapshot 公司概览 | L03 | |
| 4 | Industry & value chain 行业与产业链 | L07 (+L04 if market-size chart) | |
| 5 | Business model & segments 商业模式 | L04 or L05 (segment table) | |
| 6 | Competition & moat 竞争格局 | L06 | |
| 7 | Historical financials 历史财务 | L05 (+L04) | may span 2 slides |
| 8 | Forecast drivers 预测驱动 | L04 | assumptions must be assumption refs |
| 9 | Valuation 估值 | L09 | |
| 10 | Catalysts 催化剂 | L08 or L10 | |
| 11 | Risks 风险 | L10 | mandatory, ≥3 risks |
| 12 | Conclusion & sources 结论来源 | L11 | mandatory, non-removable |

Deck length: 12–18 slides (sections 4/5/7 may take two slides; source list may continue). The bilingual executive summary uses: L01 cover (bilingual title), one combined L03, one L09, one combined L10, one L11 — max 6 slides, zh and en text stacked per block with zh first.
