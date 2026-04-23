"""Publish the codebase improvement planning doc to Obsidian vault.

Usage: uv run python scripts/publish_planning_doc.py
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

FRONTMATTER = f"""---
title: "Codebase Improvement Plan: PM Working Backwards Agent"
type: planning
status: active
created: {NOW.isoformat()}
tags:
  - pm-agent
  - planning
  - improvements
  - docflow-ai
  - performance
aliases:
  - "Improvement Roadmap 2026-04"
---
"""

BODY = """# Codebase Improvement Plan: PM Working Backwards Agent

> Review date: 2026-04-23. This document captures all identified misalignments,
> fixes, and enhancement phases for the PM Working Backwards Agent and DocFlow AI
> subsystems.

## Current State Summary

Two subsystems share this repo:

1. **PM Agent System** (`src/pm_agent_system/`): 4-agent CrewAI pipeline
   (research, PRFAQ, design brief, BRD + build spec). CLI in `main.py`,
   orchestrator in `crew.py`. 449 tests collected, all passing (minus 3 that
   need `moto`).
2. **DocFlow AI** (`src/docflow_ai/`): documentation generation and drift
   detection system. CLI in `cli.py`. All code and tests are local-only
   (untracked in git).

---

## Phase 1: Immediate Fixes (Low Effort, High Value)

Target: same-day completion. These are blocking issues or easy wins.

### 1.1 Register DocFlow CLI Entry Point

- Add to `pyproject.toml` under `[project.scripts]`:
  `docflow = "docflow_ai.cli:run"`
- Add `src/docflow_ai` to `[tool.hatch.build.targets.wheel]` packages
- Validates: `.kiro/specs/docflow-cli-demo/tasks.md` Task 1.1

### 1.2 Add Missing Dependencies

| Package | Why | Section |
|---------|-----|---------|
| `anthropic>=0.30.0` | `docflow_ai/api_bridge.py` imports it directly | `dependencies` |
| `markdown-it-py>=3.0` | `html_export.py` uses it (currently transitive from crewai) | `dependencies` |
| `moto[dynamodb]>=5.0` | 3 test files import it (`test_audit_trail`, `test_dependency_registry`, `test_infrastructure`) | `[project.optional-dependencies] test` |

### 1.3 Add Haiku Pricing to `pricing.py`

The `.env` currently uses Haiku (`anthropic.claude-haiku-4-5-20251001-v1:0`)
but `MODEL_PRICING` only has Sonnet entries. Cost estimates return `$0.00`.

Add:
```python
"anthropic.claude-haiku-4-5-20251001-v1:0": {
    "input_per_1m": 0.80,
    "output_per_1m": 4.00,
},
```

### 1.4 Commit DocFlow AI to Git

Everything under `src/docflow_ai/`, `.kiro/specs/`, and ~30 test files are
untracked. This is a large amount of code that exists only locally.

### 1.5 Document Model ID Choice

The `.env` uses Haiku while all docs reference Sonnet. Add a comment in `.env`
explaining this is intentional for dev cost savings, and that production runs
should switch to Sonnet.

---

## Phase 2: Cost and Performance Tracking

Target: 1-2 days. Wire up the existing token tracking infrastructure.

### 2.1 Wire `_print_cost_summary` Into All Commands

Currently only called from `cmd_full_pipeline`. Extend to:
- `cmd_research`
- `cmd_generate`
- `cmd_brd`
- `cmd_build_spec`

### 2.2 Add Timing Instrumentation

Wrap each `crew.kickoff()` call with `time.monotonic()` and print elapsed time.
Format: `Stage completed in {elapsed:.1f}s`.

### 2.3 Add Usage Logging to JSONL

After each run, append a record to `output/usage_log.jsonl`:
```json
{
  "timestamp": "2026-04-23T16:00:00Z",
  "command": "research",
  "model": "anthropic.claude-haiku-4-5-20251001-v1:0",
  "input_tokens": 12500,
  "output_tokens": 3200,
  "estimated_cost_usd": 0.023,
  "elapsed_seconds": 45.2,
  "product_slug": "tech-docs-integrator"
}
```

This enables trend analysis over time without external infrastructure.

### 2.4 Add `--dry-run` to DocFlow CLI

Show what files would be analyzed and estimated token count without invoking
Bedrock. Useful for cost estimation before committing to a generation run.

---

## Phase 3: Test Coverage Gaps

Target: 2-3 days. Address the highest-value untested areas.

### 3.1 Fix the 3 Broken Test Imports

Add `moto[dynamodb]>=5.0` to test deps (Phase 1.2), then verify
`test_audit_trail`, `test_dependency_registry`, and `test_infrastructure` pass.

### 3.2 Investigate `test_html_export` Hang

The test file itself is fine (simple assertions). The hang appears to be an
import-time cost issue from `markdown_it`. Profile the import chain and fix or
mark with a timeout.

### 3.3 Property Tests (Highest Value)

