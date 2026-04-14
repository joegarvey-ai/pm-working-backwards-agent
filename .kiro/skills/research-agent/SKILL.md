---
name: research-agent
description: Run market research, competitive analysis, and customer evidence gathering for a product idea. Use when the PM needs to validate or pressure-test a product concept with real data.
---

# Research Agent

## What This Skill Does
Takes a structured product brief and produces a sourced research report covering market sizing, competitive landscape, customer evidence, pain points, and strategic implications.

## Key Files
- Agent prompt: #[[file:src/pm_agent_system/config/agents.yaml]] (research_agent section)
- Task prompt: #[[file:src/pm_agent_system/config/tasks.yaml]] (validate_input and research_task sections)
- Output schema: #[[file:src/pm_agent_system/models/research_output.py]]
- Renderer: #[[file:src/pm_agent_system/utils/render_markdown.py]]
- Example input: #[[file:examples/input.yaml]]

## Input Required
The PM must provide at minimum:
1. Feature / Idea Summary
2. Goals (measurable outcomes)
3. Timing (timeline constraints)
4. User Summary (who the users are)

Optional but recommended:
5. Success Metrics
6. Known Constraints
7. Internal Context Upload
8. Business Context (current-state metrics)

## Process
1. If input is incomplete, ask the PM to fill gaps before proceeding
2. Challenge the PM's assumptions with 5 hard questions (can be skipped with `--skip-validation`)
3. Research using Tavily search for external data
4. Cross-reference with any internal documents provided
5. Produce a structured research brief with inline citations

## Running via CLI
```
uv run pm_agent_system research examples/input.yaml
uv run pm_agent_system research examples/input.yaml --skip-validation
```

## Output Structure
1. Context (problem restatement)
2. Executive Summary / Key Findings
3. Detailed Findings (market sizing, competitors, customer evidence, pain points, internal state)
4. Strategic Implications (what data suggests, not recommendations)
5. Gaps and Limitations
6. Sources

## Quality Rules
- Every claim must have an inline `[source](url)` citation
- Minimum 3 competitors analyzed
- No fabricated quotes or data
- Flag gaps honestly rather than writing around them
