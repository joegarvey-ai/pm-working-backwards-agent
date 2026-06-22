---
title: "Claude Code Handoff Brief: Harness, Evals, and Orchestration"
tags:
- pm-agent
- handoff
- claude-code
- harness
- evals
- orchestration
status: active
owner: joegarvey
created: 2026-05-07
last_updated: 2026-05-07
---

# Claude Code Handoff Brief

This document is written for Claude Code. If you are reading this as Claude Code, work through it top to bottom. Joe (the PM and engineer) is handing off an active work stream and expects you to pick up where Kiro left off.

## Your mission

Ship production-grade harness, evaluations, and agent orchestration for a multi-agent CrewAI system that generates PM artifacts (research brief, PRFAQ, BRD, build spec).

Three work streams, in priority order:

1. Prove the harness works end to end against a real crew run.
2. Wire evals into continuous integration so regressions are caught automatically.
3. Layer in LLM-as-judge evaluations and a thin orchestration surface for agent routing.

The foundation is in place. Your job is to take it from "synthetic tests pass" to "every production run is measured, replayable, and graded."

## Read these first, in this order

Before writing any code, read these documents. They give you the full context.

### From the Obsidian vault (this folder: `PM Agent/`)

1. `harness-evals-roadmap.md` is the phased roadmap. This is the source of truth for priority and sequencing. Follow it.
2. `_all_products.md` is the index of products currently in the vault. Low priority; skim.

### From the repo root

1. `CLAUDE.md` gives the minimum context for coding agents working in this repo. Read every line.
2. `AGENTS.md` is an alternative version of the same guidance. Read if `CLAUDE.md` leaves questions.
3. `README.md` is the public-facing repo overview.
4. `pyproject.toml` confirms Python 3.11+, `uv` package manager, and dependencies.

### From `.kiro/specs/`

1. `.kiro/specs/agent-harness-evals/requirements.md` defines 15 requirements in EARS format covering the harness, observability, and evals.
2. `.kiro/specs/agent-harness-evals/design.md` contains the architecture, data models, and 17 correctness properties.
3. `.kiro/specs/agent-harness-evals/tasks.md` is the implementation plan. Tasks 1-11 are complete through commit `35e958d`. Read the checkbox state to confirm.

### From the existing harness code

1. `tests/harness/__init__.py` exposes the public API: `run_crew`, `load_record`, `diff_manifests`.
2. `tests/harness/models.py` contains the Pydantic data models.
3. `tests/harness/interceptors.py` contains the LLM and Tool interceptors (this is where Step 2 below needs work).
4. `tests/test_harness_api.py`, `test_harness_replay.py`, and `test_harness_properties.py` hold 43 passing tests.

### Recent project history (Obsidian)

Path: `01 Next Actions/Deep Work/Amazon/Projects/Agentic PM Assistant/Code Recaps/`

Most recent recaps (skim these to understand what came before the harness work):

- `2026-04-30_internal_mcp_integration_full_execution.md`
- `2026-04-24_complete_session_recap.md`
- `2026-04-24_full_session_recap_2026-04-23_to_2026-04-24.md`

## Current state summary

On `main` (commit `35e958d`):

- `tests/harness/` module with 8 components: public API, Pydantic models, LLM/Tool interceptors, TraceBuilder, CostMeter, LatencyMeter, structured logging, custom exceptions.
- `tests/harness/evals/` with schema validation, minimum content checks, banned-word detection, latency budget and cost cap assertions.
- 43 passing tests across integration and Hypothesis property-based suites.
- 17 correctness properties formally defined and tested.
- No new runtime dependencies.

What is NOT done:

- The harness has never been run against a live crew. All verification is synthetic.
- `PromptSnapshot.sequence_index` is defined in the model but not populated by the interceptor.
- No golden recordings committed, so replay mode has no production baseline to verify against.
- No CI wiring, so evals run manually only.
- No LLM-as-judge evals for subjective quality (Working Backwards fidelity, citation accuracy, AWS alignment).
- No cross-run trend reporting.
- No agent orchestration layer beyond what CrewAI provides natively.

Known environmental issue:

`scripts/bedrock_smoke_test.py` runs at pytest collection time and calls `sys.exit(1)` when the Bedrock token is expired. This blocks `uv run pytest` from collecting the full suite. Fix this early (Step 1 below) or you will hit it repeatedly.

## The priority ladder

Follow this order. Do not skip ahead.

### Step 1: Fix the pytest collection blocker (XS effort, high impact)

Edit `scripts/bedrock_smoke_test.py`. Guard the `sys.exit(1)` behind `if __name__ == "__main__":`, or rename the file so pytest does not collect it. Verify with `uv run pytest --collect-only -q`.

Acceptance: pytest can collect the full suite without errors even when the Bedrock token is expired.

### Step 2: Run the harness against `research_crew` end to end (S effort, critical impact)

Joe's Bedrock token may be expired. Ask him to refresh `AWS_BEARER_TOKEN_BEDROCK` in `.env` before you run a live pipeline (see the manual steps section below).

Once the token is valid:

