# Jacaranda Research OS

蓝楹会 AI 股票研究平台 / Jacaranda AI Equity Research Platform

This repository is the shared workspace for a bilingual, source-grounded equity research platform covering A-shares first and US equities next.

## Current stage

Phase 0: project rules, research methodology, architecture, and presentation system.

## Development principles

- A-share MVP with a provider architecture that also supports US equities.
- Chinese and English reports generated from the same structured research package.
- Development LLM calls use OpenRouter free routing only.
- API keys are loaded from local/deployment secrets and never committed.
- AI-generated research requires source attribution and human approval.
- Codex owns engineering and integration; Claude Code owns research schemas, prompts, and presentation design.

Read `PROJECT_BRIEF.md`, `AGENTS.md`, `CLAUDE.md`, and the files under `docs/` before starting work.

