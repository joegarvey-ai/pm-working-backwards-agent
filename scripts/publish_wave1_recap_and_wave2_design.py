"""Publish the Wave 1 recap and Wave 2 design doc to the Obsidian vault.

Usage: uv run python scripts/publish_wave1_recap_and_wave2_design.py
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

REPO_RECAP_FOLDER = Path(__file__).parent.parent / "docs" / "recaps"
REPO_RECAP_FOLDER.mkdir(parents=True, exist_ok=True)

NOW = datetime.now(timezone.utc)
DATE_SLUG = NOW.strftime("%Y-%m-%d")

# ---------- RECAP ----------

RECAP_FILENAME = f"{DATE_SLUG}_wave1_feedback_inbox_foundations.md"
RECAP_FRONTMATTER = f"""---
title: "Session Recap: Wave 1 Feedback Inbox Foundations"
type: code-recap
status: complete
created: {NOW.isoformat()}
tags:
  - pm-agent
  - code-recap
  - feedback-loop
  - wave-1
aliases:
  - "Recap 2026-04-24 Wave 1"
---
"""
RECAP_BODY = """# Session Recap: Wave 1 Feedback Inbox Foundations

**Date**: 2026-04-24
**Scope**: Wave 1 of the stakeholder feedback loop UX
**Status**: Shipped, tested, committed

## Headline

The PM agent system now has a structured place for stakeholder feedback. A PM drops markdown files into `output/feedback/` with YAML frontmatter, and `uv run pm_agent_system feedback status` prints a dashboard. Every piece of feedback has an ID, source attribution, status lifecycle, and fields for classifier outputs that land in Wave 2. Twenty-two unit tests cover the model, parser, writer, and CLI.

## What We Did

### Decision: Feedback is a first-class artifact

Prior to Wave 1, stakeholder feedback lived as ad-hoc context strings passed to `--context-text` or `--context-path`. No tracking, no versioning, no cross-artifact coordination. Wave 1 flips this: each feedback item is a file on disk with structured metadata, classified by affected artifact (once Wave 2 classifier lands), with a lifecycle (open, incorporated, rejected, deferred) and audit trail.

### Answered open questions from the planning doc

Before writing code, we resolved the 5 open questions from the plan:

1. **Customer interviews as feedback items**: Yes. The PM drops interview notes into the inbox. The classifier routes them like any other feedback, typically affecting research_brief first and triggering downstream revisions.
2. **Conflict resolution UX**: Contradiction flag. The system surfaces the conflict and the PM decides. No auto-resolution.
3. **Rejected items**: Kept in inbox with `status: rejected` for audit and future reference. No archive.
4. **Classifier LLM**: Same as revision agents (Haiku via `_llm()` default).
5. **Research gaps**: The classifier can propose scoped research re-runs against Tavily, CompetitiveIntel, or Dovetail when a feedback item identifies a gap those tools could fill.

These answers were appended to the planning doc so future sessions can find them.

### Shipped artifacts

**`src/pm_agent_system/models/feedback_item.py`**
- `FeedbackItem` Pydantic model with 12 fields covering identity, lifecycle, routing, application, and metadata
- `ArtifactImpact` sub-model for classifier routing output (artifact + sections + confidence + rationale)
- `ResearchGap` sub-model for "this feedback needs new research" output (tool + query + rationale)
- `ContradictionFlag` sub-model for "this feedback conflicts with X" output
- `VersionRef` sub-model for "incorporated into artifact Y version Z at timestamp T"
- `frontmatter_dict()` method serializes the item to YAML frontmatter, excluding the markdown body

**`src/pm_agent_system/feedback_inbox.py`**
- `parse_feedback_file(path)` reads a markdown file, extracts YAML frontmatter, parses into FeedbackItem. Handles missing file, missing frontmatter, bad YAML, and validation failure gracefully (returns None, logs warning, never raises).
- `load_all_feedback()` reads every `*.md` in the inbox, returns validated items sorted by received timestamp.
- `load_feedback_by_id(fb_id)` reads a single item by ID.
- `write_feedback_item(item)` serializes back to markdown with frontmatter.
- `next_feedback_id()` generates the next `fb-YYYY-MM-DD-NNN` ID, padded, incrementing past existing items for today.
- Auto-fills `summary` from the first non-empty body line if the frontmatter omits it.

