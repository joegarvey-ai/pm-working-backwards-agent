---
date: 2026-04-21
project: Agentic PM Assistant
status: draft, pending review
related: [[2026-04-20 Kiro Session Recap]]
---

# Planning: Research Task Architecture Decision

## Problem Statement

The research task is overloaded. One agent is asked to perform 8 to 10 tool calls (Tavily market sizing, Tavily competitor discovery, CompetitiveIntel lookups per competitor, Dovetail deep_search twice, FileReader for internal context) and produce a ten-field Pydantic output with inline citations, style rules, and banned-word filtering in a single LLM turn.

Observed failures under this load:

- Agent silently skips Dovetail calls (no `dovetail_calls.log` entries during test runs)
- Attempts to force Dovetail calls via "MUST call" prompt language caused malformed output (XML tool-call syntax leaking into JSON fields)
- Even when tools execute, customer_evidence is often empty because the agent's output budget is consumed by the competitive_landscape section generated earlier in the JSON structure

This document evaluates three architectural options for fixing it, with pros, cons, and risk analysis for each. The goal is to pick a path that gets real Dovetail content into research outputs reliably, without destabilizing the rest of the pipeline.

## Context: Why Dovetail Matters

The Dovetail workspace contains real Amazon developer customer research spanning:

- CAPE Apps & Games Research Repository (project `3wf8VQS4Pa99qsJzFGLS4A`) with the Vega SDK developer challenges insight, Kepler/Vega documentation usability studies, Fire TV developer experience benchmarking
- DxD Research Repository with Conversation Facilitation beta results
- 91 total projects across the workspace

This data is directly comparable in value to the PM's own brief. When Dovetail is missing from research output, the downstream PRFAQ, BRD, and build spec all produce generic content that lacks Amazon-specific developer voice. Every artifact quality improvement traces back to whether Dovetail content flowed through the first agent.

## Option A: Current Stage with 3 Sequential Sub-Tasks (Recommended First)

Keep one research_agent. Split the single research_task into three sequential tasks chained via CrewAI task context.

### Architecture

```
research_agent (one agent, three tasks, sequential process)
  |
  +-- external_research_task
  |     tools: [TavilySearchTool, CompetitiveIntelTool]
  |     output: ExternalResearchOutput (market_sizing, competitors)
  |
  +-- customer_evidence_task
  |     tools: [DovetailSearchTool]
  |     output: CustomerEvidenceOutput (customer_evidence, dovetail_gaps)
  |     context: [external_research_task]
  |
  +-- synthesis_task
        tools: [] (none)
        output: ResearchOutput (full schema, assembled from prior task outputs)
        context: [external_research_task, customer_evidence_task]
```

### Pros

- **Smallest blast radius.** Changes are isolated to `crew.py` (add two tasks, restructure research_crew builder) and `tasks.yaml` (split one task into three). No new Python modules, no new Pydantic models beyond two small intermediate schemas.
- **Each task has one job.** Customer evidence task has one tool (Dovetail), so the agent cannot skip it. No competing priorities.
- **Smaller token budgets per task.** Each task's output is one section of the current ResearchOutput, so each LLM call stays well under the 16,384 output limit. No truncation risk.
- **Synthesis task has zero tools.** That's where the final ResearchOutput gets assembled. No tool-use format confusion because there's no tool-use happening.
- **Matches CrewAI's idiomatic pattern.** Task context chaining is how CrewAI is meant to be used. Well-documented, battle-tested.
- **Easy to prove with Stage 1 single-task test.** If I can make a minimal one-agent one-task Dovetail crew work in isolation, that directly proves the pattern works here.

### Cons

- **Three serial LLM calls instead of one.** Total latency goes from roughly 60 seconds to roughly 180 seconds for the research step. Linear cost increase in both tokens and wall time.
- **Still a single agent.** The agent's backstory and style rules apply to all three tasks. If we want different voice or priorities per task, we'd need agent-level specialization, which means Option B.
- **Synthesis task could reintroduce the overload problem.** If the synthesis task is asked to produce the full ResearchOutput with all ten fields in one shot, we're back where we started. Needs prompt engineering to limit what the synthesis task actually assembles (probably just pain_points, strategic_implications, executive_summary, plus merging the prior outputs).
- **Upstream code assumes one research output.** CrewAI task context chaining passes Pydantic objects, so this should work, but I'd want to verify the PRFAQ agent (Agent 2) consumes the final ResearchOutput the same way it does today.

