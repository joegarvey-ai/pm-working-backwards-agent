# Using PM Working Backwards with Claude Code

Claude Code is the primary development interface for this project. The full CLI pipeline runs directly from the Claude Code terminal.

## Setup
1. Clone the repo and install dependencies:
```
git clone https://github.com/joegarvey-ai/pm-working-backwards-agent.git
cd pm-working-backwards-agent
crewai install
cp .env.example .env
# Add your API keys to .env
```

2. Claude Code automatically reads the `CLAUDE.md` file for project context.

## Running the Pipeline

### Full pipeline (all three agents)
```
uv run pm_agent_system full-pipeline examples/input.yaml
```

### Individual agents
```
uv run pm_agent_system research examples/input.yaml
uv run pm_agent_system generate examples/input.yaml
uv run pm_agent_system brd examples/input.yaml --prfaq-path output/prfaq_v1.0.md
uv run pm_agent_system build-spec --brd-path output/brd_v1.0.md --target-tool kiro
```

### Revision modes
```
uv run pm_agent_system revise --prfaq-path output/prfaq_v1.0.md --context-path meeting_notes.md
uv run pm_agent_system revise-brd --brd-path output/brd_v1.0.md --context-text "Engineering says FR-003 needs a GSI"
```

### Skip the challenge step
```
uv run pm_agent_system research examples/input.yaml --skip-validation
```

## Tips
- Use `uv run pm_agent_system clean --list` to see all output files
- Output files appear in `./output/` and optionally publish to a custom directory
- Each human review checkpoint pauses and waits for your input in the terminal
