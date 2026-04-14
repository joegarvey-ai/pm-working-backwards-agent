---
inclusion: always
name: repo-map
description: Repository layout, run commands, and conventions for coding agents
---

# Repository Map

## What this project is

A multi-agent CrewAI system that takes a PM's product problem statement and produces, in sequence: a research brief, a PRFAQ, a BRD, and a build spec. Four agents, one orchestrator (`src/pm_agent_system/crew.py`), CLI in `src/pm_agent_system/main.py`.

## How to run things

- Install: `crewai install`
- Smoke test (cheap, Agent 1 only): `uv run pm_agent_system research examples/input.yaml`
- Full pipeline (Agents 1-3): `uv run pm_agent_system full-pipeline examples/input.yaml`
- Generate PRFAQ only (Agents 1-2): `uv run pm_agent_system generate examples/input.yaml`
- Revise existing PRFAQ: `uv run pm_agent_system revise --prfaq-path output/prfaq_foo_v1.0.md --context-text "feedback here"`
- BRD from approved PRFAQ: `uv run pm_agent_system brd examples/input.yaml --prfaq-path output/prfaq_foo_v1.0.md`
- Regenerate build spec: `uv run pm_agent_system build-spec --brd-path output/brd_foo_v1.0.md --target-tool kiro`
- Run tests: `uv run pytest tests/`
- API keys live in `.env` (see `.env.example`)

## Where things live

- Agent and task prompts: `src/pm_agent_system/config/agents.yaml`, `tasks.yaml` — most quality improvements happen here, not in Python
- Pydantic output schemas: `src/pm_agent_system/models/` — each agent's output is validated against one of these
- Tools: `src/pm_agent_system/tools/` — Tavily, Dovetail, Obsidian, file readers, style guide loader, AWS pricing, competitive intel
- Renderers: `src/pm_agent_system/utils/` — convert Pydantic objects to markdown
- CLI entry point: `src/pm_agent_system/main.py`
- Crew orchestrator: `src/pm_agent_system/crew.py`
- Example input: `examples/input.yaml`
- Example outputs: `examples/` (research brief, PRFAQ, BRD, build spec)

## Conventions

- Python 3.11+. Use `uv`, not `pip`. Dependencies in `pyproject.toml`.
- Tools attach to agents (in `crew.py`), not to tasks, unless task-specific.
- Output files go in `./output/` and rotate after `OUTPUT_RETENTION_DAYS`.
- Never commit `.env` or anything in `output/`.
- The Dovetail integration is optional. Code paths must handle `DOVETAIL_API_TOKEN` being unset.
- Do not auto-advance between agents. Human-in-the-loop is intentional.
- Do not hardcode user-specific paths. Use env vars with sensible defaults.