```python
from tests.harness import run_crew
from pm_agent_system.crew import PmAgentSystem

crew = PmAgentSystem().research_crew(skip_validation=True)
inputs = {...}  # Use examples/input.yaml as a reference
record = run_crew(
    crew,
    inputs,
    output_path="tests/recordings/research_baseline.json",
)
```

You will likely hit issues:

- The LLM interceptor's token-delta approach assumes the LLM object exposes `_token_usage`. CrewAI may not expose this consistently. Be prepared to adjust `_snapshot_token_usage` in `tests/harness/interceptors.py`.
- Agent cloning: CrewAI may clone agents when setting `llm`. Verify interceptor wrapping survives the clone.
- Async tasks (`external_research_task` and `customer_evidence_task` run in parallel via `async_execution=True`). The TraceBuilder's stack-based parent tracking assumes sequential execution. Verify spans still parent correctly.

Fix issues inline. Document each fix in a commit message.

Acceptance: a valid `RunRecord` JSON is produced, loadable via `load_record`, with at least one LLM call and tool call captured.

### Step 3: Commit 3 golden recordings (S effort, critical impact)

- `tests/recordings/research_baseline.json` for the research crew only.
- `tests/recordings/prfaq_baseline.json` for research then PRFAQ.
- `tests/recordings/full_pipeline_baseline.json` for research, PRFAQ, BRD, and build spec.

Add `tests/recordings/README.md` explaining how to regenerate them when prompts change intentionally. Store them under git LFS if they exceed 100 KB each.

Acceptance: each golden recording can be replayed via `run_crew(crew, inputs, replay_path=...)` and produces an equivalent RunRecord.

### Step 4: Wire prompt snapshot capture (M effort, high impact)

Hook CrewAI's prompt interpolation to populate the `prompt_snapshots` list on every recorded run. This is Requirement 2 from the spec. The data model supports it; the collection path does not. Look at how CrewAI builds the final system prompt and user message for each task, and capture both the raw template and the interpolated result.

Acceptance: replaying a golden recording produces the same `prompt_snapshots` list it started with, and `PromptSnapshot.diff()` returns an empty unified diff.

### Step 5: CI wiring (M effort, high impact)

Create `.github/workflows/harness-evals.yml`. On push and PR:

1. `uv sync`
2. `uv run pytest tests/test_harness_properties.py tests/test_harness_api.py tests/test_harness_replay.py`
3. Replay-based regression tests: load each golden recording, replay it, assert schema validity, minimum content, banned words, cost cap ($2.00), latency budget (300s).

Acceptance: a PR that introduces a banned word into `src/pm_agent_system/config/agents.yaml` fails CI automatically.

### Step 6: LLM-as-judge evals (L effort, high impact)

Add a new file `tests/harness/evals/judge.py`:

- `judge_prfaq_fidelity(record)` scores the PRFAQ against a Working Backwards rubric using Claude Haiku as the judge model. Rubric: no em dashes, no contrast hooks, inverted pyramid, one idea per paragraph, every claim has an inline source. Return a 1-5 score per criterion plus free-text rationale.
- `judge_citation_accuracy(record)` verifies every factual claim in ResearchOutput and PRFAQOutput traces to a source URL.
- `judge_aws_alignment(record)` checks that BRDOutput defaults to AWS services and flags any non-AWS vendor not explicitly requested in the input brief.

Store judge results in the Run_Record as a new `judge_results` field. Extend the Pydantic model.

Acceptance: running `judge_prfaq_fidelity` on a known-good PRFAQ from `examples/` returns scores above 4/5 across all criteria. Running it on a deliberately bad PRFAQ (with em dashes, contrast hooks, and banned words) returns scores below 3/5.

### Step 7: Agent orchestration layer (new work stream, M-L effort, medium impact)

This is the stretch goal. Only start once Steps 1-6 are complete.

The goal is a thin orchestration surface above CrewAI that does three things:

- Routes model calls by task type. Research synthesis and BRD assembly use Sonnet. Classification and validation use Haiku. Configurable per agent via a new `model_tier` field in `agents.yaml`.
- Captures handoffs between agents as first-class spans in the Trace (currently only `crew`, `task`, `llm_call`, and `tool_call` span types exist).
- Supports context-window compaction when prompts approach token limits. Add a pre-call hook that checks estimated prompt size and auto-compacts older conversation history via a small Haiku call.

Implement this in a new module `src/pm_agent_system/orchestration.py`. Keep it additive: existing CrewAI code paths should work unchanged.

Acceptance: a full pipeline run with model routing enabled costs at least 30% less than baseline without a measurable quality drop on the LLM-as-judge evals.

## Manual work Joe needs to do

Some steps require human action. Ping Joe (or wait until he reaches the relevant stage) before you start them.

### Before Step 2 (live harness run)

1. Refresh the Bedrock token. The current `AWS_BEARER_TOKEN_BEDROCK` in `.env` may be expired. Run `uv run python scripts/bedrock_smoke_test.py` (after fixing Step 1) to confirm. If it fails, regenerate the bearer token via the AWS console and paste the new value into `.env`.
2. Confirm which crew to record first. The roadmap says `research_crew`. Verify with Joe that this is still the right starting point. If he wants `full_pipeline_crew` first, switch accordingly (more costly but more valuable as a single recording).
3. Choose an input brief. Use `examples/input.yaml` as the default. If Joe has a specific product he wants recorded (check `examples/` for options), use that instead.

