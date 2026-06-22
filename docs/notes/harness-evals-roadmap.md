---
title: Harness and Evals Roadmap
tags:
- pm-agent
- roadmap
- harness
- evals
status: draft
owner: joegarvey
last_updated: 2026-05-07
---

# Harness and Evals Roadmap

A phased plan for reaching production-grade harness and evaluation coverage for the PM Working Backwards multi-agent CrewAI system.

Items are stack-ranked by impact on the product's core use case: reliably producing PM artifacts (research brief, PRFAQ, BRD, build spec) that meet Working Backwards quality standards, within budget, without regressions.

## Current state

Commit `35e958d` on `main` delivered the foundation:

- `tests/harness/` module with run manifest capture, prompt/tool/LLM call recording, replay mode, structured traces, cost and latency meters, and structured logging.
- `tests/harness/evals/` with schema validation, banned-word detection, latency budget and cost cap assertions.
- 43 passing tests across integration and Hypothesis property-based suites.
- 17 correctness properties covering serialization round-trip, interceptor transparency, span containment, replay fidelity, and more.

What is not yet covered, in priority order below.

## Phase 1: Prove the harness works end to end (highest impact)

Every downstream phase depends on the harness running against a real crew. Until a live run produces a valid `RunRecord`, all our confidence is synthetic.

### 1.1 Run the harness against `research_crew` end to end
- Invoke `run_crew(research_crew, small_input, output_path="tests/recordings/research_baseline.json")`.
- Surface any wiring gaps: LLM interceptor hooking CrewAI's actual call path, tool wrapping surviving agent cloning, prompt interpolation timing.
- Fix issues inline.
- Why it matters: the PM pipeline starts with research. If research can be recorded and replayed, the rest of the pipeline follows the same pattern.

### 1.2 Commit 3 golden recordings
- `research_baseline.json`: minimal research run.
- `prfaq_baseline.json`: research then PRFAQ.
- `full_pipeline_baseline.json`: research then PRFAQ then BRD then build spec.
- Store under `tests/recordings/` with a README explaining how to regenerate when prompts change intentionally.
- Why it matters: regression detection needs a reference. No baseline means no drift detection.

### 1.3 Populate `PromptSnapshot.sequence_index` and wire prompt capture
- Hook CrewAI's task-level prompt interpolation to populate the `prompt_snapshots` list on every recorded run.
- Validates Requirement 2 from the spec, which the current implementation covers in the data model but not the collection path.
- Why it matters: prompt diff is how you catch "why did the PRFAQ tone shift?" regressions.

## Phase 2: Wire evals into CI so regressions get caught automatically

Manual eval runs do not scale. Every push to `main` should run cheap deterministic checks.

### 2.1 GitHub Actions workflow for cost cap and banned words
- On push and PR: run `uv run pytest tests/test_harness_properties.py tests/test_harness_api.py tests/test_harness_replay.py`.
- Fast, deterministic, no API calls required.
- Why it matters: today nothing prevents a prompt change that introduces a banned marketing word into the PRFAQ output. CI catches this on every push.

### 2.2 Replay-based regression tests
- Pytest fixtures that load each golden recording and replay it.
- Assert schema validity, minimum content, banned words, cost cap, latency budget.
- Why it matters: replay runs in under 5 seconds and costs nothing. You get the full pipeline under test without hitting Anthropic.

### 2.3 Fix pytest collection blocker in `scripts/bedrock_smoke_test.py`
- Script calls `sys.exit(1)` at module level when Bedrock token expires.
- Pytest picks it up as a test file and crashes collection, blocking full-suite runs.
- Options: rename so pytest ignores it (`_bedrock_smoke_test.py`), move it out of the collectable tree, or guard the `sys.exit` behind a `if __name__ == "__main__":` check.
- Why it matters: the full test suite cannot run reliably today. This blocks everything in Phase 2.

## Phase 3: Subjective quality evals (LLM-as-judge)