### Risks

- **Medium: CrewAI task context edge cases.** The `context=[task1, task2]` pattern is well-documented, but passing typed Pydantic objects across tasks is where things sometimes break in CrewAI (field name collisions, partial serialization). Mitigation: design the intermediate outputs to have non-overlapping field names.
- **Low: prompt consistency.** The three tasks need to agree on style, citation format, banned words. Solved by having the agent backstory contain the style rules (already the case today) rather than duplicating them in every task prompt.
- **Low: checkpoint behavior.** The existing checkpoint system (`output/.checkpoint.json`) records artifacts by pipeline stage. Three research tasks produce intermediate outputs; we'd need to decide whether to checkpoint each or only the final merged ResearchOutput.

### Effort

60 to 90 minutes. Two new Pydantic models (ExternalResearchOutput, CustomerEvidenceOutput) or one composite. Three YAML task definitions. One `crew.py` method refactor. No changes to the renderer or downstream agents.

## Option B: Multi-Agent Orchestration (Your Original Proposal)

Split the research agent into four distinct agents, each with its own backstory, tool set, and output.

### Architecture

```
Agent 0: Input Parser / Orchestrator
  tools: [FileReaderTool, ObsidianReadTool]
  job: parse user inputs (YAML, .md brief, Obsidian files, attachments)
       produce standardized research directives for Agents 1a/1b

Agent 1a: External Research Specialist
  tools: [TavilySearchTool, CompetitiveIntelTool]
  job: market sizing, competitive landscape, public customer quotes
  output: ExternalResearchOutput

Agent 1b: Internal Customer Research Specialist
  tools: [DovetailSearchTool, ObsidianSearchTool]
  job: Amazon-specific customer evidence, published insights, internal UX findings
  output: CustomerEvidenceOutput

Agent 1c: Synthesis & Bar-Raising
  tools: [] (or a citation_validator tool)
  job: merge 1a + 1b outputs, add pain_points, strategic_implications,
       validate that every claim has a source, final ResearchOutput
```

### Pros

- **True role separation.** Each agent's backstory, style voice, and evaluation criteria can differ. Agent 1b can be prompted as "an Amazon UX researcher who reads Dovetail transcripts for a living" which is more specific than a general product analyst.
- **Better fit for your long-term vision.** The orchestrator (Agent 0) pattern is where Obsidian file ingestion, plain-English input parsing, and multi-source kickoff belong. This is the right shape for how you want PMs to use the tool.
- **Bar-raising agent as a quality layer.** LLM-as-judge patterns work well for catching unsourced claims, style violations, and missing citations. Separate agent means the judge doesn't share context-window pressure with the writer.
- **Future-proof for parallelism.** If we later want Agent 1a and Agent 1b to run concurrently, agent isolation makes that easier.

### Cons

- **Much bigger change.** Four agents means four YAML configs, four crew builders, coordination logic in `crew.py`, orchestration of four Pydantic schemas, and test updates. Probably 200 to 300 lines of code change plus documentation.
- **Higher token cost.** Each agent gets its own system prompt containing backstory, style rules, banned words, AWS-first defaults, and output schema description. That overhead multiplies by four. Estimate 3x to 5x the prompt tokens per research run vs current.
- **More latency.** Four sequential agent invocations instead of one or three. Estimate 5 to 7 minutes for the research phase, up from roughly 1 minute.
- **Parallel execution is non-trivial in CrewAI.** The `Process.hierarchical` mode exists but has known issues. True parallel task execution requires CrewAI 1.14+ with the async API, and that's not fully in `uv.lock` yet. If parallelism is a must-have, we're debugging CrewAI internals, not building features.
- **We haven't validated the pattern works in isolation yet.** If the CrewAI + Anthropic tool-use / output-format confusion is a general problem (not specific to overloaded tasks), then splitting into more agents doesn't solve it, just localizes it. Each of the four agents could hit the same format-confusion bug.
- **Orchestrator complexity.** Agent 0 as described has to parse arbitrary inputs (YAML, Markdown, Obsidian files, attachments) and generate standardized research directives. That's its own agent prompt engineering problem and could easily become the bottleneck.

