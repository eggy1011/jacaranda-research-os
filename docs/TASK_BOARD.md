# Task Board

Solo-maintainer phase tracker (see D-010). Phase 0 of the original two-agent plan is complete;
the table below is the live plan from the v3.0 handover onwards. Each phase ends in a green CI
state and a demonstrable artifact.

## Completed foundation

| Item | Evidence |
|---|---|
| Monorepo + security baseline | PR #5 |
| Research and slide schemas | PR #2, #4 (`packages/research-schema`) |
| Unified market-data provider | Issue #18, PR #21 |
| Research prompts + quality rubric | Issue #13, PR #14 (`packages/prompts`) |
| OpenRouter free-only provider | Issue #22, PR #23 |
| Purple PPT template system | Issue #24, PR #25 (`packages/presentation`, QA 32/32) |
| Offline mock E2E vertical slice | Issue #26, PR #27 (`apps/api/.../e2e/`) |

## Productisation phases (current)

| Phase | Goal | Milestone | Status |
|---|---|---|---|
| 0 | Repo sync, doc de-staling, solo workflow, coverage gate 90% | — | Done |
| 1 | Real A-share evidence: `e2e/`→`pipeline/`, live AKShare client, `jacaranda-real-e2e --symbol … --resume`, model rotation (D-008) | 1 真实A股证据 | Done (PR #28–#32); live-LLM smoke awaits an OPENROUTER_API_KEY |
| 2 | Persistence + jobs: SQLAlchemy/Alembic, arq worker with per-stage resume, projects/runs/packages/artifacts API | 2 文件与项目保存 | Done (PR #33) |
| 3 | Uploads + parsing: pypdf/python-docx/openpyxl with `upload://{file_id}#page=N` locators into S1 | 2 文件与项目保存 | In progress |
| 4 | Full bilingual web flow: next-intl, shadcn/ui, project/run/package/deck pages, section editor with QC feedback, PNG deck preview | 3 完整网页流程 | Pending |
| 5 | Formal output: LibreOffice PDF export, draft→verified→approved lifecycle (`is_mock` never approvable), version snapshots | 4 正式输出 | Pending |
| 6 | Internal beta: invite-code auth (D-009), roles, RUNBOOK, prod compose + Caddy docs, monitoring/backup; acceptance = 3 real companies run by members | 5 内部Beta | Pending |
| 7 | Hardening: prompt/presentation validators in CI, golden-fixture digest regression, per-stage token/cost panel, model-rotation visibility | — | Pending |

## Working agreement

- Feature work: short-lived branch → PR → CI green → self-merge (D-010). Docs may go direct to `main`.
- Every phase's definition of done includes its verification steps from the implementation plan.
- The five release quality gates (fact / research / experience / security / release) apply before
  any build is called releasable.
