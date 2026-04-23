"""Publish the Phase 4 performance planning doc to the Obsidian vault.

Usage: uv run python scripts/publish_phase4_plan.py
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
if not VAULT_PATH or not Path(VAULT_PATH).is_dir():
    print("Error: OBSIDIAN_VAULT_PATH not set or directory does not exist.")
    sys.exit(1)

PLANNING_FOLDER = (
    Path(VAULT_PATH)
    / "01 Next Actions"
    / "Deep Work"
    / "Amazon"
    / "Projects"
    / "Agentic PM Assistant"
    / "Planning Documents"
)
PLANNING_FOLDER.mkdir(parents=True, exist_ok=True)

NOW = datetime.now(timezone.utc)
DATE_SLUG = NOW.strftime("%Y-%m-%d")
FILENAME = f"{DATE_SLUG}_phase4_performance_plan.md"

FRONTMATTER = f"""---
title: "Phase 4 Plan: Pipeline Latency Reduction"
type: planning
status: active
created: {NOW.isoformat()}
tags:
  - pm-agent
  - planning
  - performance
  - latency
  - phase-4
aliases:
  - "Phase 4 Performance Plan 2026-04-23"
---
"""

BODY = """# Phase 4 Plan: Pipeline Latency Reduction

**Created**: 2026-04-23
**Status**: Active
**Scope**: Reduce full-pipeline wall-clock time
**Context**: With Dovetail integration and real customer quotes flowing through BRD + Kiro spec generation, end-to-end latency has become the primary user experience concern.

## Problem Statement

The current full pipeline runs every stage sequentially, including stages where data flow is actually parallel-safe. A single `full-pipeline` invocation today walks through:

1. `validate_input`
2. `external_research_task` (Tavily + CompetitiveIntel)
3. `customer_evidence_task` (Dovetail)
4. `research_synthesis_task`
5. `generate_prfaq`
6. `generate_design_brief` (optional)
7. `brd_structure_task`
8. `brd_cost_risk_task`
9. `brd_assembly_task`
10. `build_spec_structure_standalone`
11. `format_spec_standalone`

Two observations drove this plan:

- **External research and customer evidence share zero inputs.** Tavily queries the public web; Dovetail queries a separate research workspace. Neither consumes the other's output. Running them back-to-back leaves a full research task of wall-clock time on the table.
- **BRD cost-risk analysis does not actually need the structure task output.** Reading the current task description reveals it operates on PRFAQ + business_context + success_metrics + timing, all of which are available before the structure task begins. The `context=[structure_task]` declaration in `split_brd_crew` creates an artificial dependency.

## Plan of Attack

Four sub-phases, ordered by impact per unit of risk. Each ships and gets measured before the next begins.

---

### 4D: Baseline Measurement (do first)

**Why this comes first**: Every performance claim in this plan is an estimate. Before refactoring crew topology, capture ground-truth per-stage timings so we can prove the refactor worked. The Phase 2 JSONL logging we just added captures total elapsed time per command, which is enough for before-and-after comparison.

**What we do**:
1. Run `uv run pm_agent_system full-pipeline input/tech_docs_integrator.yaml --skip-design` on the current (sequential) code
2. Capture the JSONL record in `output/usage_log.jsonl`
3. Also capture per-task timings from CrewAI's verbose output (stderr tokens) for finer granularity
4. Record: total elapsed seconds, per-stage elapsed seconds, input/output tokens per stage, estimated cost

**Success criteria**: One committed `output/usage_log.jsonl` entry showing baseline wall-clock time. This becomes the reference point for 4A and 4B.

**Estimated investment**: 15-30 minutes of pipeline runtime plus human review checkpoints at each stage.

**Risks**:
- Human-in-the-loop checkpoints add variable wait time that muddies the measurement. Mitigation: record only the time between the `kickoff()` call and its return, which is what Phase 2 already does.

---

### 4A: Research Stage Parallelization (highest impact)

**Why**: External research (Tavily + CompetitiveIntel) and customer evidence (Dovetail) are truly independent. The synthesis task waits on both. In CrewAI, this is expressed by setting `async_execution=True` on both upstream tasks and listing both in the synthesis task's `context=`. The framework handles the join.

**What we do**:

1. In `src/pm_agent_system/crew.py`, modify `_research_tasks()`:
   - Add `async_execution=True` to `external_task` and `evidence_task`
   - Leave `synthesis_task.context=[external_task, evidence_task]` as is (CrewAI auto-joins)
2. Verify the framework version supports this syntax. CrewAI docs state async_execution has been stable since 0.30.x and we're on 1.14.2.
3. Verify both tasks still produce their respective Pydantic outputs under parallel execution.
4. Re-run the same baseline input and compare.

**Expected gain**:
- If external runs 60-90 seconds and evidence runs 45-75 seconds sequentially (~105-165s total), parallel execution drops the combined stage to the slower of the two (~60-90s). Savings: 35-50% of research stage.
- On an end-to-end pipeline where research is one of four major stages, this could shave 1-2 minutes off wall clock.

**Risks**:
- CrewAI's Bedrock adapter may serialize calls at the HTTP client layer regardless of task-level async. Mitigation: if parallel wall-clock savings stay under 20%, we investigate HTTP client pooling before claiming the refactor worked.
- Dovetail and Tavily both hit external APIs; concurrent calls could trip rate limits. Mitigation: both tools are already used in the same pipeline today, just sequentially, so the total API call volume is unchanged.
- Dovetail integration is optional (`DOVETAIL_API_TOKEN` may be unset). When unset, the evidence task is a near-instant no-op, so parallelism provides no gain and also causes no regression.

---

### 4B: BRD Cost-Risk Parallelization (medium impact)

