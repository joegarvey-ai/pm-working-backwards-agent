# Notes for Claude / coding agents

This file gives a coding agent (Claude Code, Cursor, etc.) the minimum context it needs to work in this repo. ETH research suggests shorter context files outperform longer ones, so this is intentionally brief.

## What this project is

A multi-agent CrewAI system that takes a PM's product problem statement and produces, in sequence: a research brief, a PRFAQ, a BRD, and a build spec. Four agents, one orchestrator (`src/pm_agent_system/crew.py`), CLI in `src/pm_agent_system/main.py`.

## How to run things

- Install: `crewai install`
- Smoke test (cheap): `uv run pm_agent_system research examples/input.yaml`
- Full pipeline: `uv run pm_agent_system full-pipeline examples/input.yaml`
- API keys live in `.env` (see `.env.example`).

## Where things live

- Agent and task prompts: `src/pm_agent_system/config/agents.yaml`, `tasks.yaml`. These are the most important files. Most quality improvements happen here, not in Python.
- Pydantic output schemas: `src/pm_agent_system/models/`. Each agent's output is validated against one of these.
- Tools: `src/pm_agent_system/tools/`. Tavily, Dovetail, Obsidian, file readers, style guide loader.
- Renderers: `src/pm_agent_system/utils/`. Convert Pydantic objects to markdown.

## BRD pipeline architecture

The BRD stage runs three async siblings in parallel (`brd_structure_task`, `brd_cost_risk_task`, `brd_compliance_task`). Their outputs merge into `BRDOutput` via `brd_assembly_task`. The compliance sibling handles data classification, vendor considerations, privacy, compliance gates, launch readiness, and post-launch maintenance. STRIDE threat-model stubs and RACI matrices render deterministically after the build spec, not by the LLM.

## Conventions

- Python 3.11+. Use `uv`, not `pip`.
- Tools attach to agents (in `crew.py`), not to tasks, unless task-specific.
- Output files go in `./output/` and rotate after `OUTPUT_RETENTION_DAYS`.
- Never commit `.env` or anything in `output/`.
- The Dovetail integration is optional. Code paths must handle `DOVETAIL_API_TOKEN` being unset.

## What not to do

- Do not add new top-level dependencies without updating `pyproject.toml`.
- Do not auto-advance between agents. Human-in-the-loop is intentional.
- Do not hardcode any user-specific paths. Use env vars with sensible defaults.