### Before Step 5 (CI wiring)

1. Confirm GitHub Actions budget. Joe's free tier may be fine for now. If he anticipates more than roughly 2,000 CI minutes per month, he may want to enforce eval runs only on PRs, not every push.
2. Set repository secrets. Replay-based CI does NOT need API keys (that is the point of replay). But any live eval (LLM-as-judge running against fresh outputs, not recordings) needs `AWS_BEARER_TOKEN_BEDROCK` and `ANTHROPIC_API_KEY` as GitHub Actions secrets. Ask Joe to add these before you enable live judge evals in CI.

### Before Step 6 (LLM-as-judge)

1. Confirm the judge model. Default recommendation: Claude Haiku 4.5 (`anthropic.claude-haiku-4-5-20251001-v1:0`). Ask Joe if he wants Sonnet for higher-fidelity judging (costs 4x more).
2. Approve the judge budget. Each full-pipeline run today costs roughly $1.50. Adding LLM-as-judge with Haiku adds roughly $0.10 to $0.20 per run. Confirm Joe is OK with the cost uplift.

### Before Step 7 (orchestration layer)

1. Joe must decide whether to commit to this step. It is the most speculative and may not pay off if he stays at solo-use scale. Open the conversation explicitly before starting.
2. Baseline cost measurement. Run 5 full pipelines and record the cost_summary from each. This is the baseline against which the 30% reduction acceptance signal is measured.

## Rules and conventions you must follow

These are non-negotiable. Read them, acknowledge them, do not violate them.

### From `product.md` and the project style guide

- No em dashes as punctuation. Use colons or sentence breaks instead.
- No contrast hooks. Phrases like "not X, instead Y" are banned when used as rhetorical devices.
- No rhetorical questions as section openers.
- No banned marketing words. The full list lives in `tests/harness/evals/quality.py` as `BANNED_WORDS`. If you write copy, scan it against this list first.
- Inverted pyramid. Lead with the claim, follow with support.
- One idea per paragraph.
- Every factual claim traces to a source. Use inline `[source](url)` citations.

### From `tech.md`

- Python 3.11+, use `uv`, not `pip`.
- AWS services are the default for any technical architecture decision. Never suggest Supabase, Firebase, Vercel, or non-enterprise services unless Joe explicitly asked for them.
- CrewAI is the agent framework. Anthropic Claude Sonnet is the LLM backbone.
- Tavily for market research, Dovetail for customer evidence (optional), Obsidian for internal notes (optional).

### From `CLAUDE.md` and repo conventions

- Tools attach to agents (in `crew.py`), not to tasks, unless task-specific.
- Output files go in `./output/` and rotate after `OUTPUT_RETENTION_DAYS`.
- Never commit `.env` or anything in `output/`.
- Do not auto-advance between agents. Human-in-the-loop is intentional.
- Do not hardcode user-specific paths. Use env vars with sensible defaults.
- Do not add top-level dependencies without updating `pyproject.toml`.

### From the harness-specific rules

- Harness lives in `tests/harness/` only. It is never imported by production code.
- Never call real LLMs in unit tests. Use replay mode or mocks.
- Every new Pydantic model must have a JSON round-trip property test in `tests/test_harness_properties.py`.
- Every new eval function must accept a RunRecord as sole required argument and raise AssertionError on failure.

## Git workflow

Joe uses feature branches and merges to main via fast-forward. Conventions:

- Branch name: `feat/agent-harness-evals-<phase>` or similar descriptive prefix.
- Commit message format: `feat(harness): <summary>`, `fix(harness): <summary>`, or `test(harness): <summary>`.
- Push with `-u origin <branch>` on first push.
- Joe's repo: `https://github.com/joegarvey-ai/pm-working-backwards-agent`. The current default branch is `main`, currently at `35e958d`.

Do NOT force-push, do NOT rewrite shared history, do NOT merge into main without confirming with Joe first.

## Acceptance for the whole handoff

You are done when:

1. The pytest collection blocker is fixed.
2. At least one live harness run has produced a valid, replay-capable RunRecord.
3. Three golden recordings are committed and verified.
4. Prompt snapshots are captured on every recorded run.
5. CI runs the deterministic eval suite on every push and PR.
6. LLM-as-judge evals exist for PRFAQ fidelity, citation accuracy, and AWS alignment.
7. (Stretch) An orchestration layer with model routing reduces full-pipeline cost by at least 30%.

When each of these is done, update the stack rank table in `harness-evals-roadmap.md` with a status of "complete" and the commit hash that closed it.

## One last thing

If anything in the existing harness code looks wrong to you, propose a change before making it. Joe and Kiro spent meaningful time on the design. Do not silently rewrite it. Explain what you want to change, why, and what the risk of not changing it is. Then wait for approval.

Good luck.
