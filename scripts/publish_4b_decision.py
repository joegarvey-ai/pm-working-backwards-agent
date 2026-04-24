"""Publish the Phase 4B decision doc to the Obsidian vault.

Usage: uv run python scripts/publish_4b_decision.py
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
FILENAME = f"{DATE_SLUG}_phase4b_decision_brd_parallelization.md"

FRONTMATTER = f"""---
title: "Decision: Phase 4B BRD Parallelization Approach"
type: decision
status: approved
created: {NOW.isoformat()}
tags:
  - pm-agent
  - decision
  - performance
  - phase-4b
  - parallelization
  - brd
aliases:
  - "Phase 4B Decision 2026-04-23"
---
"""

BODY = """# Decision: Phase 4B BRD Parallelization Approach

**Date**: 2026-04-23 (evening)
**Decision owner**: Joe (PM)
**Recorder**: Claude (pair-programming session)
**Status**: Approved; executing

## Context

Phase 4A shipped and validated. Pipeline wall-clock time dropped from 803s baseline to 703s after parallelizing external research and customer evidence with dedicated agents. Quality held, cost fell 23%.

Post-4A, the BRD stage is the single biggest remaining latency target at 231s of LLM time, or 33% of the full pipeline. Phase 4B is the plan to reduce it.

## The Question

Can the BRD generation be parallelized, and if so, at what quality risk?

The split BRD pipeline already exists for the standalone `brd` command via `split_brd_crew`. It runs three sequential tasks:

1. `brd_structure_task`: produces prose, user stories, functional/non-functional requirements, technical context
2. `brd_cost_risk_task`: produces cost flags (with Tavily and AWS pricing lookups), risks, success metrics, timeline, version history
3. `brd_assembly_task`: merges the two outputs into final BRDOutput, no tools

Today, `brd_cost_risk_task` has `context=[structure_task]` wired in, meaning CrewAI forces it to wait for structure. But a close reading of the task description shows it only needs:

- The PRFAQ (for risks and gaps)
- The research brief (for cost-relevant architectural decisions)
- The PM's business_context, success_metrics, timing, and known_constraints

The cost_risk task's description does reference "technical complexity from the structure" as an input to the risks section. That is the only real data-flow dependency on structure.

## Options Considered

### Option A: True parallel with updated task description (CHOSEN)

Run `brd_structure_task` and `brd_cost_risk_task` in parallel using `async_execution=True`. Assembly waits on both.

Required changes:
- Add a dedicated `brd_cost_risk_agent` to `agents.yaml` with a narrow tool set (Tavily + AWS pricing + AWS docs only). Dedicated agent is mandatory to avoid the Bedrock tool-result interleaving bug that killed 4A v1.
- Update `brd_cost_risk_task` description so risks derive from PRFAQ architecture hints + known_constraints, not from structure's technical_context field.
- Remove `context=[structure_task]` from cost_risk; add `context=[research, prfaq_task]` in full_pipeline_crew.
- Add `async_execution=True` to both structure and cost_risk tasks.
- Mirror the change in `split_brd_crew` so the standalone `brd` command benefits too.

Expected gain: BRD stage drops from 231s to roughly 135s (assembly ~35s + max of two parallel tasks ~100s each). Savings: about 100s or 14% of pipeline.

Combined with 4A: 803s baseline → projected 600s = 25% faster pipeline.

Quality risk: moderate. The risks section of the BRD may miss structure-derived risks that were easier to spot when cost_risk could read the technical_context_and_dependencies field directly. Mitigation: the updated task description explicitly names the PRFAQ's architecture hints and the PM's known_constraints as the risk sources. PRFAQ and research already provide the architectural signal.

Rollback: single revert commit if BRD quality degrades.

### Option B: Adopt the split sequentially (no async) (REJECTED)

Replace the monolithic `generate_brd_chained` with the existing three-task sequential split. No parallelism; each task just runs smaller.

Rejected because:
- No latency win. Three sequential Bedrock round-trips of roughly 100s each easily add up to 250-280s, which is likely worse than the current 231s monolith. Per-call overhead is about 10s that compounds across three calls.
- The split's original purpose was to avoid Bedrock read timeouts on 32K-token BRD outputs, which is a correctness/reliability concern. Current runs are not timing out.
- The whole point of splitting BRD in this phase is to unlock parallelism. Without parallelism, the split is neutral at best.

### Option C: Skip BRD, go to 4E streaming (DEFERRED)

Re-enable Bedrock streaming on BRD so the PM sees tokens render as they arrive. Wall-clock unchanged; perceived latency improves for human review.

Deferred because:
- Phase 1 disabled streaming explicitly (commit b2c3891) to avoid Bedrock read timeouts on large BRD outputs.
- Re-enabling needs careful per-stage testing to avoid regressing reliability.
- This is a UX improvement rather than a throughput improvement. Throughput is the current bottleneck.

Revisit after 4B-A lands.

### Option D: Skip BRD, go to 4C per-stage model selection (DEFERRED)

Add env vars to override model per stage (e.g., Haiku for structure, Sonnet for cost_risk, or vice versa).

Deferred because:
- Primary use case is quality/cost tuning. Sonnet is slightly slower than Haiku per token, so this adds latency in most scenarios.
- Current Haiku output quality is holding across all stages.
- Adds config surface without addressing the 231s bottleneck.

## Decision

**Ship Option A.** The latency win justifies the moderate quality risk, and the dedicated-agent pattern from 4A is proven.

## Execution Plan

1. Update `src/pm_agent_system/config/agents.yaml`: add `brd_cost_risk_agent` with narrow tool set.
2. Update `src/pm_agent_system/config/tasks.yaml`: reword `brd_cost_risk_task` description so risks source from PRFAQ + known_constraints instead of structure output.
3. Update `src/pm_agent_system/crew.py`:
   - Add `brd_cost_risk_agent()` constructor method.
   - In `split_brd_crew`: remove `context=[structure_task]` from cost_risk, add PRFAQ path via kwargs, add `async_execution=True` on both structure and cost_risk.
   - In `full_pipeline_crew`: swap the monolithic BRD task for the three-task split; assign dedicated agents; add `async_execution=True`.
4. Test on the tech_docs_integrator input.
5. Measure per-task timing and compare to 4A baseline.
6. Commit and push.

## Success Criteria

- Pipeline wall-clock drops from 703s to roughly 600s on the same input.
- BRD stage drops from 231s to roughly 135s.
- BRDOutput still contains cost_flags with real pricing data, risks with mitigations, success_metrics with baseline-to-target mappings.
- No Bedrock errors.

## Rollback Criteria

If any of the following happens, revert the 4B-A commit and evaluate:

- Bedrock tool-result errors like 4A v1 (indicates agent isolation not working)
- BRD output missing cost_flags, risks, or success_metrics fields
- BRD risks section contains zero technical risks
- Pipeline wall-clock increases rather than decreases
- BRD quality visibly drops during PM review

## Open Question for Follow-Up

The three-task split has a known limitation: the `brd_assembly_task` runs as a separate Bedrock round-trip that just copies fields from its two inputs. That call is itself ~30-50s of overhead that the monolithic BRD does not pay. An alternate architecture would skip the assembly task entirely and assemble in Python via a post-processing step, saving that round-trip. Worth evaluating as a follow-up if Phase 4B-A lands but the wall-clock win is smaller than projected.
"""

vault_path = PLANNING_FOLDER / FILENAME
vault_path.write_text(FRONTMATTER + BODY, encoding="utf-8")
print(f"Decision doc published to vault: {vault_path}")
