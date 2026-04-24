# Session Recap: Wave 1 Feedback Inbox Foundations

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