Structural checks (schema, banned words, cost cap) catch mechanical regressions. They do not catch a PRFAQ that is technically valid but narratively weak.

### 3.1 LLM-as-judge eval for PRFAQ Working Backwards fidelity
- Rubric based on your existing style rules in `product.md` and `pm-working-backwards.md`: no em dashes, no contrast hooks, inverted pyramid, one idea per paragraph, every claim has an inline source.
- Judge model scores on a 1-5 scale across 5-7 criteria, with written justification.
- Use Claude Haiku for the judge to keep judge cost under 10% of production cost.
- Why it matters: the Working Backwards style is the product's differentiator. Without a quality eval, prompt drift toward generic corporate copy goes undetected.

### 3.2 LLM-as-judge eval for citation accuracy
- Verify every factual claim in ResearchOutput and PRFAQOutput traces to a source URL.
- Judge extracts claims, matches them to citations, flags unsourced claims and citation hallucinations.
- Why it matters: unsourced claims are a documented failure mode. The product promises every claim traces back.

### 3.3 LLM-as-judge eval for AWS alignment in BRDs
- Score whether technical decisions default to AWS services (Lambda, DynamoDB, Bedrock, etc.) per your `product.md` convention.
- Flag any mention of Supabase, Firebase, Vercel, or other non-enterprise services that were not explicitly requested.
- Why it matters: off-stack technical recommendations in a BRD would embarrass the PM and require manual rework.

## Phase 4: Observability beyond the single run

Once runs are recorded and evaluated individually, the next question is trends across runs.

### 4.1 Run Record aggregation and trend reporting
- CLI command: `uv run pm_agent_system harness-trends --since 7d`.
- Aggregate cost, latency, eval scores across all Run_Records in `output/recordings/`.
- Emit a markdown summary: average cost per run, p50/p95 latency, eval pass rate, top prompt diffs.
- Why it matters: single-run evals catch acute regressions. Trend reporting catches gradual drift (prompts slowly growing, costs slowly rising).

### 4.2 Export traces to OpenTelemetry or structured JSON dashboards
- Emit spans in OpenTelemetry format so traces can be visualized in any OTLP-compatible tool.
- Alternative: export to a simple HTML trace viewer (standalone file, no hosting).
- Why it matters: a flamegraph view of a 3-minute pipeline run shows bottlenecks that a numeric latency summary cannot.

### 4.3 Cost breakdown per run phase
- Extend CostMeter to break down cost by task type (research, prfaq, brd, build_spec) in addition to per-agent.
- Why it matters: "the BRD phase grew from $0.40 to $0.80" is more actionable than "total cost rose."

## Phase 5: Infrastructure hardening (lower priority at current scale)

These are worth doing once the product has multiple users and runs per day. At solo-use scale, the ROI is lower.

### 5.1 Filesystem sandboxing
- Run each crew invocation in a temp directory so they cannot overwrite each other's output.
- Currently everything shares `output/` with timestamp-based naming, which works for solo use.
- Why it matters later: when multiple PMs share the system or CI runs multiple pipelines in parallel, isolation becomes mandatory.

### 5.2 Model routing and compaction hooks
- Auto-compact long prompts when they approach the model context window.
- Route cheap tasks (classification, validation) to Haiku and expensive tasks (research synthesis, BRD assembly) to Sonnet.
- Why it matters later: your current full pipeline costs roughly $1.50 per run. If you ran 50 pipelines a day, routing could cut this to $0.60 without quality loss.

### 5.3 Browser-based tool sandboxing
- Not currently applicable. No crew tool requires a browser today.
- Revisit if you add a web-scraping tool beyond Tavily or an interactive UI-testing tool.

## Phase 6: Additional harness feature parity (nice to have)

Items from your original 6-component list not yet addressed. Low immediate impact but worth tracking.

