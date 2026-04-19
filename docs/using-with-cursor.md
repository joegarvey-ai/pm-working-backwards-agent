# Using PM Working Backwards with Cursor

Cursor reads the `.cursor/rules/` directory for project-specific conventions. This project includes a rules file that helps Cursor understand the pipeline.

## Setup
1. Open this repo in Cursor
2. Cursor automatically loads the rules from `.cursor/rules/pm-working-backwards.mdc`
3. Install dependencies in the terminal: `crewai install && cp .env.example .env`

## Running the Pipeline
Use the Cursor terminal to run CLI commands (same as Claude Code):
```
uv run pm_agent_system full-pipeline examples/input.yaml
```

## Using Cursor's Composer
You can also run the pipeline conversationally through Cursor's Composer. Paste the contents of a skill file (from `.kiro/skills/`) into the Composer and ask it to guide you through that step.

## Build Spec Integration
When Agent 4 generates a build spec with `target_tool: cursor`, the output is formatted as a Composer-ready prompt. Open it in Composer and Cursor will execute the build.
