# Claude Code Instructions

Claude Code is the research methodology, bilingual content, prompt, and presentation design owner.

## Read first

Before changing files, read:

1. `PROJECT_BRIEF.md`
2. `docs/RESEARCH_METHODOLOGY.md`
3. `docs/PRESENTATION_SYSTEM.md`
4. `docs/DECISIONS.md`
5. `docs/TASK_BOARD.md`
6. the assigned GitHub Issue

## Responsibilities

- Research-package and slide-deck schemas.
- Evidence extraction, verification, analysis, translation and compression prompts.
- A-share and US-market research fields.
- Fact/inference/opinion classification.
- Citation and provenance rules.
- Chinese/English consistency checks.
- Purple slide templates and visual QA.
- Research-quality rubric and hallucination checks.

## Ownership

Claude Code primarily owns:

- `packages/research-schema/`
- `packages/prompts/`
- `packages/presentation/`
- `docs/RESEARCH_METHODOLOGY.md`
- `docs/PRESENTATION_SYSTEM.md`

Do not modify API infrastructure, database migrations, authentication or deployment unless the Issue explicitly authorises it.

## Required workflow

1. Work only on the assigned Issue and a non-main branch.
2. Before editing, state intended files, exclusions, acceptance criteria and required Codex interfaces.
3. Provide structured examples that validate against the proposed schema.
4. Treat missing information as missing; never invent it.
5. Open a PR and ask Codex to review implementation compatibility.
6. Do not merge the PR yourself.

## Security

- Never ask for or store a real API key.
- Use environment-variable names and mock evidence only.
- Never include confidential uploaded research in test fixtures without approval.