### Risks

- **High: untested at this scale.** We have zero evidence this architecture fixes the Dovetail-skip problem. If it doesn't, we've spent hours on a refactor that landed us back at the starting point.
- **High: regression risk across agents 2 to 4.** The PRFAQ, design brief, and BRD agents consume research output via CrewAI context. Changing what flows through the research phase could break downstream serialization assumptions.
- **Medium: upstream coordination.** Your private GitHub has active commits coming in from Claude Code sessions. A 300-line research architecture refactor pushed to main could conflict with whatever Agent 5 or Agent 6 work you have in progress.
- **Medium: orchestrator agent unbounded scope.** "Parse user inputs in plain English, Obsidian files, YAML, attachments" is a big ask. Real version needs careful scoping.
- **Low: cost per run.** 3x to 5x tokens per research run at current Claude Sonnet pricing is a few extra cents per run. Not a real blocker, just worth noting.

### Effort

4 to 6 hours for the core refactor, plus 2 hours of testing, plus probably 2 hours of documentation updates. Non-trivial.

## Option C: "Dovetail First" Lightweight Fix (Middle Ground)

Keep the current single-agent single-task architecture. Force Dovetail to execute as a mandatory first step by making it programmatic rather than agent-chosen.

### Architecture

```
research_agent (one agent, one task)

Before task starts:
  Pre-hook: call Dovetail deep_search twice (with query derived from
            feature_summary keywords) programmatically via Python.
            Write the result to a file like
            output/.dovetail_prefetch_<slug>.md
            Inject the file path into the task's input variables.

Inside task prompt:
  "You have pre-fetched Dovetail content at {dovetail_prefetch_path}.
   Use the file_reader tool to read it. Extract customer quotes for
   the customer_evidence section. Do NOT call dovetail_research again."

No mandatory-tool-call language. The tool call already happened outside
the agent loop.
```

### Pros

- **Smallest possible code change.** No new agents, no new Pydantic models, no task restructuring. Just a pre-task hook in `crew.py` and a small prompt adjustment.
- **Guarantees Dovetail content is in context.** The agent can't skip Dovetail because the content is in a file it's instructed to read. FileReader is a simple tool the agent always uses when told to.
- **Sidesteps the format-confusion bug entirely.** No "MUST call tool" language needed.
- **Fastest to implement and test.** 30 minutes of work.

### Cons

- **Pre-fetch query derivation is dumb.** Without LLM reasoning, we'd just derive the Dovetail query from feature_summary keywords. Might return less relevant insights than an agent-reasoned query would.
- **Only fixes Dovetail, not the underlying overload problem.** Tavily and CompetitiveIntel are still invoked inside the task, with all the same token budget pressure. If truncation hits, it hits somewhere else.
- **Not a generalizable pattern.** We'd do this for Dovetail only, leaving the architecture uneven. Future integrations (Jira, SharePoint, etc.) would need their own custom pre-fetch logic.
- **Hides research behavior from the user.** The CLI verbose output wouldn't show the Dovetail call happening in the agent loop, making debugging less transparent.

### Risks

- **Low: implementation.** This is straightforward Python. No CrewAI weirdness.
- **Medium: query quality.** A keyword-derived Dovetail query is worse than an agent-reasoned one. Some problem domains might not match well. Mitigation: use a small LLM call with just the feature_summary to generate the Dovetail query.
- **Low: downstream impact.** No schema or task-flow changes, so Agents 2 to 4 behave identically.

### Effort

30 to 45 minutes.

## Recommendation

