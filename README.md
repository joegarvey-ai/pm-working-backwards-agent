# Working Backwards Agent for Product Managers

An open-source multi-agent AI system that guides product managers from a rough problem statement through stakeholder-ready research, a Working Backwards PRFAQ, a BRD, and an engineer-ready build spec. Built on [CrewAI](https://www.crewai.com/) and Claude.

This is for product managers, not engineers. If you can edit a YAML file and copy-paste an API key, you can run it. See [SETUP.md](SETUP.md) for a step-by-step walkthrough that assumes you have never used a terminal.

## How it works

```mermaid
flowchart LR
    A[input.yaml<br/>Problem statement] --> B[Agent 1<br/>Research]
    B --> C[research_brief.md]
    C --> D[Agent 2<br/>PRFAQ]
    D --> E[prfaq_v1.0.md]
    E --> F[Agent 3<br/>BRD + Build Spec]
    F --> G[brd_v1.0.md]
    F --> I[build_spec.md]
    I --> J[Drop into<br/>Kiro / Claude Code / Cursor]
```

> Three agents, four artifacts. Agent 3 produces two artifacts in sequence — the BRD first, then the build spec after you approve the BRD. In the code, these are two tasks within one agent, not two separate agents.

You write a short problem statement. The agents do the research, write the Working Backwards document, translate it into requirements, and produce a build spec your engineers (or coding agent) can run with. You stay in the loop at every handoff.

## What This System Is Not

This system does not replace your existing tools:

- **Not a replacement for Jira or Linear.** It produces requirements, not tickets. You take the BRD's user stories and create tickets in your project management tool.
- **Not a replacement for Confluence or Notion.** It generates documents (PRFAQ, BRD) that you publish to your wiki. It references your existing docs rather than duplicating them.
- **Not a replacement for Figma or design tools.** The build spec describes what to build, not how it should look. Design happens alongside or after the BRD.
- **Not a replacement for your coding IDE.** Agent 3 produces a build spec that you load into Kiro, Claude Code, Cursor, or Lovable. The coding happens in your tool of choice.
- **Not a replacement for PM judgment.** Every artifact has a human review checkpoint. The system accelerates your first draft — you own the final version.

This system is the connective layer between research and execution. It takes a product problem and produces the artifacts that bridge the gap between "we should build this" and "here's exactly what to build and why."

## Quick start

Prerequisites: Python 3.11+, [uv](https://github.com/astral-sh/uv), an Anthropic API key, a Tavily API key.

```bash
git clone https://github.com/joegarvey-ai/pm-working-backwards-agent.git
cd pm-working-backwards-agent
crewai install
cp .env.example .env
# Open .env and paste in your ANTHROPIC_API_KEY and TAVILY_API_KEY
uv run pm_agent_system full-pipeline examples/input.yaml
```

The first run takes 5-10 minutes and produces files in `./output/`. See [examples/](examples/) for what those files look like.

The `examples/` directory contains sample input files, standalone-mode examples, and templates (style guide, customer requirements formats in `examples/templates/`). The `input/` directory is where you put your own input files — see [input/README.md](input/README.md).

For a step-by-step setup walkthrough written for non-technical users, read [SETUP.md](SETUP.md).

## Platform Support

This system runs in multiple environments. Choose the one that fits your workflow:

| Platform | How It Works | Setup Guide |
|---|---|---|
| **CLI** | Python commands in your terminal | [SETUP.md](SETUP.md) |
| **Kiro** | Native skills and custom agent | [docs/using-with-kiro.md](docs/using-with-kiro.md) |
| **Claude Code** | CLI from Claude Code terminal | [docs/using-with-claude-code.md](docs/using-with-claude-code.md) |
| **Claude Desktop / Projects** | Conversational with uploaded knowledge | [docs/using-with-claude-projects.md](docs/using-with-claude-projects.md) |
| **Cursor** | CLI + Composer with project rules | [docs/using-with-cursor.md](docs/using-with-cursor.md) |

**Don't know which to pick?** If you're comfortable with a terminal, use Claude Code or the CLI. If you prefer conversation, use Claude Desktop or a Claude.ai Project. If you're at Amazon, Kiro is the natural fit.

## Common Scenarios

| I need to... | Command |
|---|---|
| Validate a product idea with market research | `uv run pm_agent_system research input/my-product.yaml` |
| Write a stakeholder-ready PRFAQ from scratch | `uv run pm_agent_system generate input/my-product.yaml` |
| Run the full pipeline end to end | `uv run pm_agent_system full-pipeline input/my-product.yaml` |
| Revise a PRFAQ after a stakeholder review meeting | `uv run pm_agent_system revise --prfaq-path prfaq_v1.0.md --context-path notes.md` |
| Turn an approved PRFAQ into an engineer-ready BRD | `uv run pm_agent_system brd input/my-product.yaml --prfaq-path prfaq_v1.2.md` |
| Generate a Kiro build spec from a BRD | `uv run pm_agent_system build-spec --brd-path brd_v1.0.md --target-tool kiro` |
| Update a BRD after engineering feedback | `uv run pm_agent_system revise-brd --brd-path brd_v1.0.md --context-text "FR-003 needs a GSI"` |
| I have my own research and just need a PRFAQ | `uv run pm_agent_system generate input/my-product.yaml --research-path research.md` |
| I have an approved PRFAQ and my own requirements | `uv run pm_agent_system brd input/my-product.yaml --prfaq-path prfaq.md --requirements-path requirements.csv` |
| Skip the assumption-challenge step | Add `--skip-validation` to any research/generate/full-pipeline command |
| Compare two document versions after a revision | `uv run pm_agent_system diff output/prfaq_v1.0.md output/prfaq_v1.1.md` |

Each command pauses for your review before producing the next artifact. See the [CLI Commands](#cli-commands) section below for full details, or the [Platform Support](#platform-support) section for non-CLI options.

## CLI commands

| Command | What it does |
|---|---|
| `research <input.yaml>` | Run Agent 1 only. Produces a research brief. |
| `generate <input.yaml>` | Run Agents 1 + 2. Produces a research brief and a PRFAQ v1.0. |
| `revise --prfaq-path <file>` | Run Agent 2 to revise an existing PRFAQ. Pass `--context-text` or `--context-path` for the revision notes. |
| `full-pipeline <input.yaml>` | Run all three agents end to end. Produces research brief, PRFAQ, BRD, and build spec. |
| `brd <input.yaml> --prfaq-path <file>` | Run Agent 3 to produce a BRD and build spec from an approved PRFAQ. |
| `build-spec --brd-path <file>` | Regenerate just the build spec from an approved BRD. Useful when switching `--target-tool`. |
| `revise-brd --brd-path <file>` | Revise an existing BRD. Pass `--context-text` or `--context-path` for the revision notes. |
| `diff <old> <new>` | Compare two document versions section by section. Shows which sections were added, removed, or changed. Works best with agent-generated document pairs — manual header renames between versions appear as a deletion plus an addition rather than a single change. |
| `clean --archive` / `--list` / `--delete-archive` | Manage the `./output/` directory retention policy. |

Run `uv run pm_agent_system <command> --help` for the full options on any command.

Every BRD generation also produces `brd_*_jira_import.csv` and `brd_*_linear_import.md` files in the output directory, ready to import into Jira or Linear. Column names and field labels are configurable — edit `config/jira_import_schema.yaml` and `config/linear_import_schema.yaml` to match your instance before importing.

## Configuration

All configuration lives in `.env`. Copy `.env.example` to `.env` and fill it in.

| Variable | Required | What it is |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | Your Anthropic API key. The agents use Claude. |
| `TAVILY_API_KEY` | yes | Your Tavily API key. The research agent uses Tavily for web search and competitive intelligence. |
| `DOVETAIL_API_TOKEN` | no | Optional. If you have a Dovetail UX research workspace, the research agent will pull customer evidence from it. Leave blank to skip. |
| `STYLE_GUIDE_PATH` | no | Path to your writing style guide. Defaults to `examples/templates/style-guide-sample.md`. |
| `OBSIDIAN_VAULT_PATH` | no | Optional. Path to your Obsidian vault if you want the agents to search your notes. |
| `OUTPUT_DIR` | no | Where output files go. Defaults to `./output/`. |
| `DEFAULT_TARGET_TOOL` | no | Which coding tool the build spec is formatted for. One of `kiro`, `claude_code`, `cursor`, `lovable`. Defaults to `kiro`. |
| `AWS_PRICING_REGION` | no | AWS region for pricing lookups. Defaults to `us-east-1`. The AWS Pricing API is public but boto3 may need credentials — see `.env.example`. |
| `OUTPUT_RETENTION_DAYS` | no | How many days output files live before being archived. Defaults to 30. |

## Architecture

Three agents, each with a single job, chained by a CrewAI orchestrator. Agent 3 produces two artifacts (BRD, then build spec) as two sequential tasks within one agent.

| Agent | Job | Tools |
|---|---|---|
| 1. Research | Gather evidence from web, customer research, and internal notes | Tavily web search, competitive intelligence (G2/Capterra/TrustRadius), Dovetail (optional), Obsidian (optional), file readers |
| 2. PRFAQ | Turn the research brief into a Working Backwards press release and FAQ | Style guide loader |
| 3. BRD + Build Spec | Translate the approved PRFAQ into requirements (BRD) and format them into a coding-agent-ready build spec | Tavily (cost flags, API doc lookups), AWS Pricing API (exact per-unit pricing for cost flags) |

The orchestrator lives in `src/pm_agent_system/crew.py`. Agent and task definitions are in `src/pm_agent_system/config/agents.yaml` and `tasks.yaml`. Each agent's outputs are validated against a Pydantic model in `src/pm_agent_system/models/`.

A human-in-the-loop checkpoint sits between every stage. The agents do not auto-advance from research to PRFAQ or PRFAQ to BRD. You read the output, decide if it is good, and either approve it or run the `revise` command.

## Known limitations

- The system has been tested on a small number of product problems. It works well for "we want to build X for Y users" but has not been stress-tested on M&A diligence, pricing strategy, or pure platform engineering problems.
- Agent 1 only knows what it can find via Tavily, Dovetail, your Obsidian vault, and any files you point it at. It cannot access paywalled research or your internal Slack.
- Output quality depends heavily on the input. A vague input gets a vague output. The example in `examples/input.yaml` shows the level of specificity that produces good results.
- A full pipeline run costs roughly $1-3 in API usage at current Claude pricing. Run `research` first if you want a cheap sanity check before committing.
- This is research software. It is not enterprise-ready. There is no auth, no multi-tenancy, no audit log.

## License

[MIT](LICENSE). Use it, fork it, ship it.

## Contributing

Pull requests welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the short version of how to help.
