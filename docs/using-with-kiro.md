# Using PM Working Backwards with Kiro

Kiro is an AI coding IDE from Amazon that supports steering files, skills, and custom agents. This project includes all three. Kiro can run the full Working Backwards pipeline natively.

## Setup

1. Open this repo in Kiro (IDE or CLI)
2. Kiro automatically loads the steering files from `.kiro/steering/`
3. The three skills (research-agent, prfaq-agent, brd-build-spec-agent) appear in the Agent Steering & Skills panel

## Running the Pipeline

### Option 1: Custom Agent (recommended)
```
kiro-cli --agent pm-working-backwards
```
Or in the IDE: type `/agent swap` and select `pm-working-backwards`.

The agent guides you through the full pipeline conversationally.

### Option 2: Individual Skills
Activate a specific skill by mentioning it in chat:
- "I need to research a product idea" activates research-agent
- "Help me write a PRFAQ from this research" activates prfaq-agent
- "Generate a BRD from this approved PRFAQ" activates brd-build-spec-agent

### Option 3: CLI Pipeline
If you prefer the Python CLI, it works from Kiro's terminal:
```
uv run pm_agent_system full-pipeline examples/input.yaml
```

## Build Spec Integration
When Agent 3 produces a build spec with `target_tool: kiro`, the output is formatted as a Kiro-compatible spec. You can open it directly in Kiro and use spec-driven development to generate the implementation.

## Tips
- The steering files load automatically on every session. You don't need to reference them.
- Skills activate based on what you're discussing. Kiro decides when they're relevant.
- You can also type `#research-agent` in chat to manually activate a skill.