**Why**: The `brd_cost_risk_task` description, as written, references the PRFAQ, business_context, success_metrics, and timing. It does not actually read fields from the `BRDStructureOutput`. The `context=[structure_task]` dependency in code is vestigial. If we remove it, the cost-risk task can run in parallel with structure, and the assembly task waits on both.

**What we do**:

1. Read `brd_cost_risk_task` description in `src/pm_agent_system/config/tasks.yaml` carefully to confirm no actual fields from `BRDStructureOutput` are referenced in the prompt text.
2. If confirmed, in `split_brd_crew()` in `crew.py`:
   - Remove `context=[structure_task]` from `cost_risk_task`
   - Add `async_execution=True` to both `structure_task` and `cost_risk_task`
   - Keep `assembly_task.context=[structure_task, cost_risk_task]`
3. Re-test that the final BRD output still contains real pricing data sourced from Tavily + AWS pricing lookups.
4. Compare timings before and after.

**Expected gain**: If structure and cost_risk take similar durations, the BRD stage drops from 3 task-durations to 2 (assembly + max(structure, cost_risk)). Savings: 30-33% of BRD stage.

**Risks**:
- If the task description implicitly depends on structure (e.g., the LLM generates better cost flags when it has seen the functional requirements from structure), output quality could degrade. Mitigation: visual diff the cost_flags section before and after; if quality drops, keep 4B sequential and accept the latency.
- Assembly task currently assumes structure produces first. Under parallel execution, either task could finish first. CrewAI's `context=[...]` handles ordering regardless of completion order, but worth verifying the assembly task's prompt does not rely on ordering cues.

---

### 4C: Per-Stage Model Override (optional, defer)

**Why consider**: You're running Haiku everywhere for cost reasons. PRFAQ quality is the most customer-visible output. Running Sonnet on PRFAQ alone would improve writing quality at roughly 4x the cost for that single stage (Haiku $0.80/$4.00 per 1M vs Sonnet $3.00/$15.00 per 1M). PRFAQ is typically 5-10K output tokens, so the delta per run is ~$0.10-0.20.

**Why defer**: This is a quality lever, separate from the latency focus of Phases 4A and 4B. Sonnet is also slightly slower than Haiku per token. Included here only because it was in the original planning doc's Phase 4 scope.

**What we would do**:
- Add `RESEARCH_MODEL`, `PRFAQ_MODEL`, `BRD_MODEL`, `BUILD_SPEC_MODEL` env vars in `.env.example`
- In `crew.py`, add a `_llm_for_agent(agent_name)` helper that reads the per-agent env var with fallback to `BEDROCK_MODEL_ID`
- Update each agent constructor to use its agent-specific LLM

**Estimated investment**: 1-2 hours of coding, no topology changes. Low risk.

**Decision**: Skip for now. Revisit after 4A and 4B land.

---

### 4E: Streaming Re-Enablement (future investigation)

**Why consider**: `BedrockCompletion(stream=False)` in `_llm()`. Streaming reduces perceived latency because tokens render as they arrive. For human-in-the-loop stages where the PM reads the output, this matters for UX even when wall-clock is unchanged.

**Why defer**: Commit `b2c3891` explicitly disabled streaming for build spec due to Bedrock read timeout issues with 32K output tokens. Re-enabling needs careful per-stage testing.

**What we would do**:
- Add a `stream` flag to `_llm()` and default it to `True` for small-output stages (research synthesis, BRD assembly, format spec) and `False` for large-output stages (build spec structure).
- Run a soak test on each stage to confirm no timeouts.

**Decision**: Defer until 4A and 4B prove out. Flag for Phase 5 if UX feedback calls for it.

---

## Success Metrics for Phase 4

| Metric | Baseline | Target after 4A | Target after 4B |
|--------|----------|-----------------|-----------------|
| Full-pipeline wall clock (skip design) | TBD from 4D | -15 to -25% | -25 to -40% |
| Research stage elapsed | TBD | -35 to -50% | no change |
| BRD stage elapsed | TBD | no change | -30 to -33% |
| Total token spend | TBD | no change | no change (same work, reordered) |
| BRD output quality (subjective) | TBD | no change | no change or flag |

Token spend stays flat because we are reordering work, keeping the task count constant.

## Rollback Plan

Each sub-phase is a single-commit diff in `crew.py` or `tasks.yaml`. If any refactor degrades output quality or latency:

1. `git revert <commit>` restores the sequential behavior
2. Re-run the baseline to confirm restoration
3. Document the failure mode in the session recap
4. Flag the underlying issue (e.g., CrewAI async quirks, HTTP client serialization) for a follow-up investigation

## Out of Scope

- Rewriting the PRFAQ task to be multi-step (would change output shape; requires its own spec)
- Swapping CrewAI for a different orchestration framework (months of work)
- Caching research outputs across runs (valuable; separate initiative)
- GPU/Bedrock provisioned throughput negotiation (infra-level, not code-level)

## Open Questions

1. Does CrewAI's `async_execution=True` actually run the Bedrock calls concurrently, or does the shared `BedrockCompletion` client serialize them under the hood? 4A will answer this empirically.
2. Can we measure per-task wall-clock without instrumenting each task manually? CrewAI's verbose stderr includes timing; we may want a parser.
3. What fraction of the 4-stage pipeline time is the LLM calls vs tool invocations (Tavily, Dovetail, AWS pricing)? 4D's breakdown informs future tool-layer optimizations.
"""

vault_path = PLANNING_FOLDER / FILENAME
vault_path.write_text(FRONTMATTER + BODY, encoding="utf-8")
print(f"Phase 4 plan published to vault: {vault_path}")