**`src/pm_agent_system/main.py`**
- New `feedback` subparser with `status` subcommand
- `--show {open,incorporated,rejected,deferred,all}` filter (default: open)
- `--artifact {research_brief,prfaq,design_brief,brd,build_spec}` filter
- Empty-state message guides the PM on how to create the first feedback item
- Prints counts per status, then visible items with source, affects, summary, contradictions, research gap count, and lifecycle metadata

**`tests/test_feedback_inbox.py`**
- 22 tests across 5 classes
- Model round-trip, defaults, each sub-model
- Parser: 5 failure modes (missing file, no frontmatter, bad YAML, missing required fields, incomplete data)
- Write: overwrite and round-trip
- Load all: empty, sorted, skips invalid files
- ID generation: first-of-day, increment past existing, ignores other days
- Inbox dir: creation, OUTPUT_DIR env var respected

All 22 tests pass. Broader test sweep (54 tests across smoke, pricing, input parser, vault checkpoint, feedback) also passes.

## Files Changed

| File | Change |
|------|--------|
| `src/pm_agent_system/models/feedback_item.py` | New: Pydantic models |
| `src/pm_agent_system/models/__init__.py` | Re-export feedback models |
| `src/pm_agent_system/feedback_inbox.py` | New: file I/O and ID generation |
| `src/pm_agent_system/main.py` | New: `feedback status` command |
| `tests/test_feedback_inbox.py` | New: 22 unit tests |
| Obsidian planning doc | Appended answered questions + revised Wave 2 scope |

## Commits

```
cd751ad feat(feedback): Wave 1 - feedback inbox foundations
cc55338 docs: add stakeholder feedback loop planning script
```

Both pushed to `origin/main`.

## What We Learned

1. **The security hook saved us from seeding sample data into `output/`.** I started to write a demo feedback file into `output/feedback/` to show the dashboard working; the pre-tool-use hook correctly blocked it because `output/` is reserved for the PM's real pipeline outputs, not agent-generated demo content. This is exactly the protection the hook exists for.
2. **`tmp_path` + `monkeypatch` fixture pattern works cleanly for directory-scoped utilities.** Every feedback test runs against an isolated temp inbox. No cross-test pollution.
3. **Graceful-failure parsing matters.** The parser returns None on five distinct failure modes (missing, bad YAML, missing fields, not a mapping, validation error), with targeted log messages. A PM can drop a malformed feedback file and the dashboard keeps working; the bad file just does not appear.

## How to Use Today

```bash
# See the empty inbox and instructions for creating your first item
uv run pm_agent_system feedback status

# Drop a feedback file at output/feedback/fb-YYYY-MM-DD-NNN.md:
# ---
# id: fb-2026-04-24-001
# source: "VP Engineering"
# received: "2026-04-24T15:30:00Z"
# status: open
# ---
# # Feedback body
# Free-form markdown.

# Re-run status to see it
uv run pm_agent_system feedback status

# Filter
uv run pm_agent_system feedback status --artifact prfaq
uv run pm_agent_system feedback status --show all
uv run pm_agent_system feedback status --show rejected
```

## What's Next: Wave 2 Design

Wave 1 shipped the plumbing. Wave 2 adds the classifier agent that reads each open feedback item, looks at current artifact content, and populates the `affects`, `research_gaps`, and `contradictions` fields. Then an `apply` command that groups feedback by artifact and runs the existing revise flows with the aggregated context.

A separate Wave 2 design doc lands alongside this recap. Major open areas for design: the classifier's prompt shape, how the apply flow coordinates multiple revise commands in sequence, whether the `revise-research` command (new) follows the same pattern as the existing three revise commands, and how contradictions block the apply flow until the PM explicitly resolves them.

## Open Items (Carried Forward)

