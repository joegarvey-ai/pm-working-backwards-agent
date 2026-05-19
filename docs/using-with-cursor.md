# Using PM Working Backwards with Cursor

Cursor reads the `.cursor/rules/` directory for project-specific conventions. This project includes a rules file that helps Cursor understand the pipeline.

## Setup
1. Open this repo in Cursor
2. Cursor automatically loads the rules from `.cursor/rules/pm-working-backwards.mdc`
3. Install dependencies in the terminal: `crewai install && cp .env.example .env`

## Running the Pipeline

Cursor's Composer is the recommended way for PMs to run this pipeline — it
lets you describe the idea in plain language and reviews each artifact with
you. The conversational rules in `CLAUDE.md` apply: Composer asks 3-5
clarifying questions, shows you the structured brief, waits for explicit
approval, and pauses after each stage.

In conversational mode, prefer per-stage commands so you review each artifact:

```
uv run pm_agent_system research input/my-product.md --skip-validation
uv run pm_agent_system generate input/my-product.md --skip-validation
uv run pm_agent_system brd input/my-product.md --prfaq-path output/prfaq_*_v1.0.md
uv run pm_agent_system build-spec --brd-path output/brd_*_v1.0.md --target-tool cursor
```

For CI/automation only — skips all human review:

```
uv run pm_agent_system full-pipeline examples/input.yaml --target-tool cursor
```

## Using Cursor's Composer
Run the pipeline conversationally through Cursor's Composer. The
`.cursor/rules/pm-working-backwards.mdc` rules file plus `CLAUDE.md` give
Composer the same conversational contract that Claude Code uses. You can
also paste a specific skill file from `.kiro/skills/` into the Composer
when you want to drive a single stage in isolation.

## Build Spec Integration
When Agent 4 generates a build spec with `target_tool: cursor`, the output is formatted as a Composer-ready prompt. Open it in Composer and Cursor will execute the build.
