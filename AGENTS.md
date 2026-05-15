# Notes for Claude / coding agents

This file gives a coding agent (Claude Code, Cursor, etc.) the minimum context it needs to work in this repo. ETH research suggests shorter context files outperform longer ones, so this is intentionally brief.

## What this project is

A multi-agent CrewAI system that takes a PM's product problem statement and produces, in sequence: a research brief, a PRFAQ, a BRD, and a build spec. Four agents, one orchestrator (`src/pm_agent_system/crew.py`), CLI in `src/pm_agent_system/main.py`.

## How to run things

- Install: `crewai install`
- Smoke test (cheap): `uv run pm_agent_system research examples/input.yaml`
- Full pipeline: `uv run pm_agent_system full-pipeline examples/input.yaml`
- API keys live in `.env` (see `.env.example`).
- Model routing: set `MODEL_ROUTING_ENABLED=true` in `.env` to use Opus for research/PRFAQ and Haiku for classification.
- Trend report: `uv run python -m pm_agent_system.harness_trends --since 7d`
- Trace export: `uv run python -m pm_agent_system.trace_export tests/recordings/prfaq_baseline.json`

## Where things live

- Agent and task prompts: `src/pm_agent_system/config/agents.yaml`, `tasks.yaml`. These are the most important files. Most quality improvements happen here, not in Python.
- Pydantic output schemas: `src/pm_agent_system/models/`. Each agent's output is validated against one of these.
- Tools: `src/pm_agent_system/tools/`. Tavily, Dovetail, Obsidian, file readers, style guide loader.
- Renderers: `src/pm_agent_system/utils/`. Convert Pydantic objects to markdown.
- Orchestration: `src/pm_agent_system/orchestration.py`. Model routing (Opus/Sonnet/Haiku) and retry logic.
- Verification: `src/pm_agent_system/verification.py`. Inter-stage quality gate.
- Harness: `tests/harness/`. Recording, replay, evals, and LLM-as-judge.
- Recordings: `tests/recordings/`. Golden baselines for replay-based regression.

## BRD pipeline architecture

The BRD stage runs three async siblings in parallel (`brd_structure_task`, `brd_cost_risk_task`, `brd_compliance_task`). Their outputs merge into `BRDOutput` via `brd_assembly_task`. Use `sequential_brd=True` on `full_pipeline_crew()` for reliability when recording. The compliance sibling handles data classification, vendor considerations, privacy, compliance gates, launch readiness, and post-launch maintenance. STRIDE threat-model stubs and RACI matrices render deterministically after the build spec, not by the LLM.

## Harness and evals

- `tests/harness/run_crew()` wraps any crew with LLM/tool interception, producing a `RunRecord`.
- Replay mode: `run_crew(crew, inputs, replay_path="tests/recordings/...")` serves canned responses. No API calls.
- Judge evals: `tests/harness/evals/judge.py` scores PRFAQ fidelity, citation accuracy, and AWS alignment via Bedrock.
- CI: `.github/workflows/harness-evals.yml` runs deterministic tests and replay regression on every push/PR.

## Conventions

- Python 3.11+. Use `uv`, not `pip`.
- Tools attach to agents (in `crew.py`), not to tasks, unless task-specific.
- Output files go in `./output/` and rotate after `OUTPUT_RETENTION_DAYS`.
- Never commit `.env` or anything in `output/`.
- The Dovetail integration is optional. Code paths must handle `DOVETAIL_API_TOKEN` being unset.
- Harness code lives in `tests/harness/` only. Never imported by production code.
- Never call real LLMs in unit tests. Use replay mode or mocks.

## Conversational pipeline workflow

When a user describes a product idea (even informally), follow this process:

1. **Ask clarifying questions** before structuring anything. You need: feature summary, target user, goals, success metrics, known constraints, and business context. Ask 3-5 focused questions to fill gaps. Do NOT invent details.
2. **Write a structured input brief** and present it for approval. Do not run the pipeline until the user says yes.
3. **Run stages individually** (`research`, then `generate`, then `brd`, then `build-spec`). Do not use `full-pipeline`. Add `--skip-validation` to each.
4. **Summarize each output** in 3-5 sentences. Wait for the user to say "proceed" or give feedback before running the next stage.
5. **Run the verification gate** between PRFAQ and BRD (or when the user asks "is this ready?"). Report issues conversationally.

See `docs/using-with-claude-code.md` for the full workflow reference.

## What not to do

- Do not add new top-level dependencies without updating `pyproject.toml`.
- Do not auto-advance between agents. Human-in-the-loop is intentional.
- Do not hardcode any user-specific paths. Use env vars with sensible defaults.
- Do not modify `tests/recordings/*.json` by hand. Re-record via `run_crew()`.
- Do not enable `MODEL_ROUTING_ENABLED` in CI. CI uses replay mode only.
- Do not auto-fill gaps in the input brief. Ask the user, do not guess.
- Do not run the pipeline without explicit user approval of the input brief.