- Wave 2 design doc (see `2026-04-24_wave2_design_classifier_and_apply.md`)
- `feedback classify` and `feedback apply` subcommands
- `revise-research` command (currently missing)
- Classifier prompt engineering
- End-to-end integration test with fixture feedback items
- Wave 3 (impact analysis, dedup, prototype demo flow) remains on the board but not yet designed
"""

vault_recap = RECAP_FOLDER / RECAP_FILENAME
vault_recap.write_text(RECAP_FRONTMATTER + RECAP_BODY, encoding="utf-8")
print(f"Wave 1 recap published to vault: {vault_recap}")

repo_recap = REPO_RECAP_FOLDER / RECAP_FILENAME
repo_recap.write_text(RECAP_BODY, encoding="utf-8")
print(f"Wave 1 recap saved to repo:    {repo_recap}")


# ---------- WAVE 2 DESIGN DOC ----------

DESIGN_FILENAME = f"{DATE_SLUG}_wave2_design_classifier_and_apply.md"
DESIGN_FRONTMATTER = f"""---
title: "Design: Wave 2 Feedback Classifier and Apply"
type: design
status: draft
created: {NOW.isoformat()}
tags:
  - pm-agent
  - design
  - feedback-loop
  - wave-2
  - classifier
aliases:
  - "Wave 2 Design 2026-04-24"
---
"""
DESIGN_BODY = """# Design: Wave 2 Feedback Classifier and Apply

**Status**: Draft, pending PM review
**Created**: 2026-04-24
**Depends on**: Wave 1 foundations (shipped in commit cd751ad)

## Purpose

Wave 2 turns the feedback inbox from a dashboard into a workflow. A PM who has accumulated several stakeholder feedback items should be able to:

1. Run one command to classify all open feedback (which artifacts does each item affect, are there conflicts, are there research gaps)
2. Review the classifier's routing in Obsidian or the terminal
3. Run one command to apply the feedback across affected artifacts
4. Get one human-in-the-loop checkpoint per affected artifact (not per feedback item)
5. See feedback items automatically marked as incorporated with version references

## Non-Goals

- Real-time feedback collection (Slack bots, API listeners). Feedback items stay as markdown files.
- Fully automated revision. PM approves every artifact revision.
- Resolving contradictions automatically. Contradictions block apply until the PM manually marks one side rejected or deferred.
- Cross-session memory. Each classify run operates on current inbox state; prior classifications are not re-run unless an item goes from `incorporated` back to `open` (which the PM would have to do manually).

## Commands to Ship

### `feedback classify`

```bash
uv run pm_agent_system feedback classify
uv run pm_agent_system feedback classify --item fb-2026-04-24-001
uv run pm_agent_system feedback classify --rerun   # reclassify already-classified items
```

**What it does**:
1. Loads every `status: open` feedback item from the inbox
2. Filters out items that already have non-empty `affects` unless `--rerun` is passed
3. Loads the current state of each artifact (latest versioned file from `output/` or vault)
4. Runs the classifier agent on each feedback item with the item body + summaries of each current artifact
5. Classifier returns: affected artifacts/sections, research gaps, contradictions
6. Writes results back to each item's YAML frontmatter
7. Prints a routing table to the terminal

**Classifier inputs per feedback item**:
- The feedback item body and summary
- A short summary (first 500 tokens) of each current artifact's content
- The other open feedback items' summaries (for contradiction detection)
- A schema reference listing valid artifact names and section names per artifact

**Classifier outputs per feedback item** (JSON matching existing sub-models):
- `affects`: list of `ArtifactImpact`
- `research_gaps`: list of `ResearchGap`
- `contradictions`: list of `ContradictionFlag`

### `feedback apply`

```bash
uv run pm_agent_system feedback apply
uv run pm_agent_system feedback apply --only prfaq
uv run pm_agent_system feedback apply --only prfaq,brd
uv run pm_agent_system feedback apply --item fb-2026-04-24-001
uv run pm_agent_system feedback apply --dry-run   # print the plan without executing
```

