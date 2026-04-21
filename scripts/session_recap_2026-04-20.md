---
date: 2026-04-20
project: Agentic PM Assistant
session_tool: Kiro (Claude Opus 4.7)
repo: pm-working-backwards-agent
branch: main
---

# 2026-04-20 Kiro Session Recap — Dovetail Integration and Pipeline Hardening

## Session Goal

End-to-end test of the full PM agent pipeline against the tech documentation authoring and drift detection brief, with a focus on validating that the Dovetail API key pulls real Amazon developer customer research into the research brief's Customer Evidence section.

## Starting State

- Local HEAD: `0ccbcf6` (April, pre-weekend work)
- Remote main: `24fc3dd` (28 commits ahead, including Agent 3 design/wireframe work and Obsidian vault integration)
- `.env` had all required keys present: `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `DOVETAIL_API_TOKEN`, `OBSIDIAN_VAULT_PATH` pointing at the iCloud vault
- Prior research briefs from 2026-04-15 and 2026-04-16 all showed "No customer evidence available" in section 3c

## Timeline of Changes

### 1. Repo sync and dependency install

- Stashed local changes to `pyproject.toml`, `uv.lock`, and the test-on-save hook
- Fast-forwarded local main from `0ccbcf6` to `24fc3dd` (28 commits)
- Ran `uv sync` to pick up the four-agent pipeline (research to PRFAQ to design brief to BRD to build spec)
- Confirmed `design_brief_agent` now exists on disk; new CLI subcommands `wireframes`, `revise-wireframes`, `diff`, `view`, `clean`

### 2. Dovetail MCP investigation (the big finding)

**Initial smoke test:** Called Dovetail with the three action names the tool used (`search`, `get_highlights`, `get_insights`). All three returned HTTP 403 with JSON body `{"error":"unknown_tool"}`. Auth was working; tool names were wrong.

**Discovery via `tools/list`:** Dovetail's MCP server exposes 11 tools. Correct names are `search_workspace`, `get_project_highlights`, `list_project_insights`, `get_insight_content`, `get_data_content`, plus helpers for channels and project enumeration.

**First patch:** Renamed the tool's action mappings to match real Dovetail MCP tool names. Auth-plus-tool-name combination worked. `search_workspace` returned 901 hits for "developer documentation" including titles like Kepler Documentation Usability Testing Program, Vega Documentation Usability Testing Program, Fire TV Purchase Developer Experience Benchmarking, and Kepler Tech Doc Findability Study, all from the CAPE Apps & Games Research Repository (project ID `3wf8VQS4Pa99qsJzFGLS4A`).

**Second finding, titles-only problem:** `search_workspace` returns note titles, IDs, project IDs, and a generic `preview_text: " [File]"`. It does NOT return actual content. The real research lives in `get_insight_content`, which returns full markdown with direct customer quotes and quantified metrics.

**Deep test confirmed data quality:** CAPE project has 4 insights totaling ~1,591 tokens. The "Vega SDK developer challenges and tooling gaps" insight (1,208 tokens) contains exactly the evidence the pipeline needs:

- *"Vega documentation quality remains a consistent pain point for both 3P and 1P/2P developers"*
- Testing tool satisfaction at 3.2/5 among top 10 partners
- Media player problems accounting for 21% of forum posts
- Five themed findings from the VOD Insights Summary (BLR Feb 2026)

**Third patch, `deep_search` action:** Added a convenience action that chains `search_workspace` to `list_project_insights` to `get_insight_content` in a single tool call, so the agent gets actual content rather than metadata. Set as the default action. Includes `insight_content`, `data_content`, `highlights` as granular drill-in options.

**Data entries caveat:** CAPE project has 110 data entries (PDFs, videos, spreadsheets) but Dovetail's MCP API serves them as stub links, not content. Only insights have extractable text. Platform limitation, not ours.

### 3. Token limit bump

Research agent was configured at `_DEFAULT_MAX_TOKENS = 8192` while all other agents used `_LARGE_MAX_TOKENS = 16384`. The research output contains competitive landscape (4 competitors with full G2/Capterra review data, pros, cons, pricing), which dominates the token budget. `customer_evidence` sits after `competitors` in the Pydantic schema, so truncation consistently hit that field. Bumped the research agent to 16384.

### 4. Mandatory tool call prompt changes (REVERTED)

After fixing the tool and bumping tokens, the agent still wasn't calling Dovetail. Added explicit "You MUST call the dovetail_research tool" language to both the research agent backstory and the research task prompt. **This broke the pipeline.** Three consecutive Pydantic validation failures on the agent's first output attempt:

- `competitors: List should have at least 3 items after validation, not 0` (twice)
- `market_sizing: Input should be a valid dictionary... input_type=str, input_value='<parameter name="summary...'`

The `<parameter name="summary...>` token leaking into the output revealed that Anthropic's XML-flavored tool-call syntax was bleeding into the JSON response. The mandatory-tool-call prompt language, placed near the output schema instructions, confused the model's format selection. Reverted the commit.

