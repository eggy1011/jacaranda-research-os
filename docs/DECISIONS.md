# Decision Log

## D-001 — Market order

Status: accepted.

A-shares are the first MVP market. US equities use the same provider contracts and are expanded in phase two.

## D-002 — Bilingual output

Status: accepted.

Generate separate complete Chinese and English decks from one research package, plus an optional bilingual executive summary. Do not duplicate full Chinese and English paragraphs on every slide.

## D-003 — Development LLM routing

Status: superseded by D-008 (2026-07).

Use OpenRouter with `openrouter/free` during development. No automatic paid fallback is allowed.

## D-004 — Structured generation

Status: accepted.

The LLM produces validated research and slide JSON. Rendering code, not free-form model output, creates the final PPT.

## D-005 — Agent ownership

Status: superseded by D-010 (2026-07).

Codex owns engineering/integration. Claude Code owns research schemas, prompts and presentation design. Work is exchanged through Issues and PRs.

## D-006 — Branding

Status: accepted.

Use a professional 16:9 purple equity-research design inspired by existing Jacaranda materials without copying their exact layouts.

## D-007 — Presentation renderer

Status: accepted (2026-07, recorded retroactively).

The bespoke python-pptx renderer in `packages/presentation` (Issue #24 / PR #25) supersedes the
original "Presenton first, PptxGenJS for gaps" preference. It is token-driven, bilingual, QA-gated
and already produces the branded decks; no external presentation service is used. PDF export is
produced from the rendered PPTX via headless LibreOffice.

## D-008 — LLM budget and model rotation

Status: accepted (2026-07, project owner approval).

Replaces D-003. OpenRouter remains the single provider. Configuration holds an ordered candidate
model list with free models first; inexpensive paid models (DeepSeek/Gemini-Flash class) may follow
only when `ALLOW_PAID_MODELS` is explicitly enabled. Rotation happens on rate-limit/availability
failure, never as a silent quality upgrade. Every call records the model actually used. A small
per-month budget cap applies; anything beyond it is a new decision.

## D-009 — Internal-beta authentication

Status: accepted (2026-07, project owner approval).

Invite-code registration plus email/password login for roughly 10–30 society members. Argon2
password hashing, server-side sessions in Redis with an httpOnly signed cookie. Roles: `member`
(create/run/edit), `reviewer` (adds verify/approve), `admin` (adds invites/user management). No
SSO, no open signup, no email verification infrastructure.

## D-010 — Solo maintainership workflow

Status: accepted (2026-07).

Replaces D-005. The project is maintained by a single owner assisted by AI. Feature work still uses
short-lived branches and PRs (for CI enforcement and revert points) but is self-merged once CI is
green; the dual-AI review ritual is retired. Documentation-only changes may go directly to `main`.
The API coverage gate is 90% (was 100%); mypy strict remains. Milestone-level quality gates (fact /
research / experience / security / release) from the handover documents still apply before anything
is called releasable.

## D-011 — Deployment sequencing

Status: accepted (2026-07, project owner approval).

All five milestones are completed and accepted against the local Docker Compose stack first. Server
deployment (single VPS + Caddy TLS, per `docs/RUNBOOK.md` once written) is executed afterwards as a
documented, repeatable step. No budget is committed to hosting until the local acceptance passes.

## Open decisions

- Final hosting provider (deferred by D-011 until local acceptance passes).
- Production market-data licensing.
- Whether the final product repository remains public or becomes private.

