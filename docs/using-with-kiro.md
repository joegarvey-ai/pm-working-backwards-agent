# Using PM Working Backwards with Kiro

Kiro is an AI coding IDE from Amazon that supports steering files, skills, hooks, and custom agents. This project includes all four. Kiro can run the full Working Backwards pipeline natively.

## Setup

1. Open this repo in Kiro
2. Kiro automatically loads the steering files from `.kiro/steering/` on every session
3. The three skills (research-agent, prfaq-agent, brd-build-spec-agent) appear in the Agent Steering & Skills panel
4. Three hooks activate automatically: test-on-save, protect-secrets, and style-guard

## What Loads Automatically

### Steering (always-on context)
- `repo-map.md` — file layout, run commands, conventions
- `product.md` — pipeline overview, core principles, style rules
- `tech.md` — Python/CrewAI stack, AWS-first defaults
- `pm-working-backwards.md` — pipeline workflow, human-in-the-loop rules, editing guidance

### Hooks (automated guardrails)
- **test-on-save** — runs `uv run pytest tests/ -x -q` when any `.py` file is saved
- **protect-secrets** — blocks writes to `.env` files and `output/` directory
- **style-guard** — checks for banned words, em dashes, contrast hooks before any file write

### Skills (activate on demand)
Each skill includes `#[[file:...]]` references that pull the actual source files (agent prompts, task prompts, output schemas, renderers) into Kiro's context when activated.

## Running the Pipeline

### Option 1: Custom Agent (recommended for guided workflow)
In the IDE, select the `pm-working-backwards` agent. It guides you through the full pipeline conversationally, pausing for your review at each step.

### Option 2: Individual Skills
Activate a specific skill by mentioning it in chat:
- "I need to research a product idea" activates research-agent
- "Help me write a PRFAQ from this research" activates prfaq-agent
- "Generate a BRD from this approved PRFAQ" activates brd-build-spec-agent

You can also type `#research-agent`, `#prfaq-agent`, or `#brd-build-spec-agent` in chat to manually activate a skill.

## BRD pipeline internals

The BRD stage runs three async siblings in parallel (`brd_structure_task`, `brd_cost_risk_task`, `brd_compliance_task`). Their outputs merge into `BRDOutput` via `brd_assembly_task`. The compliance sibling handles data classification, vendor considerations, privacy, compliance gates, launch readiness, and post-launch maintenance. STRIDE threat-model stubs and RACI matrices render deterministically after the build spec, not by the LLM.

### Option 3: CLI Pipeline
The Python CLI works from Kiro's terminal:
```
uv run pm_agent_system full-pipeline examples/input.yaml --target-tool kiro
```

## Build Spec Integration
When Agent 4 produces a build spec with `target_tool: kiro`, the output is formatted as a Kiro-compatible spec with requirements, design, and tasks sections. You can open it directly in Kiro and use spec-driven development to generate the implementation.

## Tips
- The steering files load automatically. You do not need to reference them.
- Skills activate based on what you discuss. Kiro decides when they are relevant.
- The style-guard hook catches banned words before they hit disk, so you get feedback in real time.
- If you edit Python files, the test-on-save hook runs pytest automatically.
- The protect-secrets hook prevents accidental writes to `.env` or `output/` from the agent.
