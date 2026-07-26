# Claude Code Instructions (research-content focus)

The project is maintained by a single human owner assisted by AI (D-010). These rules apply to any
work on research methodology, bilingual content, prompts, and presentation design.

## Read first

Before changing files, read:

1. `PROJECT_BRIEF.md`
2. `docs/RESEARCH_METHODOLOGY.md`
3. `docs/PRESENTATION_SYSTEM.md`
4. `docs/DECISIONS.md`
5. `docs/TASK_BOARD.md`

## Research-content scope

- Research-package and slide-deck schemas (`packages/research-schema/`).
- Evidence extraction, verification, analysis, translation and compression prompts
  (`packages/prompts/`).
- A-share and US-market research fields.
- Fact/inference/opinion classification; citation and provenance rules.
- Chinese/English consistency checks.
- Purple slide templates and visual QA (`packages/presentation/`).
- Research-quality rubric and hallucination checks.

Schema, prompt or visual-rule changes ripple into the pipeline, validators and renderer — make
them deliberately, never as a side effect of engineering work, and update the affected validators
and fixtures in the same PR.

## Required workflow (solo mode, D-010)

1. Feature work happens on a short-lived non-main branch and is merged through a PR once CI is
   green. Self-merge is allowed; documentation-only changes may go directly to `main`.
2. Provide structured examples that validate against the proposed schema.
3. Treat missing information as missing; never invent it.
4. Mock (`is_mock`) packages can never be promoted to `approved`.

## Security

- Never ask for or store a real API key.
- Use environment-variable names and mock evidence only.
- Never include confidential uploaded research in test fixtures without approval.
