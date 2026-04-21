---
date: 2026-04-21
session_time: PM session (morning through afternoon)
project: Agentic PM Assistant
session_tool: Kiro (Claude Opus 4.6 and 4.7)
repo: pm-working-backwards-agent
branch: main
status: milestone achieved
---

# 2026-04-21 PM Session Recap

## Milestone

For the first time, the research brief contains real Amazon developer customer research from Dovetail. Seven direct quotes from the Vega SDK developer challenges insight, layered with competitive analysis and the PM's business context. The brief at `output/research_brief_20260421_123208.md` is stakeholder-ready.

## Changes Made Today

### 1. AWS Bedrock Integration (crew.py, pricing.py, .env.example)

Added `LLM_PROVIDER` env var switch. When set to `bedrock`, all LLM calls route through AWS Bedrock using `BedrockCompletion` with `AWS_BEARER_TOKEN_BEDROCK` auth. Auto-prepends `us.` to model IDs for cross-region inference profiles. Pricing module updated for Bedrock model IDs.

Commit: `d63e4d6`

### 2. CrewAI Upgrade 1.13.0 to 1.14.2 (pyproject.toml)

CrewAI 1.13.0 had a bug in BedrockCompletion that passed empty dicts as tool arguments instead of the LLM's actual args. Every Dovetail call received `query=""`. Diagnosed by: (a) running Stage 1 test showing 52 failed tool calls, (b) hitting Bedrock Converse API directly with boto3 proving the model returns correct args, (c) tracing through CrewAI source confirming the bug was in response processing. Upgrade to 1.14.2 fixed it.

Also changed pyproject from `==1.13.0` to `>=1.14.0,<2.0.0` and added `bedrock` extra.

Commit: `99af12e`

### 3. DovetailSearchInput Schema Hardening (dovetail_research.py)

Changed `query` field from `default=""` to required (`...`). Defense-in-depth so future CrewAI regressions fail fast with "Field required" instead of silently passing empty strings.

Commit: `99af12e`

### 4. Stage 2: Three-Task Research Split (tasks.yaml, crew.py, new models)

Replaced the monolithic `research_task` with three sequential tasks:

1. `external_research_task` (Tavily + CompetitiveIntel) produces `ExternalResearchOutput`
2. `customer_evidence_task` (Dovetail only) produces `CustomerEvidenceOutput`
3. `research_synthesis_task` (no tools) merges both into final `ResearchOutput`

New models in `models/research_intermediate.py`. Original `research_task` kept as fallback.

This is the architectural fix for the root cause: the agent was skipping Dovetail when it was one of eight tools competing for attention in a single task. By giving Dovetail its own task with no competing tools, skipping it becomes impossible.

Commit: `4500142`

## What Broke and How We Fixed It

### Bedrock model ID format

AWS console shows `anthropic.claude-sonnet-4-6` but on-demand invocation requires `us.anthropic.claude-sonnet-4-6`. Added auto-prefix logic in crew.py.

### CrewAI 1.13.0 tool-arg serialization bug

The biggest time sink. 52 failed tool calls with empty args. Root cause was in CrewAI's BedrockCompletion response processing, not in our code or the Bedrock API. Fix: version bump to 1.14.2.

### Anthropic API credits exhausted

Personal API key ran out of credits. Forced us to fix Bedrock rather than work around it. Correct outcome.

### Mandatory tool-call prompt language (from 4/20, reverted)

Adding "You MUST call dovetail_research" to the prompt caused XML tool-call syntax to leak into JSON output fields. Architectural separation (Stage 2) is cleaner than prompt coercion.

## What We Tried That Didn't Work

- LiteLLM fallback path: CrewAI routes `bedrock/` models to the same native provider, so this would have hit the same bug
- Schema field reordering (from 4/20): moving `customer_evidence` above `competitors` in the Pydantic schema just picks a different field to truncate
- Anthropic direct as fallback: blocked by billing

## Full Pipeline Run Status

Research, PRFAQ, design brief, and BRD all completed successfully. Build spec generation failed with `CodingPromptOutput ... Invalid JSON: EOF while parsing a list at line 295`. The BRD agent hit the 16,384 output token ceiling mid-JSON while generating the `formatted_spec` field. Same class of issue as the research truncation, same fix pattern available (split into two sub-tasks).

## Research Brief Quality Assessment

The brief is legitimately good by PM standards. Strengths:
- Seven direct Dovetail quotes with insight name, project, date, and theme attribution
- Five competitors with G2/Capterra/TrustRadius review data, pros/cons from real users, pricing
- Executive summary weaves internal data, external market sizing, competitor gaps, and Dovetail evidence
- Pain points ranked by severity with 3-6 evidence sources each
- Honest gap flagging: "technical writers have no representation in the Dovetail workspace"

Weaknesses worth addressing in prompt tuning:
- Market sizing lists four different numbers without reconciling them
- Some review ratings show "Not publicly confirmed" or "No data found"
- All seven Dovetail quotes come from one insight (CAPE project has limited published content)

## Commits Pushed Today

| Hash | Summary |
|------|---------|
| `6b4ff1c` | Revert mandatory tool call prompt changes |
| `d63e4d6` | feat: add AWS Bedrock support via LLM_PROVIDER env var |
| `99af12e` | fix: upgrade CrewAI to 1.14.2 to fix Bedrock tool-arg bug |
| `4500142` | feat: Stage 2 split research into three sequential sub-tasks |

## Next Steps

1. Fix build spec token overflow (split into two sub-tasks or raise token ceiling)
2. Run `build-spec` standalone against the saved BRD to get the build spec without re-running the full pipeline
3. Expand Dovetail project reach (target DxD Research Repository and others by ID)
4. Write tests for the three-task split
5. Decide whether to keep or remove the original monolithic `research_task`

## Links

- [[2026-04-20 Kiro Session Recap - Dovetail Integration]]
- [[2026-04-21 Kiro Session Recap - Bedrock and Stage 1]]
- [[2026-04-21 Planning - Research Task Architecture Decision]]
