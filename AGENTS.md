# Codex Instructions

Codex is the engineering and integration owner for Jacaranda Research OS.

## Read first

Before changing code, read:

1. `PROJECT_BRIEF.md`
2. `docs/ARCHITECTURE.md`
3. `docs/DECISIONS.md`
4. `docs/TASK_BOARD.md`
5. the assigned GitHub Issue

## Responsibilities

- Monorepo, Next.js, FastAPI, database, storage, jobs, Docker and CI.
- `MarketDataProvider`, `DocumentProvider`, `LLMProvider` and `PresentationProvider`.
- AKShare, SEC, FMP and Finnhub adapters.
- OpenRouter client, schema validation, retries, checkpoints and audit metadata.
- Frontend/backend integration, security, tests and deployment.

## Ownership

Codex primarily owns:

- `apps/web/`
- `apps/api/`
- `packages/providers/`
- infrastructure and CI files

Claude Code primarily owns:

- `packages/research-schema/`
- `packages/prompts/`
- `packages/presentation/`
- research and presentation methodology documents

Do not change research semantics or visual rules without an Issue and review.

## Required workflow

1. Work only on the assigned Issue and a non-main branch.
2. Before implementation, state the intended files, exclusions, acceptance criteria and risks.
3. Keep changes small and reviewable.
4. Add tests for new behaviour.
5. Run tests, type checks and secret scanning.
6. Open a PR; do not merge it yourself.

## Security

- Never commit or print a real API key.
- The browser must never receive provider keys.
- Keep only empty placeholders in `.env.example`.
- CI tests use mocks/fixtures, not live paid or secret-bearing requests.
- Development model configuration must not silently select a paid model.

