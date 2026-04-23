"""Publish a session recap to the Obsidian vault and repo docs/recaps/.

Usage: uv run python scripts/publish_recap.py
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

RECAP_FOLDER = (
    Path(VAULT_PATH)
    / "01 Next Actions"
    / "Deep Work"
    / "Amazon"
    / "Projects"
    / "Agentic PM Assistant"
    / "Code Recaps"
)
RECAP_FOLDER.mkdir(parents=True, exist_ok=True)

REPO_RECAP_FOLDER = Path(__file__).parent.parent / "docs" / "recaps"
REPO_RECAP_FOLDER.mkdir(parents=True, exist_ok=True)

NOW = datetime.now(timezone.utc)
DATE_SLUG = NOW.strftime("%Y-%m-%d")
FILENAME = f"{DATE_SLUG}_phase1_and_phase2_execution.md"

FRONTMATTER = f"""---
title: "Session Recap: Phase 1 and Phase 2 Execution"
type: code-recap
status: complete
created: {NOW.isoformat()}
tags:
  - pm-agent
  - code-recap
  - docflow-ai
  - phase-1
  - phase-2
  - cost-tracking
aliases:
  - "Recap 2026-04-23 Phase 1 and 2"
---
"""

BODY = """# Session Recap: Phase 1 and Phase 2 Execution

**Date**: 2026-04-23
**Scope**: Codebase review, planning doc creation, Phase 1 immediate fixes, Phase 2 cost/performance tracking
**Status**: Phases 1 and 2 complete; committed to GitHub

## What Was Accomplished

### 1. Codebase Review and Planning Doc

Reviewed the full codebase and identified misalignments between specs and implementation. Published a 6-phase improvement plan to the Obsidian vault at `01 Next Actions/Deep Work/Amazon/Projects/Agentic PM Assistant/Planning Documents/2026-04-23_codebase_improvement_plan.md`.

Key findings:
- DocFlow CLI entry point missing from `pyproject.toml` despite spec marking it complete
- 3 dependencies undeclared (`anthropic`, `markdown-it-py`, `moto`)
- Haiku pricing missing from `pricing.py` while `.env` uses Haiku
- 30+ DocFlow AI files untracked in git
- 3 tests failing at collection due to missing `moto`

### 2. Phase 1: Immediate Fixes

**`pyproject.toml`**
- Added `docflow = "docflow_ai.cli:run"` to `[project.scripts]`
- Added `anthropic>=0.30.0` to runtime dependencies
- Added `markdown-it-py>=3.0` to runtime dependencies
- Added `moto[dynamodb]>=5.0` to `[project.optional-dependencies] test`
- Added `src/docflow_ai` to hatch wheel packages

**`src/pm_agent_system/pricing.py`**
- Added Claude Haiku 4.5 pricing entries for both plain and `us.`-prefixed model IDs
- Cost estimates now return accurate values for Haiku runs (previously $0.00)

**Verification**
- `uv run docflow --help` now works
- 26 previously-broken tests (audit trail, dependency registry, infrastructure) now pass
- 106 other unit tests still pass

### 3. Phase 2: Cost and Performance Tracking

**`src/pm_agent_system/main.py`**
- Added `_print_run_metrics()` function that prints cost summary and elapsed time, and appends a structured JSONL record to `output/usage_log.jsonl`
- Wired `time.monotonic()` timing and `_print_run_metrics()` call into four commands:
  - `cmd_research`
  - `cmd_generate`
  - `cmd_brd`
  - `cmd_build_spec`

**JSONL log format**
```json
{
  "timestamp": "2026-04-23T22:30:00Z",
  "command": "research",
  "model": "anthropic.claude-haiku-4-5-20251001-v1:0",
  "input_tokens": 12500,
  "output_tokens": 3200,
  "estimated_cost_usd": 0.023,
  "elapsed_seconds": 45.2,
  "product_slug": "tech-docs-integrator"
}
```

This enables trend analysis over time without external infrastructure. Appended non-blockingly so logging failures never fail the command.

## Files Changed

| File | Change |
|------|--------|
| `pyproject.toml` | Added docflow entry point, 3 new deps, docflow_ai package |
| `src/pm_agent_system/pricing.py` | Added Haiku pricing |
| `src/pm_agent_system/main.py` | Added `_print_run_metrics()`, wired timing into 4 commands, added `time` import |
| `scripts/publish_planning_doc.py` | New: publishes planning doc to vault |
| `scripts/publish_recap.py` | New: publishes this recap to vault |

## Git Status

Committed to `main` and pushed to `origin/main` on GitHub.

Note: The uncommitted `src/docflow_ai/` package and ~30 untracked test files remain untracked per Phase 1.4 of the planning doc. That decision is deferred until the subsystem boundary question (separate package or co-located) is resolved.

## Verification

- All 106 fast unit tests pass
- All 26 previously-broken moto tests now pass
- `uv run docflow --help` works
- `uv run pm_agent_system --help` works
- Haiku cost estimation returns non-zero values

## Open Items for Next Session

Per the planning doc, remaining phases:

- **Phase 3**: Test coverage gaps (property tests, `test_html_export` hang investigation, DocFlow CLI integration tests)
- **Phase 4**: Performance enhancement (parallel BRD sub-tasks, parallel demo presets, per-stage model selection, rate limiting)
- **Phase 5**: Observability and alerts (structured logging, CloudWatch metrics, error budget tracking)
- **Phase 6**: Architecture cleanup (unified error handling, Pydantic in CLI, front matter validation, Vale backend)

## Open Questions (carried forward)

1. Should DocFlow AI be a separate package/repo, or stay co-located?
2. What's the target date for committing DocFlow AI to the remote?
3. Is the design brief agent (Agent 3) still planned, or deprioritized?
4. Should we add a CI pipeline (GitHub Actions) for automated test runs?
"""

# Write to vault
vault_path = RECAP_FOLDER / FILENAME
vault_path.write_text(FRONTMATTER + BODY, encoding="utf-8")
print(f"Recap published to vault: {vault_path}")

# Write to repo docs/recaps/ (without frontmatter, since repo recaps don't use it)
repo_path = REPO_RECAP_FOLDER / FILENAME
repo_path.write_text(BODY, encoding="utf-8")
print(f"Recap saved to repo:   {repo_path}")