The `.kiro/specs/docflow-ai/tasks.md` marks ~15 property test tasks as optional
(`[ ]*`). Priority order:

1. **Front-matter round-trip** (Property 1): catches serialization bugs
2. **Drift alert structure completeness** (Property 7): validates core model
3. **Severity classification validity** (Property 8): validates business logic
4. **Webhook payload parsing** (Property 4): validates integration boundary
5. **Prompt construction completeness** (Property 10): validates LLM input

### 3.4 DocFlow CLI Integration Tests

No tests exist for the CLI subcommands (`cmd_generate`, `cmd_scan`, `cmd_demo`).
Add mocked integration tests per `.kiro/specs/docflow-cli-demo/tasks.md` Task 9.2.

---

## Phase 4: Performance Enhancement

Target: 1 week. Optimize the pipeline for speed and cost.

### 4.1 Parallel BRD Sub-Tasks

The BRD generation is split into 3 sequential sub-tasks (structure, cost-risk,
synthesis). Evaluate whether the cost-risk task can run in parallel with the
structure task since they have independent inputs.

### 4.2 Parallel DocFlow Demo Presets

The 3 demo presets in `cmd_demo` run sequentially but are independent. Use
`concurrent.futures.ThreadPoolExecutor` to parallelize them.

### 4.3 Evaluate Haiku vs Sonnet Per-Stage

Not all stages need Sonnet-level quality:
- **Research synthesis**: Haiku may suffice (structured data merging)
- **PRFAQ generation**: Sonnet recommended (creative writing quality)
- **BRD structure**: Haiku may suffice (template-driven)
- **Build spec formatting**: Haiku may suffice (mechanical transformation)

Add per-agent model override support in `crew.py` via env vars:
`RESEARCH_MODEL`, `PRFAQ_MODEL`, `BRD_MODEL`, `BUILD_SPEC_MODEL`.

### 4.4 Bedrock Rate Limiting

Add rate limiting to Bedrock calls. The current code has no throttling, which
can hit API limits during full-pipeline runs or concurrent DocFlow generation.

Use `tenacity` (already a dependency) with a rate limiter.

---

## Phase 5: Observability and Alerts

Target: 1-2 weeks. Production-readiness for monitoring.

### 5.1 Structured Logging

Replace `print()` statements with structured `logging` calls throughout
`main.py` and `cli.py`. Use JSON format for machine-parseable logs.

### 5.2 CloudWatch Metrics (Optional)

If deploying to AWS, emit custom CloudWatch metrics:
- `pipeline.duration_seconds` (per stage)
- `pipeline.token_usage` (per model)
- `pipeline.cost_usd` (per run)
- `drift.alerts_generated` (per scan)
- `generation.confidence_score` (per draft)

### 5.3 Error Budget Tracking

Track success/failure rates per pipeline stage. Alert when failure rate exceeds
threshold (e.g., >10% of research runs fail due to Tavily timeouts).

### 5.4 Drift Detection Scheduling

Wire the DocFlow `cmd_scan` to a cron schedule (or EventBridge Scheduler) for
daily drift detection across monitored repos. Currently manual-only.

---

## Phase 6: Architecture Cleanup

Target: ongoing. Reduce tech debt.

### 6.1 Unify Error Handling in DocFlow

Some components raise exceptions, others return error dicts. Standardize on
Pydantic models for error responses throughout `docflow_ai/`.

### 6.2 Use Pydantic Models in DocFlow CLI

The CLI uses plain dicts instead of the Pydantic models defined in
`docflow_ai/models/`. Wire the models into the CLI code paths.

### 6.3 Front Matter Validation

The `FrontMatter` model exists but there's no runtime validation that declared
source file paths actually exist in monitored repos. Wire
`validate_dependencies()` from `front_matter_parser.py` into the generation
pipeline.

### 6.4 Style Checker Backend

The CLI hardcodes `StyleChecker(checkers=["builtin"])`. The design spec mentions
Acrolinx and Vale integration. Implement at least the Vale backend for local
linting.

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-23 | Use Haiku for dev, Sonnet for production | Cost savings during iteration |
| 2026-04-23 | Split research into 3 sub-tasks | Prevent tool-skipping under load |
| 2026-04-23 | DocFlow CLI uses in-memory registry | Avoid DynamoDB dependency for local dev |
| 2026-04-23 | Property tests marked optional | MVP speed; highest-value ones prioritized in Phase 3 |

---

## Open Questions

1. Should DocFlow AI be a separate package/repo, or stay co-located?
2. What's the target date for committing DocFlow AI to the remote?
3. Is the design brief agent (Agent 3) still planned, or deprioritized?
4. Should we add a CI pipeline (GitHub Actions) for automated test runs?
"""

# Write the file
filename = f"{DATE_SLUG}_codebase_improvement_plan.md"
filepath = PLANNING_FOLDER / filename
filepath.write_text(FRONTMATTER + BODY, encoding="utf-8")

print(f"Planning doc published to vault: {filepath}")
