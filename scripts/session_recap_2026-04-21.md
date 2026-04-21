---
date: 2026-04-21
project: Agentic PM Assistant
session_tool: Kiro (Claude Opus 4.6)
repo: pm-working-backwards-agent
branch: main
---

# 2026-04-21 Kiro Session Recap — Bedrock Migration and Stage 1 Dovetail Validation

## Session Goal

Migrate the PM agent pipeline from personal Anthropic API key to AWS Bedrock, then validate that the isolated Dovetail-only CrewAI test (Stage 1) produces real Amazon developer customer quotes through Bedrock.

## What We Built

### AWS Bedrock LLM Provider Integration

Added a configurable LLM provider switch in `crew.py` controlled by `LLM_PROVIDER` env var:
- `LLM_PROVIDER=bedrock` routes all LLM calls through AWS Bedrock using `BedrockCompletion`
- `LLM_PROVIDER=anthropic` (or unset) uses the direct Anthropic API
- Auto-prepends `us.` to `BEDROCK_MODEL_ID` if missing, so the cross-region inference profile works for Claude Sonnet 4.6
- Updated `pricing.py` with Bedrock model IDs so cost summaries still work
- Updated `.env.example` with full Bedrock configuration documentation

### Stage 1 Isolated Dovetail Test

Built `scripts/stage1_dovetail_isolated.py`: a minimal CrewAI crew with one agent, one tool (Dovetail), one task, and one Pydantic output schema (`CustomerEvidenceOutput`). Designed to validate whether a single-tool agent reliably calls Dovetail and produces structured customer evidence.

### CrewAI Upgrade from 1.13.0 to 1.14.2

Bumped `pyproject.toml` from `crewai[anthropic,tools]==1.13.0` to `crewai[anthropic,bedrock,tools]>=1.14.0,<2.0.0`. Added the `bedrock` extra for native Bedrock provider support.

## What Broke and How We Fixed It

### 1. Bedrock model ID format (quick fix)

