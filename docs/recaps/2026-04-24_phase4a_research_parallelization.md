# Session Recap: Phase 4A Research Parallelization

**Date**: 2026-04-23 (evening)
**Scope**: Phase 4A of the latency-reduction plan
**Status**: Shipped, measured, validated

## Headline

The PM Working Backwards pipeline is now 12.5% faster end-to-end. A clean baseline run after the fix clocked 703s of LLM wall-clock time, down from 803s. Research stage dropped from 117s sequential to 79s parallel, a 32% stage-level reduction. Cost per run also fell 23% because fewer retries and no loops.

## What We Did

### Decision 1: Parallelize external research and customer evidence

External research (Tavily + CompetitiveIntel) and customer evidence (Dovetail) share no inputs. Running them sequentially left wall-clock on the table. CrewAI's `async_execution=True` is the right primitive, but the first attempt failed.

### Attempt 1 (reverted)

Set `async_execution=True` on both tasks, leaving them on the shared `research_agent` instance. Bedrock threw a ValidationException on the second task: two concurrent tool-use requests in the same conversation history interleaved their tool-result blocks, and Bedrock's Converse API rejects any message stream that pairs a `tooluse_*` ID with a `toolResult` for a different ID.

Root cause: when two async tasks share one agent, they append to the same conversation message list. Bedrock requires strict tool-use / tool-result pairing, so interleaved parallel tool calls always fail.

Reverted with `git revert`, kept the task naming improvements (readable log output).

### Attempt 2 (shipped)

Gave each async task its own dedicated agent with its own tool set:

- `external_research_agent`: Tavily + CompetitiveIntel + file/vault tools
- `customer_evidence_agent`: Dovetail only
- `research_agent`: synthesis agent, no tools (matches the task description)

Each agent has isolated conversation state. Parallel tool calls no longer conflict.

Also added new agent definitions to `agents.yaml` with tight backstories that match each agent's narrow scope.

### Decision 2: Fix the measurement

The first post-4A measurement looked catastrophically slow. Research synthesis appeared to take 1088 seconds, 10x the baseline. The PM stepped away during several review checkpoints, and the task callback was capturing those pauses as LLM latency.

Fix: `VaultCheckpointProvider.handle_feedback()` runs BEFORE the approval prompt. Added an `llm_completion_at` dict keyed by artifact type that records `time.monotonic()` at that point. `main.py` now prefers this timestamp for tasks with `human_input=True`. The callback timestamp stays as a fallback for tasks without human review (external research, customer evidence, synthesis).

Post-fix, the numbers tell the real story: research synthesis is about 71s of LLM work, not 1088s.

## Numbers

### Baseline (v1, sequential research)

```
validate_input:            13.6s
external_research_task:    79.9s
customer_evidence_task:    36.6s  (ran AFTER external, total research stage = 117s)
research_synthesis_task:  108.8s
generate_prfaq:           121.7s
generate_brd_chained:     266.7s
generate_build_spec:      175.8s
Total:                    803.0s
Cost:                       $0.73
```

Baseline timing includes some human-review pauses; exact LLM-only numbers are unavailable for the v1 run.

### 4A v2 (parallel research, dedicated agents, clean timing)

```
validate_input:            44.6s
customer_evidence_task:    71.9s  (parallel with external)
external_research_task:    79.1s  (parallel with evidence)
research_synthesis_task:   71.0s
generate_prfaq:           113.0s
generate_brd_chained:     231.2s
generate_build_spec:      164.3s
Total:                    703.3s
Cost:                       $0.56
```

Research stage wall-clock = max(79.1, 71.9) = 79s vs 117s sequential. Savings: 38s in-stage, 100s end-to-end.

## Files Changed

| File | Change |
|------|--------|
| `src/pm_agent_system/config/agents.yaml` | Added external_research_agent and customer_evidence_agent; tightened research_agent to a synthesis-only role |
| `src/pm_agent_system/crew.py` | Two new agent constructors, dedicated agent assignment per task, async_execution flags, task naming across all inline-built tasks |
| `src/pm_agent_system/main.py` | Prefer provider.llm_completion_at over task-callback timestamps for tasks with human review |
| `src/pm_agent_system/vault_checkpoint.py` | Capture LLM completion timestamp in handle_feedback before the approval prompt |

## Commits

```
52f976a chore: name all inline-built tasks in crew.py
08c7347 fix(metrics): exclude human review pauses from per-task timing
0c78307 perf(4A v2): parallelize research with dedicated agents per task
c41aa6b revert: remove async_execution on research tasks (Bedrock tool-result conflict)
6c4bd9c perf(4A): parallelize external research and customer evidence tasks (reverted)
```

All pushed to `origin/main`.

## What We Learned

1. **CrewAI's `async_execution=True` is only safe when each async task has its own agent instance.** The pattern extends to any future parallelization work: per-task agents, isolated tool sets, isolated conversation state.
2. **Measurement matters more than implementation.** The first 4A v2 run looked like a catastrophic regression until we checked where human-review pauses were being counted. One callback-placement bug made a 12% win look like a 110% loss.
3. **Bedrock's Converse API is strict about tool-use pairing.** Interleaved tool calls in a shared conversation always fail. The error message names the orphaned `tooluse_*` IDs, which makes the root cause obvious once you know where to look.
4. **Confidence without verification is dangerous.** The first reading of the v2 data produced a confident "10x slowdown in synthesis" diagnosis that was simply wrong. The user caught it by asking a question (did we count review time?). Future sessions should explicitly note what the measurement excludes.

## What's Next (Phase 4B-new)

The BRD stage is now the biggest single target at 231s (33% of the pipeline).

### Plan
1. Adopt the three-task BRD split (`brd_structure`, `brd_cost_risk`, `brd_assembly`) inside `full_pipeline_crew`, replacing the monolithic `generate_brd_chained` task.
2. Create a dedicated `brd_cost_risk_agent` (Tavily + AWS pricing + AWS docs) so the structure and cost-risk tasks can run in parallel without shared conversation state.
3. Remove the vestigial `context=[structure_task]` from the cost-risk task after confirming the task description does not reference structure output fields.
4. Measure.

### Expected result
- BRD drops from 231s to roughly 130s (35s assembly + max(100s structure, 100s cost_risk))
- Pipeline: 703s → ~600s (another 15% reduction)
- Combined 4A + 4B: 803s baseline → ~600s = 25% faster pipeline

## Open Questions

1. Does the BRD structure task currently depend on any field from the research or PRFAQ that the cost-risk task needs as well? (Both read from task context; cost_risk should be able to pull from same context directly.)
2. Should we push a streaming experiment (Phase 4E) after 4B lands? Perceived latency matters for human-in-the-loop UX even when wall clock stays the same.
3. Is there a case for Haiku-only everywhere vs per-stage model selection (Phase 4C)? With 703s LLM time on Haiku and quality holding, Sonnet may be overkill.
