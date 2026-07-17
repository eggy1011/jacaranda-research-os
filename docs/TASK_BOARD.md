# Task Board

## Phase 0 — Rules and contracts

| ID | Owner | Task | Status | Dependency |
|---|---|---|---|---|
| 1 | Codex | Monorepo and security baseline | Done (PR #5) | Bootstrap docs |
| 2 | Claude | Research and slide schemas | Done (PR #2, #4) | Bootstrap docs |
| 3 | Codex | Unified market-data provider | Done (Issue #18, PR #21) | 1 |
| 4 | Claude | Research prompts and quality rubric | Done (Issue #13, PR #14) | 2 |
| 5 | Codex | OpenRouter free-only provider | Done (Issue #22, PR #23) | 1, 2 |
| 6 | Claude | Purple PPT template system | In review (PR for Issue #24) | 2 |
| 7 | Codex | End-to-end mock vertical slice | Pending | 3–6 |

## Issue requirements

Every Issue must state:

1. Outcome.
2. Out of scope.
3. Allowed directories.
4. Input/output example.
5. Acceptance criteria.
6. Required tests.

## Merge policy

- No direct work on `main`.
- The other AI reviews each PR within its area of expertise.
- Blocking review comments and CI failures must be resolved.
- The human project owner approves the final merge.
