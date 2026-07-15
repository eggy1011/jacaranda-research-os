# Project Brief

## Mission

Build a low-maintenance, bilingual AI equity research platform for Jacaranda Stock Market Society. The system should collect evidence, generate traceable research drafts, and export professional branded PPTX/PDF reports.

## Product scope

### MVP

1. Search and select an A-share company.
2. Keep the same provider interface ready for US equities.
3. Retrieve market, financial, filing, and uploaded-document evidence.
4. Generate a structured research package with citations.
5. Produce:
   - a complete Chinese report;
   - a complete English report;
   - an optional bilingual executive summary.
6. Preview and export a purple 16:9 PPTX/PDF.
7. Require human approval before publication.

### Not in MVP

- Brokerage execution or trading.
- Personalised financial advice.
- Social/community features.
- Crypto, options, and real-time portfolio management.
- Fully autonomous investment decisions.

## Market priority

1. A-shares first.
2. US equities supported by architecture from day one and expanded in phase two.
3. Hong Kong equities later.

## Preferred reuse

- A-shares: AKShare behind an internal provider interface.
- US equities: SEC EDGAR, FMP and Finnhub adapters.
- Documents: Docling.
- Presentations: Presenton first; PptxGenJS only for gaps.
- Research workflow inspiration: FinRobot and TradingAgents.
- go-stock is reference material only until its GPL implications are reviewed.

## LLM policy during development

- Provider: OpenRouter OpenAI-compatible API.
- Default model: `openrouter/free`.
- Never silently fall back to a paid model.
- Validate important output against JSON Schema/Pydantic.
- Record the actual returned model and task metadata, never secrets.
- Free-model failure must produce an explicit retryable state.

## Completion definition

The first vertical slice must select one A-share and one US mock/example company, generate source-linked Chinese and English research packages, and export readable branded decks without exposing secrets.