**What it does**:
1. Loads every `status: open` feedback item that has been classified (`affects` is non-empty)
2. Refuses to proceed if any item has `contradictions` unless `--ignore-contradictions` is passed. Prints which items conflict and directs the PM to resolve first.
3. Groups items by affected artifact
4. Computes execution order: research_brief -> prfaq -> design_brief -> brd -> build_spec (upstream to downstream)
5. For each affected artifact, in order:
   a. Aggregates the relevant feedback items' bodies into a single context blob
   b. Runs the appropriate revise command (existing `revise`, `revise-brd`, `revise-wireframes`, or new `revise-research`)
   c. Pauses at the existing human_input checkpoint so PM can approve
   d. On approval, marks every contributing feedback item as `status: incorporated` with a new `VersionRef` for the artifact+version
6. If a revision creates a material change to an upstream artifact (e.g. PRFAQ fact flipped), optionally flags downstream artifacts for follow-up review (Wave 3 feature; in Wave 2 this is a console warning only)

### `revise-research` (new)

A research brief is currently unrevisable. Wave 2 adds this command to support the "customer interviews as feedback" flow (answered question 1 from the plan).

```bash
uv run pm_agent_system revise-research --research-path output/research_brief_slug_v1.0.md --context-text "..."
uv run pm_agent_system revise-research --research-path ... --context-path output/feedback/fb-2026-04-24-001.md
```

Mirrors the existing `revise` command pattern exactly: reads the current research brief, asks which sections to revise, updates only those sections, bumps version, writes a new file.

### Manual state commands

```bash
uv run pm_agent_system feedback reject fb-2026-04-24-001 --reason "Out of scope for v1"
uv run pm_agent_system feedback defer fb-2026-04-24-001 --until "2026-Q3"
uv run pm_agent_system feedback reopen fb-2026-04-24-001   # if PM changed their mind
```

Each command sets the `status` field, populates `rejection_reason` or `defer_until` if applicable, and writes the item back.

## Classifier Design

### Agent configuration

Add to `agents.yaml`:

```yaml
feedback_classifier_agent:
  role: >
    Stakeholder Feedback Routing Specialist
  goal: >
    Classify stakeholder feedback items by affected artifact and section,
    identify conflicts with other feedback or with existing artifact
    content, and surface research gaps that existing tools could fill.
  backstory: >
    You are a PM ops specialist whose job is to route incoming feedback
    to the right artifact for revision. You know the artifact chain
    (research brief -> PRFAQ -> design brief -> BRD -> build spec) and
    the sections within each. You never revise content yourself. You
    only classify.
    ...
```

Narrow tool set: `file_reader` only (to read feedback files and artifact summaries). No Tavily, no Dovetail, no style guide loader.

### Task configuration

Add to `tasks.yaml`:

```yaml
feedback_classify_task:
  description: >
    Classify a stakeholder feedback item by affected artifact and section.
    
    ## Inputs
    
    **Feedback item body:** {feedback_body}
    **Feedback item source:** {feedback_source}
    
    **Current artifact summaries:**
    
    Research brief: {research_brief_summary}
    PRFAQ: {prfaq_summary}
    Design brief: {design_brief_summary}
    BRD: {brd_summary}
    Build spec: {build_spec_summary}
    
    **Other open feedback item summaries:**
    {other_feedback_summaries}
    
    ## Process
    
    1. Read the feedback body. Identify the topic.
    2. For each artifact, decide whether the feedback's topic affects
       content in that artifact. If yes, name the affected sections.
    3. Check whether the feedback states anything that contradicts the
       current artifact content or another open feedback item.
    4. Check whether the feedback asks for data that one of the three
       research tools (Tavily, CompetitiveIntel, Dovetail) could fill.
    5. Return a FeedbackClassification JSON with affects, research_gaps,
       and contradictions fields.
    
    ## Rules
    
    - Only name sections that actually exist in the artifact schema.
    - Confidence below 0.5 means do not flag the artifact.
    - Flag contradictions conservatively. Only flag if the contradiction
      is unambiguous.
```

### New Pydantic output

