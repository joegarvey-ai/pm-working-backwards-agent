---
name: research-agent
description: Run market research, competitive analysis, and customer evidence gathering for a product idea. Use when the PM needs to validate or pressure-test a product concept with real data.
---

# Research Agent

## What This Skill Does
Takes a structured product brief and produces a sourced research report covering market sizing, competitive landscape, customer evidence, pain points, and strategic implications.

## Input Required
The PM must provide at minimum:
1. Feature / Idea Summary - what to build or validate
2. Goals - measurable outcomes
3. Timing - timeline constraints
4. User Summary - who the users are

Optional but recommended:
5. Success Metrics - how to measure success
6. Known Constraints - budget, platform, regulatory limits
7. Internal Context Upload - existing docs, screenshots, architecture diagrams
8. Business Context - current-state metrics (churn, conversion, adoption)

## Process
1. If input is incomplete, ask the PM to fill gaps before proceeding
2. Challenge the PM's assumptions with 5 hard questions (can be skipped with user confirmation)
3. Research using Tavily search for external data
4. Cross-reference with any internal documents provided
5. Produce a structured research brief with inline citations

## Output Structure
1. Context (problem restatement)
2. Executive Summary / Key Findings
3. Detailed Findings (market sizing, competitors, customer evidence, pain points, internal state)
4. Strategic Implications (what data suggests, not recommendations)
5. Gaps and Limitations
6. Sources

## Quality Rules
- Every claim must have a source citation
- Minimum 3 competitors analyzed
- No fabricated quotes or data
- Flag gaps honestly rather than writing around them