### 6.1 Capture CLAUDE.md, AGENTS.md, KIRO.md content in the manifest
- Hash and record steering-file content so prompt regressions can be traced to doc changes.
- Why it matters: when a coding agent behaves differently, the steering files are often the reason.

### 6.2 Capture tool descriptions and args_schemas, not just class names
- The Run_Manifest records tool class names. It does not capture the tool descriptions the LLM sees.
- A change to a tool's docstring or args_schema changes agent behavior without changing the class name.
- Why it matters: catches silent tool-description regressions that class-name-only hashing would miss.

### 6.3 Handoff and model-routing spans as first-class citizens
- Currently the trace is `crew` to `task` to `llm_call` or `tool_call`.
- Add span types for handoffs between agents, context-window compaction events, and model-routing decisions once those exist.
- Why it matters: interpretability of complex runs. Low urgency at current complexity.

## Summary stack rank

| Rank | Item | Phase | Status | Effort | Impact |
|------|------|-------|--------|--------|--------|
| 1 | End-to-end live run against research_crew | 1.1 | not started | S | Critical |
| 2 | Commit 3 golden recordings | 1.2 | not started | S | Critical |
| 3 | Wire prompt snapshot capture | 1.3 | not started | M | High |
| 4 | Fix bedrock_smoke_test pytest collection blocker | 2.3 | not started | XS | High |
| 5 | GitHub Actions for deterministic evals | 2.1 | not started | M | High |
| 6 | Replay-based regression tests in CI | 2.2 | not started | M | High |
| 7 | LLM-as-judge for PRFAQ Working Backwards fidelity | 3.1 | not started | L | High |
| 8 | LLM-as-judge for citation accuracy | 3.2 | not started | L | Medium |
| 9 | LLM-as-judge for AWS alignment in BRDs | 3.3 | not started | M | Medium |
| 10 | Run record aggregation and trend reporting | 4.1 | not started | M | Medium |
| 11 | OpenTelemetry or HTML trace export | 4.2 | not started | M | Medium |
| 12 | Cost breakdown per pipeline phase | 4.3 | not started | S | Medium |
| 13 | Filesystem sandboxing | 5.1 | not started | M | Low (solo) |
| 14 | Model routing and compaction hooks | 5.2 | not started | L | Low (solo) |
| 15 | CLAUDE.md / AGENTS.md / KIRO.md capture | 6.1 | not started | S | Low |
| 16 | Tool description and args_schema capture | 6.2 | not started | S | Low |
| 17 | First-class handoff and routing spans | 6.3 | not started | L | Low |

Effort: XS < 1hr, S 1-4hr, M 4-16hr, L 16+hr.

## Acceptance signals per phase

**Phase 1 complete when:** `uv run pytest tests/test_harness_*.py` runs green AND three golden recordings sit in `tests/recordings/` AND replaying any of them produces an equivalent RunRecord.

**Phase 2 complete when:** a pull request that introduces a banned word or exceeds a cost cap fails CI automatically.

**Phase 3 complete when:** every full-pipeline run produces a 1-5 quality score for the PRFAQ with written judge rationale, stored in the Run_Record.

**Phase 4 complete when:** `harness-trends --since 7d` prints a cost, latency, and eval-score summary across all recent runs.

**Phase 5 is deferred** until there is more than one concurrent user or more than ~10 pipelines per day.

**Phase 6 is opportunistic:** do items as they become blockers, not proactively.

## Open questions for review

1. Is the priority order right, or does the organization want LLM-as-judge evals (Phase 3) before CI wiring (Phase 2)?
2. Should we commit golden recordings to git (clear history, large files) or store them separately (smaller repo, harder to reproduce)?
3. What cost cap and latency budget values do we set as defaults for Phase 2 CI? Proposal: $2.00 and 300s based on current full-pipeline runs, with 20% headroom.
4. For the judge model (Phase 3), do we want a deterministic rubric with numeric scores, or free-form qualitative reviews that a human reads?
