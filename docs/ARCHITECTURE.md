# Architecture

## Proposed stack

- Web: Next.js, TypeScript, Tailwind and shadcn/ui.
- API: FastAPI, Python and Pydantic.
- Data: PostgreSQL with pgvector.
- Jobs/cache: Redis with a background worker; MVP may begin with a simpler job runner.
- Charts: ECharts.
- Documents: Docling.
- Presentations: Presenton, with PptxGenJS for template-specific gaps.
- Deployment: Docker Compose for development and a small managed/container deployment for MVP.

## Core flow

```text
company selection
  -> market-data providers
  -> filings and uploaded documents
  -> evidence package
  -> validated research package
  -> validated slide specification
  -> PPTX/PDF renderer
  -> human review
```

## Provider boundaries

### MarketDataProvider

Normalises symbols, company profile, prices, statements, ratios and provenance across CN/US markets.

The provider contract is asynchronous and capability-based (`quote`, `financials`, `filings`). A
deterministic registry/router selects an injected AKShare, FMP, Finnhub or SEC adapter; adapters do
not own credentials or create network clients. Provider results use immutable Pydantic records
compatible with the research-package `sources[]` and `metrics[]` contracts. Package-local source
registration is persistent/immutable: registering a source returns a new registry and every
`source_id` referenced by a metric must resolve before the result is accepted.

| Adapter | Market | Current capability | Credential/config gate |
|---|---|---|---|
| AKShare | CN-A | quote | none |
| FMP | US | quote | `FMP_API_KEY` |
| Finnhub | US | quote | `FINNHUB_API_KEY` |
| SEC | US | financials | `SEC_USER_AGENT` (not a secret) |

This foundation contains only injected client protocols and strict response normalisation. Wiring
real SDK/HTTP clients, caching and bounded retry execution belongs to a later integration task;
tests use synthetic fixtures and block socket access.
The `filings` capability is reserved until a typed filing-record result is defined; numeric SEC
company facts are exposed only through `financials`.

US ticker normalisation does not guess an exchange. The selected provider supplies and validates
NYSE/NASDAQ/AMEX identity data when a later company-profile capability is added. A-share `.SS` /
`.SH` and `.SZ` suffixes determine SSE/SZSE directly.

### DocumentProvider

Retrieves or parses filings, annual reports, announcements and user uploads into source-addressable chunks.

### LLMProvider

The asynchronous provider-neutral contract accepts a registered task name, structured JSON input
and a Draft 2020-12 output schema. The prompt catalogue is the task authority: the provider loads
the prompt version and registry-bound schema without modifying Claude-owned files. Cross-file
schema references are bundled into one self-contained object before a structured-output request,
and every response is parsed strictly and validated again locally.

The OpenRouter implementation is globally locked to `openrouter/free`, requests strict JSON Schema
output with `require_parameters: true`, and records the actual returned model verbatim. It never
uses `openrouter/auto`, a named paid model or a paid fallback. Invalid JSON, schema-invalid output
and truncated completions receive at most three total attempts with structured validator feedback;
transport, authentication and rate-limit failures are classified and returned to the future
scheduler without an internal retry loop. Tests inject an offline HTTP boundary and block sockets.

### PresentationProvider

Accepts a validated slide specification and produces PPTX/PDF without allowing the model to freely position unvalidated content.

## Important constraints

- Provider keys stay on the server.
- Every numeric fact includes source, period, unit, currency and retrieval time.
- Generation jobs are checkpointed by stage.
- The Chinese and English reports share data and source IDs.
- External-provider calls are cached and rate-limited.
