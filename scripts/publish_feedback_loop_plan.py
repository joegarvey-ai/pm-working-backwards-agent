"""Publish the Stakeholder Feedback Loop planning doc to the Obsidian vault.

Usage: uv run python scripts/publish_feedback_loop_plan.py
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
FILENAME = f"{DATE_SLUG}_stakeholder_feedback_loop_plan.md"

FRONTMATTER = f"""---
title: "Plan: Stakeholder Feedback Loop UX"
type: planning
status: active
created: {NOW.isoformat()}
tags:
  - pm-agent
  - planning
  - feedback-loop
  - revision
  - ux
  - multi-stakeholder
aliases:
  - "Feedback Loop UX Plan 2026-04-24"
---
"""

BODY_PART_1 = """# Plan: Stakeholder Feedback Loop UX

**Created**: 2026-04-24
**Status**: Active
**Scope**: Design the end-to-end experience for a PM receiving, classifying, and incorporating stakeholder feedback across PRFAQ, BRD, design brief, and build spec artifacts.
**Why now**: Phase 4 proved the pipeline can generate artifacts in ~700s of LLM time. The real bottleneck is no longer generation; it is the multi-week alignment cycle that follows. A PM running the full pipeline to get a prototype-ready build spec may need to inject updates from several stakeholders across weeks. Today's revision model handles this one artifact at a time, manually decomposed. That is an undercooked UX.

## The Core Problem

A PM's real workflow looks like this:

1. Run full pipeline against initial problem brief
2. Get PRFAQ, BRD, design brief, build spec
3. Build a prototype from the build spec (manual or via Kiro / Claude Code / Cursor / Lovable)
4. Demo the prototype in a PRFAQ review
5. Receive feedback from many sources over many days or weeks:
   - Legal (compliance, language)
   - VP (strategy, competitive positioning)
   - Eng lead (feasibility, scope)
   - Design (UX, flows)
   - Finance (cost)
   - Customer interviews (validation)
   - Prototype demo observations
6. Decide what to do with that feedback
7. Revise the relevant artifacts
8. Bump versions
9. Re-align stakeholders
10. Go to step 3 if the feedback implies a prototype rebuild

Today, step 5 through step 9 are manual and per-artifact. The PM has to:
- Collect feedback in ad-hoc ways (email, Slack, Obsidian notes)
- Manually decompose each piece of feedback: "does this affect the PRFAQ? the BRD? the build spec?"
- Run a separate revise command for each affected artifact
- Hand-merge multi-stakeholder comments into a single context string
- Track which feedback went into which version by memory or note-taking

## What We Have Today

Three per-artifact revision commands:

| Command | Scope | Feedback input |
|---------|-------|----------------|
| `revise --prfaq-path ...` | PRFAQ only | `--context-text` or `--context-path` |
| `revise-brd --brd-path ...` | BRD only | same |
| `revise-wireframes --design-brief-path ...` | Design brief only | same |

Each command:
- Prompts the PM to confirm which sections to revise
- Updates ONLY the selected sections
- Preserves every other section verbatim
- Bumps the version number
- Writes a new file (e.g., `prfaq_slug_v1.1.md`)
- Marks the old vault file as superseded via frontmatter wikilink

What works well:
- Version history is clean and traceable
- Section-level scoping prevents accidental rewrites
- The Obsidian `[o]` option reads PM edits from the vault back into the agent's context

What is missing:
- Cross-artifact coordination
- Bidirectional feedback flow (BRD feedback cannot propagate to PRFAQ)
- Multi-stakeholder batching
- Feedback history as first-class artifacts
- Impact analysis across the artifact chain
- Prototype-demo-to-artifact feedback integration

## Design Principles

Before naming features, agree on the principles that shape the UX:

1. **Feedback is a first-class artifact.** Each piece of feedback has structured metadata: source (who), target (what artifact and section), summary, raw text, timestamp, status (open, incorporated, rejected, deferred), and version it was incorporated into. The same feedback item may touch multiple artifacts.

2. **PM approves routing; the system proposes it.** The system should classify feedback by artifact impact and propose revision scopes. The PM confirms or overrides. Today the PM does the routing manually by typing into `--context-text`.

3. **Artifact chain is bidirectional in feedback flow.** If BRD feedback contradicts a PRFAQ claim, the PRFAQ is the source of truth and must be updated first. Downstream artifacts can surface inconsistencies without silently rewriting upstream claims.

4. **Human-in-the-loop stays intact.** The system proposes routing, drafts revisions, and previews impact. The PM approves every change. No auto-commits.

5. **Every change traces to a feedback item.** Version history entries should name the feedback items they incorporate, not just describe them in prose. This lets the PM (and stakeholders) ask "why did v1.3 change the press release?" and get an answer.

6. **Existing revision commands stay working.** New functionality is additive. A PM who wants the current single-artifact revise flow keeps getting it. New commands compose on top.

## Proposed Feature Set

### F1. Feedback Inbox (`output/feedback/` directory)

