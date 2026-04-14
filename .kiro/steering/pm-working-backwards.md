---
inclusion: always
name: pipeline-workflow
description: Pipeline workflow rules and agent interaction patterns
---

# Pipeline Workflow

## Agent Sequence
1. Research Agent — market research, competitive analysis, customer evidence → ResearchOutput
2. PRFAQ Agent — Working Backwards document for stakeholder alignment → PRFAQOutput
3. BRD Agent — engineer-ready requirements with code samples → BRDOutput
4. Build Spec — tool-specific output (kiro, claude_code, cursor, lovable) → CodingPromptOutput

## Human-in-the-Loop Rules
- Each agent pauses for PM review before the next agent starts
- Never auto-advance between agents
- The PM approves or requests revisions at each checkpoint
- Revision mode updates only PM-specified sections, preserving everything else

## Quality Rules
- Every factual claim must have an inline `[source](url)` citation
- AWS services by default for all architecture
- "The system shall..." format for functional requirements
- Given/when/then acceptance criteria
- No em dashes, no contrast hooks, no hyperbole, no banned words
- Gaps and limitations must be surfaced honestly, never written around

## Editing Guidance
- Prompt quality lives in `src/pm_agent_system/config/agents.yaml` and `tasks.yaml` — most improvements happen there, not in Python
- Output schemas in `src/pm_agent_system/models/` — change these when you need new fields in agent output
- When editing task descriptions, preserve the `{variable}` template placeholders — CrewAI interpolates them at runtime
