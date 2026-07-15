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

### DocumentProvider

Retrieves or parses filings, annual reports, announcements and user uploads into source-addressable chunks.

### LLMProvider

Accepts a task, structured input and output schema. Returns validated output plus actual model, latency and request metadata. Development configuration must remain free-only.

### PresentationProvider

Accepts a validated slide specification and produces PPTX/PDF without allowing the model to freely position unvalidated content.

## Important constraints

- Provider keys stay on the server.
- Every numeric fact includes source, period, unit, currency and retrieval time.
- Generation jobs are checkpointed by stage.
- The Chinese and English reports share data and source IDs.
- External-provider calls are cached and rate-limited.