- PM drops or writes markdown files into `output/feedback/`
- Each file is a feedback item with YAML frontmatter:
  ```yaml
  ---
  id: fb-2026-04-24-001
  source: "VP Engineering (Sam Chen)"
  received: 2026-04-24T15:30:00Z
  status: open   # open | incorporated | rejected | deferred
  affects: []    # filled by classifier, confirmed by PM
  incorporated_in: []   # filled after revision
  ---
  
  # Feedback summary
  
  VP wants sharper differentiation vs Swimm and Readme in the PRFAQ.
  Current solution overview reads generic.
  ```
- The body is free-form markdown (stakeholder's actual comments, interview notes, etc.)

### F2. `feedback classify` subcommand

```bash
uv run pm_agent_system feedback classify
```

- Reads every `status: open` feedback item
- For each, uses the LLM to classify which artifacts it affects (PRFAQ, BRD, design brief, build spec) and which sections within each
- Updates the feedback item's `affects:` frontmatter field
- Prints a routing table:
  ```
  fb-2026-04-24-001 (VP Chen): PRFAQ (press_release, external_faqs)
  fb-2026-04-24-002 (Legal):   PRFAQ (customer_experience_narrative), BRD (risks, NFRs)
  fb-2026-04-24-003 (Eng):     BRD (risks, cost_flags), build spec (out_of_scope)
  ```
- PM can manually edit the `affects:` field if the classifier got it wrong

### F3. `feedback apply` subcommand (the "revise-all" of Option A)

```bash
uv run pm_agent_system feedback apply
# or targeted
uv run pm_agent_system feedback apply --only prfaq
uv run pm_agent_system feedback apply --item fb-2026-04-24-001
```

- Reads all `status: open` feedback items (or a filtered subset)
- Groups them by affected artifact
- For each artifact, runs the existing revise command with the aggregated feedback as context
- PM approval checkpoint per artifact (human-in-the-loop preserved)
- On approval, marks each incorporated feedback item as `status: incorporated` and adds the new version to `incorporated_in:`
- Version history entries in each artifact reference the feedback item IDs, not paraphrases

### F4. `feedback status` subcommand

```bash
uv run pm_agent_system feedback status
```

Prints a dashboard:
```
Feedback inbox:
  Open:        4
  Incorporated: 7
  Rejected:    1
  Deferred:    2

Open items:
  fb-2026-04-24-001 (VP Chen)    PRFAQ            received 2 hours ago
  fb-2026-04-24-003 (Eng Lead)   BRD, build spec  received 3 hours ago
  ...

Current artifact versions:
  PRFAQ:       v1.2 (2 open feedback items pending)
  BRD:         v1.1 (1 open feedback item pending)
  design brief: v1.0 (0 open feedback items)
  build spec:   v1.0 (1 open feedback item pending)
```

### F5. Cross-artifact impact analysis

When any single-artifact revise command runs (existing or new), after the revision completes:

- The system scans the new content for material changes to facts that appear in downstream artifacts (e.g., PRFAQ says "DynamoDB" but v1.1 now says "Aurora")
- Produces an impact report listing downstream artifacts and sections that reference the changed facts
- PM sees the impact report and decides whether to run downstream revisions now, queue them as new feedback items, or defer

### F6. Prototype demo feedback flow

- PM records stakeholder observations during a prototype demo into a feedback item with `source: "Prototype demo - 2026-04-30"`
- Feedback classification names which artifact is affected (often multiple)
- Same `feedback apply` flow handles it

### F7. Multi-stakeholder deduplication

- When classifying feedback, identify items that say substantially the same thing (e.g., VP and Legal both flag "GDPR language missing")
- Group them; treat as one logical revision with multiple sources
- Preserves attribution in version history ("Incorporated feedback from VP Chen, Legal Team")
"""

# Write to vault
vault_path = PLANNING_FOLDER / FILENAME
vault_path.write_text(FRONTMATTER + BODY_PART_1, encoding="utf-8")
print(f"Planning doc (part 1) written to vault: {vault_path}")

BODY_PART_2 = """

## Implementation Phases

Ship the feature set in three waves. Each wave is independently valuable.

### Wave 1: Feedback as first-class artifact (foundations)

Ships: F1 (inbox directory), F4 (status dashboard)

- Add `FeedbackItem` Pydantic model in `src/pm_agent_system/models/`
- Add `output/feedback/` directory as a convention
- Add `FeedbackInboxTool` or parser utility that reads/writes feedback items
- Add `feedback` subparser in `main.py` with `status` subcommand
- Tests: unit tests for model, parser, and status output

Value: A PM can start tracking feedback items today with structured metadata, even before the apply flow exists.

Estimated effort: half a day.

### Wave 2: Classification and application (the core win)

Ships: F2 (classify), F3 (apply)

- Add `feedback_classifier` agent to `agents.yaml` and `crew.py` with a narrow tool set (file_reader)
- Add classifier task to `tasks.yaml` that reads each feedback item plus the current artifact schemas and returns affected artifact/section names
- Add `feedback classify` and `feedback apply` subcommands to `main.py`
- The `apply` command composes the existing revise commands under the hood
- Update version history schema to include `feedback_items_incorporated` list
- Tests: end-to-end with fixture feedback items

Value: The full "stakeholder feedback round" UX works. PM drops feedback, runs classify, runs apply, moves on.

Estimated effort: 2-3 days. This is the bulk of the work.

### Wave 3: Cross-artifact coordination and impact

Ships: F5 (impact analysis), F6 (prototype demo feedback), F7 (dedup)

- Add a post-revision hook that scans for material changes and flags downstream impact
- Dedup logic in classifier
- No new command; features layer on top of the apply flow

Value: Fewer inconsistencies. PM gets proactive "hey, you changed DynamoDB to Aurora in the PRFAQ; the BRD and build spec mention DynamoDB in 4 places" warnings.

Estimated effort: 1-2 days.

## Data Model Sketch

```python
# src/pm_agent_system/models/feedback_item.py

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Literal

FeedbackStatus = Literal["open", "incorporated", "rejected", "deferred"]

class ArtifactImpact(BaseModel):
    artifact: Literal["prfaq", "brd", "design_brief", "build_spec"]
    sections: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    rationale: str = ""

class VersionRef(BaseModel):
    artifact: str
    version: str   # e.g. "1.2"
    incorporated_at: datetime

class FeedbackItem(BaseModel):
    id: str   # fb-YYYY-MM-DD-NNN
    source: str
    received: datetime
    status: FeedbackStatus = "open"
    affects: list[ArtifactImpact] = Field(default_factory=list)
    incorporated_in: list[VersionRef] = Field(default_factory=list)
    summary: str = ""
    raw_text: str   # free-form markdown body
```

## CLI Surface Sketch

```bash
# Status
uv run pm_agent_system feedback status
uv run pm_agent_system feedback status --artifact prfaq

# Classify (routing only, no revisions yet)
uv run pm_agent_system feedback classify
uv run pm_agent_system feedback classify --item fb-2026-04-24-001

# Apply (routes + runs revisions with PM approval)
uv run pm_agent_system feedback apply
uv run pm_agent_system feedback apply --only prfaq
uv run pm_agent_system feedback apply --only prfaq,brd
uv run pm_agent_system feedback apply --item fb-2026-04-24-001

# Mark state manually
uv run pm_agent_system feedback reject fb-2026-04-24-001 --reason "Out of scope for v1"
uv run pm_agent_system feedback defer fb-2026-04-24-001 --until "2026-Q3"
```

## What Is Out of Scope

- Real-time collaboration (Slack bots, webhook listeners). Feedback items are markdown files, period. External integrations can land future feedback items into the directory, but the system itself does not run a server.
- Automatic re-run of the full pipeline. `feedback apply` revises existing artifacts; it does not regenerate from scratch. If the PM wants a clean regeneration, they still use `full-pipeline`.
- Automatic prototype rebuild. The build spec revision produces an updated spec; the PM decides whether to hand it to Kiro/Cursor/Claude Code for a rebuild.
- Feedback items affecting the original input brief. If feedback is fundamental enough to change the problem statement, the PM should edit the input YAML and rerun `full-pipeline --fresh`.

## Open Questions

1. Where does customer-interview data live? Dovetail integration already pulls quotes at research time. Should follow-up customer interviews from post-launch discovery land as feedback items, or are they a separate concept?
2. What happens when feedback items contradict each other? Example: VP wants scope cut, Eng wants scope expanded. The classifier surfaces the conflict; what is the resolution UX?
3. Does a "rejected" feedback item still get preserved for audit, or does it get archived out of the inbox?
4. Should the classifier use the same LLM as the revision agents, or a dedicated cheaper model (Haiku only, no Sonnet fallback)?
5. How do we handle feedback that requires NEW research? Example: "VP wants market sizing for EU specifically." The classifier might propose re-running the research agent with scoped inputs instead of revising existing artifacts. Worth supporting?

## Success Criteria

A PM can demo the following flow in under 10 minutes of PM hands-on time (not counting LLM wall-clock):

1. Finish a stakeholder review meeting
2. Drop 3 feedback items into `output/feedback/` (copy-paste from meeting notes)
3. Run `feedback classify` and confirm the routing
4. Run `feedback apply`
5. Approve revisions for each affected artifact during the human-in-the-loop checkpoints
6. See updated version numbers in Obsidian, feedback items marked incorporated, and version history entries that name the feedback IDs

## Decision Log (to be filled as we build)

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-24 | Ship Wave 1 foundations first | De-risk the data model before building the expensive classifier |
| | | |

## Next Action

Review this plan with the PM (you). Once aligned, start Wave 1: Feedback model + inbox + status command. One commit, one measurable delivery.
"""

with open(vault_path, "a", encoding="utf-8") as f:
    f.write(BODY_PART_2)
print(f"Planning doc (part 2) appended to vault: {vault_path}")