The AWS console shows the model ID as `anthropic.claude-sonnet-4-6`, but Bedrock's on-demand invocation requires the US cross-region inference profile prefix: `us.anthropic.claude-sonnet-4-6`. Without it, the API returns `ValidationException: Invocation of model ID... with on-demand throughput isn't supported`.

Fix: auto-prefix logic in `crew.py` that prepends `us.` if the model ID doesn't start with a region prefix.

### 2. Anthropic API credit balance exhausted

The personal Anthropic API key ran out of credits during testing. Every call returned `400: Your credit balance is too low`. This blocked the Anthropic-direct fallback path.

Resolution: pivoted fully to Bedrock, which is billed through the AWS account and has no credit-balance gating.

### 3. CrewAI 1.13.0 Bedrock tool-argument serialization bug (the big one)

On CrewAI 1.13.0, the `BedrockCompletion` provider passed empty dicts (`{}`) as tool arguments instead of the LLM's actual args. Every Dovetail tool call received `query=""`, triggering the "requires a non-empty query" validation error. The agent retried 52 times, got the same error each time, and eventually gave up.

Diagnosis path:
1. Stage 1 test showed 52 tool calls, all with empty query
2. `dovetail_calls.log` confirmed `query=""` on every invocation
3. Raw `boto3.client.converse()` call proved Bedrock returns correct `toolUse.input = {"query": "developer documentation pain points"}`
4. Traced through CrewAI source: `_format_tools_for_converse()` produces correct `toolConfig`, `extract_tool_info()` produces correct parameters, but somewhere in the response-processing pipeline the args were being dropped
5. Confirmed this was a CrewAI framework bug, not an API or schema issue

Fix: upgraded CrewAI from 1.13.0 to 1.14.2. The tool-arg passthrough works correctly in 1.14.2.

### 4. DovetailSearchInput schema defense-in-depth

Changed `query` field from `default=""` (optional) to `...` (required) in the Pydantic schema. Even though the 1.14.2 upgrade fixed the root cause, making `query` required provides defense against future regressions where the LLM might omit optional fields.

## What We Tried That Didn't Work

- **LiteLLM path:** Investigated using `crewai.LLM("bedrock/...")` with LiteLLM as an alternative to the native BedrockCompletion. Found that CrewAI's `LLM.__new__` factory routes `bedrock/` prefixed models to the same native `BedrockCompletion` class, so this would have hit the same bug. LiteLLM wasn't installed and would have required `is_litellm=True` to force the fallback path.
- **Anthropic direct as fallback:** Blocked by exhausted credit balance.
- **Kiro model traffic issues:** Hit "high volume of traffic" errors on the Kiro-side model (Claude Opus 4.7) three times during the session, requiring model switch to Opus 4.6.

## Stage 1 Results

Final run on CrewAI 1.14.2 + Bedrock + Claude Sonnet 4.6:

- **5 real customer evidence quotes** extracted from Dovetail's CAPE Apps & Games Research Repository
- Quotes include: Vega documentation quality pain points, OS disparity and tooling gaps, testing tool satisfaction at 3.2/5, media player issues at 21% of forum posts, simulator and debugging gaps
- **10 Dovetail call log entries**: multiple deep_search calls returning 6,833 / 9,860 / 27,321 chars, plus highlights calls returning 832 / 19,719 chars
- **Verdict: SUCCESS.** The isolated single-agent single-tool pattern works on Bedrock. Proceeding to Stage 2 is safe.

## Commits Pushed to origin/main

| Hash | Commit | Notes |
|------|--------|-------|
| `d63e4d6` | feat: add AWS Bedrock support via LLM_PROVIDER env var | crew.py, pricing.py, .env.example |
| `6b4ff1c` | Revert mandatory tool call prompt changes | Cleaned up from 4/20 session |
| `99af12e` | fix: upgrade CrewAI to 1.14.2 to fix Bedrock tool-arg bug | pyproject.toml, dovetail schema |

## Recommended Next Steps

1. **Stage 2: Split research task into three sequential sub-tasks.** Now that Stage 1 proves the pattern works, implement Option A from the planning doc: external_research_task (Tavily + CompetitiveIntel), customer_evidence_task (Dovetail only), synthesis_task (no tools, assembles final ResearchOutput). This prevents Dovetail from being skipped when competing with 7 other tools.

2. **Run full pipeline on Bedrock.** After Stage 2, run `full-pipeline` against `input/tech_docs_integrator.yaml` with `LLM_PROVIDER=bedrock`. Validate that customer_evidence flows through to PRFAQ appendix_customer_quotes and BRD user stories.

3. **Bedrock bearer token rotation.** The current token is short-term. Set up a process for regenerating it before expiry, or investigate whether the METExperiments account supports longer-lived credentials or SSO-based auth.

4. **CrewAI version monitoring.** Pin to `>=1.14.0` not `==1.14.2` so future patches land automatically. Watch CrewAI's changelog for Bedrock-related fixes.

5. **Dovetail content expansion.** The CAPE project has only 4 insights with extractable content. As more research gets published to Dovetail, the deep_search results will get richer. Consider adding a Dovetail project ID whitelist in `.env` so the agent can target specific projects.

## Key Learnings

1. **CrewAI's Bedrock provider is usable but fragile.** The 1.13.0 tool-arg bug was a showstopper that required source-level debugging to diagnose. The fix was a version bump, but finding it took hours of tracing through CrewAI internals. Pin versions carefully and test tool-calling on every upgrade.

2. **Bedrock API keys are bearer tokens, not IAM access keys.** The newer Bedrock-specific API key format is a single long JWT-style token set via `AWS_BEARER_TOKEN_BEDROCK`. boto3 picks it up automatically. No `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` needed.

3. **Cross-region inference profiles are required for newer Claude models.** `anthropic.claude-sonnet-4-6` fails with `ValidationException` on direct invocation. Must use `us.anthropic.claude-sonnet-4-6` (the US inference profile). Auto-prefix logic in `crew.py` handles this transparently.

4. **Stage 1 validation before architecture changes is the right pattern.** Building a minimal throwaway test crew before committing to a multi-task refactor saved us from debugging two problems at once. When Stage 1 failed on 1.13.0, we knew the issue was CrewAI, not our architecture.

## Links

- Planning doc: [[2026-04-21 Planning - Research Task Architecture Decision]]
- Prior session recap: [[2026-04-20 Kiro Session Recap - Dovetail Integration]]
- CrewAI changelog: https://github.com/crewAIInc/crewAI/releases
- Dovetail CAPE project ID: `3wf8VQS4Pa99qsJzFGLS4A`