**Stage 1 (30 minutes): Minimal Dovetail-only CrewAI test.**

Before committing to Option A, B, or C, validate the pattern works. Build a throwaway minimal crew: one agent, one tool (Dovetail only), one task ("find customer quotes about documentation pain points"), one output (customer_evidence + gaps). Run it. Check `output/dovetail_calls.log` for tool invocations. Check the output for real Vega quotes.

Outcome A: It works. Confirms Option A will work, since Option A is the same pattern scaled to three sequential tasks. Proceed to Stage 2.

Outcome B: It fails in the same way as today. Confirms CrewAI + Anthropic has a deeper format-confusion problem that affects any task with tools. In that case, Option C becomes the preferred path because it sidesteps the tool-use format issue entirely. Option B is still on the table but riskier.

**Stage 2 (if Stage 1 succeeds, 60 to 90 minutes): Option A.**

Implement three sequential sub-tasks. Ship it. Run the full research pipeline against the tech docs brief. Validate customer_evidence is populated with real Dovetail quotes.

**Stage 3 (if Stage 2 works and you still want multi-agent, 4 to 6 hours): Option B promotion.**

Convert the three tasks into three dedicated agents with specialized backstories. Add Agent 0 orchestration separately, once the core research flow is stable.

**Skip or defer:**

- The "LLM-as-judge" bar-raising agent (1c synthesis). Useful pattern, but it's a quality-layer improvement on top of already-good data. No value until the base pipeline produces real content.
- Parallel execution of 1a and 1b. 60 seconds of saved latency is not worth CrewAI concurrency debugging until everything else works.
- Orchestrator Agent 0 with Obsidian/plain-English input parsing. This is a separate feature track from research quality. Tackle after research is solid.

## Open Questions (For Tomorrow's Session)

1. Which option feels right to you given the cons analysis above? I lean strongly toward Stage 1 then Option A, but Option C is also reasonable if you want to deprioritize architectural cleanup in favor of speed.
2. Should the three-sub-task pattern (Option A) produce a unified ResearchOutput at the end, or should we let the downstream agents (PRFAQ, design brief, BRD) consume the three intermediate outputs directly via task context chaining? Unifying is simpler. Letting them flow separately is more flexible long-term.
3. Do you want me to write the Stage 1 minimal-crew test script, or do you want to do it yourself as a learning exercise? It's a good small CrewAI exercise.
4. Do you want the Dovetail logging kept in as a permanent diagnostic feature, or should we scope it to a dev flag so production runs don't write per-call logs?
5. How concerned are you about your other in-progress agents on the private GitHub? If there's a big refactor landing in the next few days, we might want to coordinate or delay.

## Technical Deep-Dive: The CrewAI + Anthropic Tool-Use Problem

The failure from session 2026-04-20 where the agent emitted `<parameter name="summary...>` inside a JSON field is worth double-clicking. Here's what I believe is happening:

CrewAI uses the Anthropic Completion API with structured output (Pydantic schema enforcement). Anthropic's native tool-use format is XML-tagged. When the agent is told "you MUST call the tool" while also being asked to return structured JSON matching a Pydantic schema, the model sometimes conflates the two output modes. It starts generating what looks like an XML tool-call block inside a JSON string field.

This is a known edge case in Anthropic's structured output mode, not specific to our codebase. The workaround is to avoid prompting patterns that emphasize tool use alongside structured output.

Option A's synthesis task (no tools, just output generation) sidesteps this entirely because there's no tool-use context for the model to confuse.

Option B's per-agent isolation also helps, but each agent with tools still has the risk.

Option C's pre-fetch design sidesteps it completely because the agent's tools list stays minimal (just FileReader to read the pre-fetch file).

## References

- Session recap: [[2026-04-20 Kiro Session Recap]]
- CrewAI task context docs: https://docs.crewai.com/concepts/tasks
- Repo: https://github.com/joegarvey-ai/pm-working-backwards-agent
- Dovetail CAPE project ID: `3wf8VQS4Pa99qsJzFGLS4A`
- Current HEAD: `6b4ff1c` on main