```python
# src/pm_agent_system/models/feedback_classification.py
class FeedbackClassification(BaseModel):
    affects: list[ArtifactImpact] = Field(default_factory=list)
    research_gaps: list[ResearchGap] = Field(default_factory=list)
    contradictions: list[ContradictionFlag] = Field(default_factory=list)
```

This is the task's output_pydantic. After the task returns, the caller copies these fields back onto the `FeedbackItem` and writes it to disk.

### Artifact summary generation

The classifier needs short summaries of each artifact (500 tokens max). Options:
- **Option A**: Generate summaries lazily by reading the first N lines of each artifact file
- **Option B**: Store summaries in frontmatter each time an artifact is written (requires updating the render/save functions)
- **Option C**: Run a one-shot summarizer LLM call per artifact the first time classify runs, cache in `output/.classifier_cache/`

Recommendation: **Option A for Wave 2**, Option C if quality falls short. Option A is zero-LLM-cost and works well if artifact files have clean section headers.

## Apply Flow Details

### Execution order

The PM agent pipeline chain is strict: research_brief -> prfaq -> design_brief -> brd -> build_spec. The apply flow revises upstream artifacts first so downstream revisions see the updated upstream.

Example: if feedback affects both PRFAQ and BRD, the PRFAQ revise runs first. The BRD revise then sees the revised PRFAQ v1.1 on disk (because `revise-brd` reads from disk) and incorporates the updated content naturally.

### Aggregating feedback per artifact

For each artifact, collect all feedback items that list that artifact in `affects`. Build a single context string:

```
# Feedback to incorporate

## From fb-2026-04-24-001 (VP Engineering (Sam Chen))
Summary: Ask for tighter differentiation vs Swimm and Readme
Affected sections: press_release, external_faqs

[feedback body]

---

## From fb-2026-04-24-002 (Legal Team)
Summary: Add explicit GDPR / SOC2 language to the CX narrative
Affected sections: customer_experience_narrative

[feedback body]
```

Pass this as `--context-text` to the underlying revise command.

### Section scoping

The existing revise commands ask the PM "which sections to revise" at a checkpoint. In the apply flow, the aggregated context already names affected sections in each feedback block. The revise task's human_input prompt then lets the PM confirm or adjust.

### Marking items as incorporated

After each artifact's revise command completes and the PM approves, the apply flow:
1. Reads the new artifact version from the output path
2. Creates a `VersionRef(artifact=..., version=..., incorporated_at=now)`
3. For each feedback item that contributed to this artifact's revision:
   - Appends the VersionRef to `incorporated_in`
   - Sets `status` to `incorporated` only if ALL of its `affects` entries are now represented in `incorporated_in`
   - Otherwise stays `open` (feedback affecting multiple artifacts stays open until all artifacts are revised)
4. Writes the updated feedback item back to disk

This handles the cross-artifact feedback case correctly. An item that affects PRFAQ and BRD becomes incorporated only after both revisions land.

### Contradiction handling

If `feedback classify` populated any item's `contradictions` field, `feedback apply` refuses to proceed unless the PM either:
- Resolves by marking one of the contradicting items as rejected
- Runs `feedback apply --ignore-contradictions` explicitly

The refusal message lists each contradiction with the item IDs involved and a short summary.

### Research gaps handling

If a feedback item has `research_gaps` and no `affects` (pure gap), the apply flow asks the PM: "this feedback identifies a research gap in {tool}. Do you want to re-run the research agent with this scoped query?"

If yes, `feedback apply` invokes the relevant research agent (external_research_agent, customer_evidence_agent, or both via a scoped research command) with the feedback's scoped query as context. The result produces a research supplement markdown file in `output/research_supplements/`.

The supplement is then treated as a new feedback item on research_brief with `source: "research_supplement_<original_feedback_id>"` and auto-classified to affect research_brief.

## New Models

```python
# src/pm_agent_system/models/feedback_classification.py

from pydantic import BaseModel, Field
from pm_agent_system.models.feedback_item import (
    ArtifactImpact,
    ResearchGap,
    ContradictionFlag,
)


class FeedbackClassification(BaseModel):
    \"\"\"Classifier output: the routing decisions for a single feedback item.\"\"\"
    
    affects: list[ArtifactImpact] = Field(default_factory=list)
    research_gaps: list[ResearchGap] = Field(default_factory=list)
    contradictions: list[ContradictionFlag] = Field(default_factory=list)
```