### 5. Per-call logging instrumentation

Added a file logger to the Dovetail tool that writes one JSON line per invocation to `output/dovetail_calls.log` (invocation event, response event, error events). Exception-wrapped so it never breaks the tool. This lets future debugging sessions verify whether the agent actually called Dovetail during a run.

## Commits Pushed to origin/main

| Hash | Commit | Status |
|------|--------|--------|
| `fb86bad` | fix: Dovetail MCP tool integration and research agent token limit | Kept |
| `ddf9938` | fix: make Dovetail deep_search a mandatory tool call in research agent | Reverted |
| `d60708d` | diag: log every Dovetail tool invocation to output/dovetail_calls.log | Kept |
| `6b4ff1c` | Revert "fix: make Dovetail deep_search a mandatory tool call..." | Applied to main |

Also pushed the upstream pull (`24fc3dd`) that brought in the design agent and vault integration.

## What Worked

- **Dovetail MCP auSth and `search_workspace` endpoint.** Real data flows cleanly. Token bomb concerns were unfounded (deep_search returns ~1,700 tokens per call, vs 200K context window).
- **The `deep_search` chained action.** Verified end-to-end returning 5,300+ chars of real Vega/CAPE insight content including the key customer quotes the brief needs.
- **`test-on-save` hook disabled.** That was creating Kiro chat tab noise. Already `enabled: false` upstream, confirmed committed.
- **Rollback via git revert.** Clean, preserves useful commits, single-file change.

## What Failed

- **Assumption that renaming MCP tool names alone would fix Dovetail.** It was three stacked bugs, not one.
  1. Wrong tool names (403 errors)
  2. Research agent token limit too low (truncation)
  3. `search_workspace` returns metadata only, not content (needed deep_search chain)
- **Schema field reordering as a fix.** Moving `customer_evidence` above `competitors` in the Pydantic schema was proposed to dodge truncation. I called out in the session that this just picks a different field to fail, not a root-cause fix. Reverted before committing.
- **Mandatory tool-call prompt language.** Added "You MUST call the dovetail_research tool" to both the agent backstory and the task prompt. Caused the model to emit malformed output with XML tool-call syntax leaking into JSON fields. Three validation retries, no brief generated.
- **The terminal `uv run` path.** External PowerShell terminal couldn't resolve `uv run pm_agent_system` even though the exe existed in `.venv/Scripts/`. Workaround: call the exe directly.

## Key Learnings

1. **CrewAI + Anthropic has a tool-use / output-format interaction problem.** When tool-use instructions are prominent in the prompt, the model sometimes emits XML tool-call syntax inside structured JSON output fields. Subtle: works for smaller tasks, fails when the task is large and multi-tool.
2. **Dovetail's MCP server is best for published insights, not raw data.** The 11 tools cover insights well (full markdown content), but data entries (transcripts, surveys, videos) return stub links. This has implications for how much we can pull from any given workspace without a separate content-retrieval pathway.
3. **`deep_search` as a convenience action is the right pattern.** Chaining search to list insights to fetch content server-side in the tool (not in the agent loop) is cleaner than forcing the agent to make 3-5 sequential MCP calls. Less prompt complexity, smaller token budget per call, more predictable output.
4. **Research task is overloaded.** The current research_task asks one agent to do ~10 tool calls (Tavily 4-5, CompetitiveIntel 3-5, Dovetail 2, FileReader 1-2) plus produce a 10-field Pydantic object with inline citations, style rules, and banned-word filtering. This is why the agent quietly drops Dovetail under load: not defiance, overload. This is the root cause that needs an architectural fix, not another prompt tweak.
5. **LLM output truncation warnings are unreliable signals.** The `find_defaulted_empty_fields` warning banner fires whenever a defaulted field is empty, regardless of whether the output was actually truncated. Can't use that banner to diagnose truncation specifically. Real diagnosis needs per-call logging.
6. **Kiro pre-tool-use hooks add friction on every write.** Every `fsWrite`, `strReplace`, and `fsAppend` triggered a `protect-secrets` and `style-guard` check, requiring the agent to verify intent before execution. The hooks never blocked a legitimate change, but they added conversational overhead on every single file edit.

## Current State at Session End

- Local HEAD and origin/main synced at `6b4ff1c`
- Pipeline runs but still produces "No customer evidence available" when the research agent skips Dovetail under load
- Dovetail tool itself works correctly when called directly; issue is in the agent's tool-calling behavior, not the tool
- Logging in place to diagnose future runs
- Architecture refactor queued up for next session (see planning doc)

## Links

- Commit history: `git log --oneline` on main
- Dovetail CAPE project ID for reference: `3wf8VQS4Pa99qsJzFGLS4A`
- Related: [[2026-04-21 Planning - Research Task Architecture Decision]]
