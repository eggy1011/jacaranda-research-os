# Agent Instructions (engineering focus)

The project is maintained by a single human owner assisted by AI (D-010). Any AI agent doing
engineering work in this repository follows these rules.

## Read first

Before changing code, read:

1. `PROJECT_BRIEF.md`
2. `docs/ARCHITECTURE.md`
3. `docs/DECISIONS.md`
4. `docs/TASK_BOARD.md`

## Engineering scope

- Monorepo, Next.js, FastAPI, database, storage, jobs, Docker and CI.
- `MarketDataProvider`, `DocumentProvider`, `LLMProvider` and `PresentationProvider`.
- AKShare, SEC, FMP and Finnhub adapters and their live clients.
- OpenRouter client, schema validation, retries, checkpoints and audit metadata.
- Frontend/backend integration, security, tests and deployment.

Research-content contracts live in `packages/research-schema`, `packages/prompts` and
`packages/presentation` (see `CLAUDE.md`). Do not change research semantics or visual rules as a
side effect of engineering work; make such changes deliberately and state them in the PR.

## Required workflow (solo mode, D-010)

1. Feature work happens on a short-lived non-main branch and is merged through a PR once CI is
   green. Self-merge is allowed; documentation-only changes may go directly to `main`.
2. Keep changes small and reviewable; each PR states its intent and acceptance criteria.
3. Add tests for new behaviour. The API coverage gate is 90%; mypy strict must pass.
4. Never mark work done without its verification step from `docs/TASK_BOARD.md`.

## Security

- Never commit or print a real API key.
- The browser must never receive provider keys.
- Keep only empty placeholders in `.env.example`.
- CI tests use mocks/fixtures, not live paid or secret-bearing requests.
- Paid LLM models require the explicit configuration opt-in from D-008; never a silent selection.
