# Jacaranda Research OS

蓝楹会 AI 股票研究平台 / Jacaranda AI Equity Research Platform

This repository is the shared workspace for a bilingual, source-grounded equity research platform covering A-shares first and US equities next.

## Current stage

Phase 1 engineering baseline: Next.js web, FastAPI, PostgreSQL/pgvector, Redis, Docker Compose,
automated checks, and secret scanning. Market-data, LLM, research, and presentation integrations are
not enabled yet.

## Development principles

- A-share MVP with a provider architecture that also supports US equities.
- Chinese and English reports generated from the same structured research package.
- Development LLM calls use OpenRouter free routing only.
- API keys are loaded from local/deployment secrets and never committed.
- AI-generated research requires source attribution and human approval.
- Codex owns engineering and integration; Claude Code owns research schemas, prompts, and presentation design.

Read `PROJECT_BRIEF.md`, `AGENTS.md`, `CLAUDE.md`, and the files under `docs/` before starting work.

## Prerequisites

- Docker Desktop with Docker Compose v2 for the full development stack.
- Node.js 22 and pnpm 10 for local web development.
- Python 3.11 for local API development.

Do not put real credentials in the repository. Local overrides belong in an ignored `.env` file;
the committed `.env.example` intentionally contains empty values only.

## Start the development stack

From the repository root, run the single documented startup command:

```bash
(test -f .env || (umask 077 && printf 'POSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 24)" > .env)) && docker compose up --build
```

On first run, this creates an ignored, owner-readable `.env` with a random local PostgreSQL
password. Later runs reuse the same password so it continues to match the existing PostgreSQL data
volume. Do not commit `.env`. To rotate the local password, first remove the development volume with
`docker compose down --volumes`, then replace the password in `.env` before starting again.

Then open:

- Web status page: <http://localhost:3000>
- API liveness endpoint: <http://localhost:8000/health>
- API Swagger UI (development only): <http://localhost:8000/docs>
- API ReDoc (development only): <http://localhost:8000/redoc>

PostgreSQL and Redis listen on localhost only. The web container reaches the API over the private
Compose network, and provider credentials are never exposed through `NEXT_PUBLIC_` variables.

Stop the stack with:

```bash
docker compose down
```

Add `--volumes` only when you intentionally want to delete local PostgreSQL and Redis data.

## Run checks locally

Install and check the web application:

```bash
pnpm install
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Install and check the API in an isolated environment:

```bash
python3 -m venv apps/api/.venv
apps/api/.venv/bin/python -m pip install -e "apps/api[dev]"
apps/api/.venv/bin/ruff check apps/api
apps/api/.venv/bin/mypy apps/api/src apps/api/tests
apps/api/.venv/bin/pytest apps/api
```

CI repeats these checks, builds and starts all four Compose services, verifies the runtime health
endpoints, and scans the Git history for secrets. Tests must use mocks or fixtures and must not call
live providers.

## Offline mock vertical slice

Issue #26 provides a credential-free S1–S7 integration path. It uses only the fictional `600XXX`
fixtures, blocks socket creation for the full run, batches S6 at 20 texts or fewer, and executes S7
as one plan call followed by one call per slide:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e 'apps/api[dev]'
.venv/bin/jacaranda-mock-e2e --output-dir /tmp/jacaranda-mock-run
```

The new or empty output directory receives `research-package.json`, both edition Deck JSON files,
editable PPTX files, passing overflow reports, a deterministic manifest, and checkpoint audit data.
The mock package stops at `verified`; this workflow never performs human `approved` promotion.

## Service boundaries

- `apps/web/`: browser application and a same-origin health proxy.
- `apps/api/`: server-only API and configuration.
- `packages/`: research, prompt, and presentation contracts owned by Claude Code.

The backend health endpoint is intentionally a liveness check. Database and Redis readiness are
reported by their Docker Compose health checks until application persistence is implemented.
