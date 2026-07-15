# Decision Log

## D-001 — Market order

Status: accepted.

A-shares are the first MVP market. US equities use the same provider contracts and are expanded in phase two.

## D-002 — Bilingual output

Status: accepted.

Generate separate complete Chinese and English decks from one research package, plus an optional bilingual executive summary. Do not duplicate full Chinese and English paragraphs on every slide.

## D-003 — Development LLM routing

Status: accepted.

Use OpenRouter with `openrouter/free` during development. No automatic paid fallback is allowed.

## D-004 — Structured generation

Status: accepted.

The LLM produces validated research and slide JSON. Rendering code, not free-form model output, creates the final PPT.

## D-005 — Agent ownership

Status: accepted.

Codex owns engineering/integration. Claude Code owns research schemas, prompts and presentation design. Work is exchanged through Issues and PRs.

## D-006 — Branding

Status: accepted.

Use a professional 16:9 purple equity-research design inspired by existing Jacaranda materials without copying their exact layouts.

## Open decisions

- Final hosting provider.
- Production market-data licensing.
- Whether the final product repository remains public or becomes private.
- Authentication approach for the first internal release.

