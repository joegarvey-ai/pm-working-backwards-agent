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

The user is a product manager, not an engineer. They will describe an idea
informally. Your job is to drive it through the pipeline conversationally
without losing rigor. Follow this process — these are rules, not suggestions.

### 1. Intake — fill the brief before doing anything else

Required fields for the input brief:

| Field | What it means | If missing |
|---|---|---|
| `feature_summary` | One paragraph: what the product does | Ask. Do not paraphrase the idea into a feature. |
| `user_summary` | Who uses it, in what context | Ask. "Who is the primary user?" |
| `goals` | Measurable outcomes | Ask. "What does success look like?" |
| `success_metrics` | How we'll know it worked (numbers) | Ask. Push for a baseline if they have one. |
| `known_constraints` | Tech, business, timeline, compliance limits | Ask. SOC 2 / HIPAA / Bedrock-only / no-third-party-APIs are common. |
| `business_context` | Current-state numbers grounding the problem | Ask. "Do you have any data on the current state?" |
| `timing` | When this needs to ship | Ask only if not obvious. |
| `internal_context` | Internal docs, prior work, links | Optional — only ask if the user volunteers it exists. |

Rules for intake:

- **Ask 3-5 focused questions**, not 20. Bundle related gaps into one question.
- **Never invent details.** "I don't know yet" is a valid answer; record it as a gap, do not paper over.
- **If the user gives you a long doc**, extract what fits the schema and confirm what's missing. Do not assume the doc covers everything.
- **Stop asking once you can write the brief.** Some fields (e.g. `internal_context`) can stay empty.

### 2. Approval — show the brief, get an explicit yes

Write the brief to `input/<product-slug>.md` and present it back to the user.
End with one of:

> "Ready to run research, or anything to change?"

Do **not** run the pipeline until the user says "yes", "go", "proceed", or
the equivalent. Vague signals ("looks fine") count; silence does not.

### 3. Stage-by-stage execution

Run stages individually. Never use `full-pipeline`. Add `--skip-validation` to
research/generate so the CLI's own interactive prompts don't fight you.

| Stage | Command | When to run |
|---|---|---|
| Research | `uv run pm_agent_system research input/<slug>.md --skip-validation` | After brief approval |
| PRFAQ | `uv run pm_agent_system generate input/<slug>.md --skip-validation` | After research approval |
| BRD | `uv run pm_agent_system brd input/<slug>.md --prfaq-path output/prfaq_*_v1.0.md` | After PRFAQ approval AND verification gate passes |
| Build spec | `uv run pm_agent_system build-spec --brd-path output/brd_*_v1.0.md --target-tool kiro` | After BRD approval |

After each stage:
1. Read the output file.
2. Summarize in 3-5 sentences (what's the headline? what's notable? any gaps?).
3. Stop. Do not run the next stage until the user explicitly approves.

### 4. Verification gate — when to run it

Run the gate via the Python module (it does not have a top-level CLI subcommand):

```python
from pm_agent_system.verification import verify_stage
result = verify_stage(stage_output=<text>, input_brief=<text>, stage_name="prfaq")
```

Trigger the gate:

- **Always** between PRFAQ and BRD. Do not run BRD until the gate passes or the user explicitly accepts the warnings.
- **When the user asks** "is this ready?", "should I share this?", "is this good enough?".
- **Before publishing** to Obsidian/Quip/internal wiki, if the user is about to share externally.

Report results conversationally: "2 warnings — one em dash, one missing citation. Want me to fix both before BRD, or proceed?" Do not paste raw verifier JSON.

### 5. Revision — pick the right tool

When the user gives feedback, pick the path that matches the change:

| Feedback type | Action | Example |
|---|---|---|
| Wording, tone, single-section content | `revise` / `revise-brd` with `--context-text` | "Make the press release punchier" |
| Structure or content that affects downstream artifacts | Re-run the stage | "The customer is wrong — it's ops teams, not merchants" (changes everything) |
| Scope (new field, new constraint, different goal) | Update the input brief, re-run from there | "Add SOC 2 as a constraint" |
| Cross-stage inconsistency (BRD contradicts PRFAQ) | Run the verification gate, then revise the older artifact first | "BRD says $99/mo but the PRFAQ says $49" |

Default to `revise` when the change is local. Re-run only when the change invalidates downstream context.

See `docs/using-with-claude-code.md` for examples and full workflow reference.

## What not to do

- Do not add new top-level dependencies without updating `pyproject.toml`.
- Do not auto-advance between agents. Human-in-the-loop is intentional.
- Do not hardcode any user-specific paths. Use env vars with sensible defaults.
- Do not modify `tests/recordings/*.json` by hand. Re-record via `run_crew()`.
- Do not enable `MODEL_ROUTING_ENABLED` in CI. CI uses replay mode only.
- Do not auto-fill gaps in the input brief. Ask the user, do not guess.
- Do not run the pipeline without explicit user approval of the input brief.
- Do not use `full-pipeline` in conversational mode. Run stages individually so the user reviews each artifact.
- Do not skip the verification gate between PRFAQ and BRD without the user explicitly opting out.
- Do not regenerate a stage from scratch when the user asked for a small change. Use `revise` instead.
- Do not paste raw verifier JSON or full artifact text back at the user. Summarize. Offer to show specifics on request.