## CLI Surface Summary

After Wave 2 ships, the full feedback CLI is:

```bash
# Foundations (Wave 1 - shipped)
feedback status [--show {open,incorporated,rejected,deferred,all}] [--artifact <name>]

# Classification (Wave 2)
feedback classify [--item <id>] [--rerun]

# Application (Wave 2)
feedback apply [--only <artifacts>] [--item <id>] [--dry-run] [--ignore-contradictions]

# Manual state (Wave 2)
feedback reject <id> --reason <text>
feedback defer <id> --until <date>
feedback reopen <id>
```

## Implementation Order

1. **Day 1: Classifier foundations**
   - `FeedbackClassification` output model
   - `feedback_classifier_agent` in agents.yaml
   - `feedback_classify_task` in tasks.yaml
   - Classifier agent constructor in crew.py
   - Classifier crew (single-task)
   - Artifact summary utility (read first N lines with section headers)
   - `feedback classify` subcommand in main.py
   - Unit tests (mock crew response; verify item frontmatter is updated correctly)

2. **Day 2: Apply flow (no new research)**
   - `revise-research` command (mirror existing revise patterns)
   - Context aggregation utility (feedback items to context string)
   - `feedback apply` subcommand (orchestrates existing revise commands in dependency order)
   - Incorporated/VersionRef bookkeeping
   - Contradiction-blocking logic
   - Unit tests (mock revise commands; verify state transitions)

3. **Day 3: Research gaps + polish**
   - Research gap handling in apply (scoped research re-run)
   - Research supplement markdown output
   - `feedback reject`, `feedback defer`, `feedback reopen` subcommands
   - Integration test: fixture feedback items -> classify -> apply -> verify artifact versions and feedback statuses

## Open Questions for PM Review

1. Should the classifier run against feedback items individually (one LLM call per item) or batch multiple items per call? Batching is cheaper but reduces isolation. Recommendation: one-per-item for Wave 2 to keep classifier prompts focused.

2. When apply finishes and a feedback item was incorporated, should the item file move to an `output/feedback/incorporated/` subdirectory or stay in place with status flipped? Recommendation: stay in place. The status field is the source of truth; subdirectories add complexity.

3. For the research gap flow: the classifier says "Tavily can fill this gap." The apply flow then triggers a Tavily search. Should that Tavily call go through the existing external_research_task (which produces a full ExternalResearchOutput) or a new lightweight `tavily_supplement_task` that returns just the relevant data points? Recommendation: new lightweight task, reused inside the apply flow only.

4. Do we want a `--verbose` flag on apply that prints the aggregated context before running the revise command? Useful for debugging. Recommendation: yes.

5. If a feedback item affects multiple artifacts and the PM approves the PRFAQ revision but rejects the BRD revision, what happens to the feedback item's status? Recommendation: `incorporated_in` tracks the PRFAQ VersionRef; status stays `open` because the BRD side was not incorporated. PM can then choose to reject, defer, or re-queue for a different BRD revision.

## Success Criteria

A PM can complete the following in under 10 minutes of hands-on time (not counting LLM wall clock for the revisions):

1. Drop 3 feedback items into `output/feedback/` (2 affect PRFAQ, 1 affects BRD + build spec)
2. Run `feedback classify`; confirm routing is correct (takes ~15-30s of LLM time)
3. Run `feedback apply`; approve each artifact revision at its human checkpoint
4. See all 3 feedback items marked `incorporated` with correct VersionRefs
5. Run `feedback status`; see 0 open items and the 3 marked incorporated

## Next Action

Review this design doc. Once aligned, start Day 1: classifier foundations.
"""

vault_design = PLANNING_FOLDER / DESIGN_FILENAME
vault_design.write_text(DESIGN_FRONTMATTER + DESIGN_BODY, encoding="utf-8")
print(f"Wave 2 design doc published to vault: {vault_design}")
