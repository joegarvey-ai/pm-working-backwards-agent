# Working Backwards Agent for Product Managers

An open-source multi-agent AI system that guides product managers from a rough problem statement through stakeholder-ready research, a Working Backwards PRFAQ, a design brief with screen inventory and user flows, a BRD, and an engineer-ready build spec. Built on [CrewAI](https://www.crewai.com/) and Claude.

This is for product managers, not engineers. If you can fill out a markdown template and copy-paste an API key, you can run it. See [SETUP.md](SETUP.md) for a step-by-step walkthrough that assumes you have never used a terminal.

## How it works

```mermaid
flowchart LR
    A[input brief<br/>.md or .yaml] --> B[Agent 1<br/>Research]
    B --> C[research_brief.md]
    C --> D[Agent 2<br/>PRFAQ]
    D --> E[prfaq_v1.0.md]
    E --> K[Agent 3<br/>Design Brief<br/>optional]
    K --> L[design_brief_v1.0.md]
    L --> F[Agent 4<br/>BRD + Build Spec]
    E -. "--skip-design" .-> F
    F --> G[brd_v1.0.md]
    F --> I[build_spec.md]
    I --> J[Drop into<br/>Kiro / Claude Code / Cursor]
```

> Four agents, five artifacts. Agent 3 (Design Brief) synthesizes the PRFAQ and research into a screen inventory, user flows, and design principles. It's optional in the full pipeline — pass `--skip-design` to reproduce the three-agent behavior. Agent 4 produces two artifacts in sequence — the BRD first, then the build spec after you approve the BRD. In the code, Agent 4 is two tasks within one agent, not two separate agents. SVG wireframe generation is coming soon; today Agent 3 produces the design brief only.

You write a short problem statement. The agents do the research, write the Working Backwards document, translate it into requirements, and produce a build spec your engineers (or coding agent) can run with. You stay in the loop at every handoff.

## What This System Is Not

This system does not replace your existing tools:

- **Not a replacement for Jira or Linear.** It produces requirements, not tickets. You take the BRD's user stories and create tickets in your project management tool.
- **Not a replacement for Confluence or Notion.** It generates documents (PRFAQ, BRD) that you publish to your wiki. It references your existing docs rather than duplicating them.
- **Not a replacement for Figma or design tools.** The build spec describes what to build, not how it should look. Design happens alongside or after the BRD.
- **Not a replacement for your coding IDE.** Agent 4 produces a build spec that you load into Kiro, Claude Code, Cursor, or Lovable. The coding happens in your tool of choice.
- **Not a replacement for PM judgment.** Every artifact has a human review checkpoint. The system accelerates your first draft — you own the final version.

This system is the connective layer between research and execution. It takes a product problem and produces the artifacts that bridge the gap between "we should build this" and "here's exactly what to build and why."

## Input Format

The pipeline accepts your product brief as either a markdown file (recommended)
or a YAML file. Both produce identical results — pick whichever your workflow
prefers.

### Markdown (recommended for most PMs)

Copy the template and fill it in:

```bash
cp examples/templates/input-brief-template.md input/my-product.md
```

Open `input/my-product.md` in your text editor or Obsidian and fill in each
section. Then run:

```bash
uv run pm_agent_system full-pipeline input/my-product.md
```

If you use Obsidian with vault integration enabled, the input brief is
automatically copied into your product's vault folder alongside the
generated artifacts.

See [examples/input-brief-example.md](examples/input-brief-example.md) for a
completed reference.

### YAML (for developers and automation)

YAML input is still fully supported for CI/CD pipelines and developers who
prefer it:

```bash
uv run pm_agent_system full-pipeline input/my-product.yaml
```

See [examples/input.yaml](examples/input.yaml) for the YAML format.

> **Note:** JSON input files (`.json`) from earlier versions are no longer
> supported. If you have existing JSON inputs, convert them to markdown or
> YAML format.

## Quick start

Prerequisites: Python 3.11+, [uv](https://github.com/astral-sh/uv), an Anthropic API key, a Tavily API key.

```bash
git clone https://github.com/joegarvey-ai/pm-working-backwards-agent.git
cd pm-working-backwards-agent
crewai install
cp .env.example .env
# Open .env and paste in your ANTHROPIC_API_KEY and TAVILY_API_KEY
uv run pm_agent_system full-pipeline examples/input-brief-example.md
```

The first run takes 5-10 minutes and produces files in `./output/`. See [examples/](examples/) for what those files look like.

If you want to run the test suite locally, also run `uv sync --group dev` — this installs pytest and any other dev-only dependencies. See [CONTRIBUTING.md](CONTRIBUTING.md#running-tests) for the full test workflow.

The `examples/` directory contains sample input files (markdown and YAML), standalone-mode examples, and templates (style guide, customer requirements formats in `examples/templates/`). The `input/` directory is where you put your own input files — see [input/README.md](input/README.md).

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

Input file paths below show `.md` as the primary example. YAML input files (`.yaml`) are also supported — swap the extension and the rest of the command is identical.

| I need to... | Command |
|---|---|
| Validate a product idea with market research | `uv run pm_agent_system research input/my-product.md` |
| Write a stakeholder-ready PRFAQ from scratch | `uv run pm_agent_system generate input/my-product.md` |
| Run the full pipeline end to end | `uv run pm_agent_system full-pipeline input/my-product.md` |
| Revise a PRFAQ after a stakeholder review meeting | `uv run pm_agent_system revise --prfaq-path prfaq_v1.0.md --context-path notes.md` |
| Turn an approved PRFAQ into an engineer-ready BRD | `uv run pm_agent_system brd input/my-product.md --prfaq-path prfaq_v1.2.md` |
| Generate a Kiro build spec from a BRD | `uv run pm_agent_system build-spec --brd-path brd_v1.0.md --target-tool kiro` |
| Update a BRD after engineering feedback | `uv run pm_agent_system revise-brd --brd-path brd_v1.0.md --context-text "FR-003 needs a GSI"` |
| I have my own research and just need a PRFAQ | `uv run pm_agent_system generate input/my-product.md --research-path research.md` |
| I have an approved PRFAQ and my own requirements | `uv run pm_agent_system brd input/my-product.md --prfaq-path prfaq.md --requirements-path requirements.csv` |
| I want to visualize the product before writing requirements | `uv run pm_agent_system wireframes input/my-product.md --prfaq-path prfaq.md` |
| Revise a design brief after a review | `uv run pm_agent_system revise-wireframes --design-brief-path design_brief_v1.0.md --context-text "screen inventory needs a settings page"` |
| Run the full pipeline without the design brief | Add `--skip-design` to the `full-pipeline` command |
| Skip the assumption-challenge step | Add `--skip-validation` to any research/generate/full-pipeline command |
| Compare two document versions after a revision | `uv run pm_agent_system diff output/prfaq_v1.0.md output/prfaq_v1.1.md` |

Each command pauses for your review before producing the next artifact. See the [CLI Commands](#cli-commands) section below for full details, or the [Platform Support](#platform-support) section for non-CLI options.

### Reviewing Output

Every artifact is written to `output/` in two formats: a `.md` file for editing and version control, and a `.html` file for browser viewing. The HTML files are self-contained — you can email them, share them over Slack, or open them offline. Add `--open` to any pipeline command to auto-launch the HTML when the run finishes.

### Obsidian Vault Integration

If you use [Obsidian](https://obsidian.md) for note-taking, artifacts can be
written directly to your vault with frontmatter, version history, and
wikilinks connecting the full artifact chain (research → PRFAQ → design brief → BRD → build spec).

To enable:

1. Set `OBSIDIAN_VAULT_PATH` in your `.env` to your vault's root directory.
2. (Optional) Set `OBSIDIAN_FOLDER_PREFIX` to customize the top-level folder
   name (default: `PM Agent`).

Artifacts are written to `{vault}/{prefix}/{product-slug}/` with:
- The PM's input brief (`input_brief.md`) — copied from your source file with frontmatter so the vault folder holds the complete artifact chain from idea to build spec
- YAML frontmatter (tags, status, version, linked artifacts)
- A dashboard note (`_index.md`) summarizing all artifacts for the product
- Wikilinks connecting each artifact to its upstream and downstream neighbors
- Version history — revisions create new version files rather than overwriting
- A global map of content (`_all_products.md`) listing every product

Two optional fields in your input brief improve organization at scale:
- `Product Name` — a short name for cleaner vault folder slugs (otherwise derived from `Feature / Idea Summary`)
- `Initiative` — groups products into nested folders (e.g., `PM Agent/Commerce Platform/analytics-dashboard/`)

If your vault isn't set up, artifacts are still written to `output/` as usual.
The vault is optional and additive.

## CLI commands

Input file arguments below accept either `.md` (recommended) or `.yaml`/`.yml`.

| Command | What it does |
|---|---|
| `research <input>` | Run Agent 1 only. Produces a research brief. |
| `generate <input>` | Run Agents 1 + 2. Produces a research brief and a PRFAQ v1.0. Pass `--research-path <file>` to reuse an existing research brief and skip Agent 1. |
| `revise --prfaq-path <file>` | Run Agent 2 to revise an existing PRFAQ. Pass `--context-text` or `--context-path` for the revision notes. |
| `wireframes <input> --prfaq-path <file>` | Run Agent 3 only. Produces a design brief from an approved PRFAQ. Pass `--research-path` to ground competitive UI patterns. |
| `revise-wireframes --design-brief-path <file>` | Revise an existing design brief. Pass `--context-text` or `--context-path` for the revision notes. |
| `full-pipeline <input>` | Run all agents end to end. Produces research brief, PRFAQ, design brief, BRD, and build spec. Add `--skip-design` to run the three-agent pipeline without Agent 3. |
| `brd <input> --prfaq-path <file>` | Run Agent 4 to produce a BRD and build spec from an approved PRFAQ. Pass `--design-brief-path` to have the BRD reference screen names and flows, `--verify` to run the advisory PRFAQ check first, and `--sequential-brd` to run the BRD sub-steps sequentially (auto-enabled on Bedrock). |
| `build-spec --brd-path <file>` | Regenerate just the build spec from an approved BRD. Useful when switching `--target-tool`. |
| `revise-brd --brd-path <file>` | Revise an existing BRD. Pass `--context-text` or `--context-path` for the revision notes. |
| `diff <old> <new>` | Compare two document versions section by section. Shows which sections were added, removed, or changed. Works best with agent-generated document pairs — manual header renames between versions appear as a deletion plus an addition rather than a single change. |
| `view <artifact>` | Open a generated artifact in a terminal viewer (requires the `[ui]` extra: `uv pip install 'pm-working-backwards-agent[ui]'`). |
| `feedback status` / `feedback classify` | Show the stakeholder feedback inbox dashboard, or route each open feedback item to the artifacts and sections it affects. |
| `ingest-feedback --source slack --channel <id>` | Pull messages from a Slack channel and write each as an open feedback item into the inbox. Requires the `slack-mcp` binary + Midway. Pass `--since <date>` to bound the range. |
| `clean --archive` / `--list` / `--delete-archive` | Manage the `./output/` directory retention policy. |

Run `uv run pm_agent_system <command> --help` for the full options on any command.

### Write-back commands (internal Amazon only)

These are the **only commands that write outside `./output/`**. Each requires an internal MCP Gateway client binary (`builder-mcp` / `sharepoint-mcp` / `python-pippin-mcp` / `slack-mcp`) on PATH and a live Midway/FedAuth session (`mwinit -f`), and each publishes to an external system only after an **explicit `[y/N]` confirmation that defaults to No**. They are human actions you run *after* approving an artifact — no agent ever publishes or creates tasks autonomously. When the binary or Midway session is absent, they fail soft with a descriptive message and write nothing, exactly like the read integrations.

| Command | What it does |
|---|---|
| `publish-doc --artifact-path <md> [--target quip\|sharepoint\|pippin] [--folder <dest>] [--pippin-project <id>]` | Publish an approved artifact markdown to a document store. Shows a preview, then confirms before writing, and prints the resulting document URL. `quip` and `sharepoint` take an optional `--folder` destination (Quip member IDs / SharePoint site-library-folder path); `pippin` requires `--pippin-project` (or `PIPPIN_PROJECT_ID`). Amazon is migrating off Quip toward SharePoint; Pippin is the canonical PRFAQ/BRD platform. |
| `seed-taskei --brd-path <md> --taskei-room <id> [--dry-run] [--parent-task <id>]` | Create one Taskei task per BRD functional requirement, nested under a parent EPIC (or an existing `--parent-task`). Prints the full plan first; `--dry-run` stops there without writing. `--taskei-room` (or `TASKEI_ROOM_ID`) is required — there is no default room. |
| `ingest-feedback --source slack --channel <id> [--since <date>]` | *(also listed above)* Ingest Slack stakeholder messages into the local feedback inbox. This one writes locally, not to an external system. |

Every BRD generation also produces `brd_*_jira_import.csv` and `brd_*_linear_import.md` files in the output directory, ready to import into Jira or Linear. Column names and field labels are configurable — edit `config/jira_import_schema.yaml` and `config/linear_import_schema.yaml` to match your instance before importing.

### Internal read integrations (optional, Amazon only)

Beyond the write-back commands, several optional **read** tools attach to the agents when their MCP binary is on PATH. Each is gated on binary presence, so the OSS pipeline is unchanged when the binary is absent — no config required. They let the agents ground drafts in internal systems public web search cannot reach:

| Tool | Reads | Attached to |
|---|---|---|
| `builder_mcp` | Internal wikis, code, Taskei, Quip, pipelines | Research, BRD |
| `pippin_read` | Prior PRFAQs/BRDs + reviewer comments from Pippin (read-only) | Research |
| `quicksight_dashboard` | QuickSight dashboard/analysis data (returns CSV file paths, not inline data) | BRD |
| `software_catalog` | The SoftwareCatalog knowledge graph (products, services, features, org, costs) | Research, BRD |
| `working_backwards_ai` / `virtual_pm_critique` | Persona/bar-raiser critique of a PRFAQ draft (two independent lenses) | PRFAQ |
| `outlook_mcp` | Calendar, email metadata, room booking | PRFAQ, BRD |

These are read-only on the agents. Document *creation* (Pippin, SharePoint, Quip) stays in the human-gated `publish-doc` path above, never on an agent. See [docs/internal-mcp-setup.md](docs/internal-mcp-setup.md) for install, auth, and the binary/tool environment overrides.

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
| `MODEL_ROUTING_ENABLED` | no | Set to `true` to enable tiered model routing (Opus for research/PRFAQ, Sonnet for structural tasks, Haiku for classification). Default: off — every agent uses Opus 4.8 (override with `ANTHROPIC_MODEL_ID` / `BEDROCK_MODEL_ID`). |
| `LLM_PROVIDER` | no | `bedrock` or `anthropic`. Defaults to `anthropic`. Bedrock uses `AWS_BEARER_TOKEN_BEDROCK`. |
| `AWS_BEARER_TOKEN_BEDROCK` | no | Bedrock API key (bearer token). Required when `LLM_PROVIDER=bedrock`. |
| `CREW_MAX_RETRIES` | no | Max retries on transient Bedrock errors. Defaults to 5. |

## Architecture

Four agents, each with a single job, chained by a CrewAI orchestrator. Agent 4 produces two artifacts (BRD, then build spec) as two sequential tasks within one agent. Agent 3 is optional; pass `--skip-design` to run the pipeline without it.

Optional tools (in italics) attach only when their credential or MCP binary is present; the pipeline runs without them.

| Agent | Job | Tools |
|---|---|---|
| 1. Research | Gather evidence from web, customer research, and internal notes | Tavily web search, competitive intelligence (G2/Capterra/TrustRadius), prior-art search, file readers, *Dovetail*, *Obsidian*, *builder_mcp*, *pippin_read*, *software_catalog* |
| 2. PRFAQ | Turn the research brief into a Working Backwards press release and FAQ | Style guide loader, file reader, *Obsidian*, *outlook_mcp*, *working_backwards_ai* / *virtual_pm_critique* (persona critique) |
| 3. Design Brief + Wireframe | Synthesizes the PRFAQ and research into a design brief: screen inventory, user flows, design principles, competitive UI patterns. Optionally generates visual wireframes (coming soon). | File reader, *Obsidian* |
| 4. BRD + Build Spec | Translate the approved PRFAQ (and design brief, if present) into requirements (BRD) and format them into a coding-agent-ready build spec | Tavily (cost flags, API doc lookups), AWS Pricing API, AWS docs, requirements reader, style guide, file reader, *Obsidian*, *builder_mcp*, *outlook_mcp*, *quicksight_dashboard*, *software_catalog* |

The orchestrator lives in `src/pm_agent_system/crew.py`. Agent and task definitions are in `src/pm_agent_system/config/agents.yaml` and `tasks.yaml`. Each agent's outputs are validated against a Pydantic model in `src/pm_agent_system/models/`.

A human-in-the-loop checkpoint sits between every stage. The agents do not auto-advance from research to PRFAQ or PRFAQ to BRD. You read the output, decide if it is good, and either approve it or run the `revise` command.

## Observability and Quality

The system includes a harness, evaluation framework, and model routing layer for measuring, replaying, and improving output quality.

### Model Routing

Routing is off by default: every agent runs on Opus 4.8. Set `MODEL_ROUTING_ENABLED=true` in `.env` to automatically route LLM calls to the best model for each task instead:

| Task type | Model | Why |
|---|---|---|
| Research synthesis, PRFAQ writing | Opus | High-stakes creative work, stakeholder-facing |
| External research, BRD, build spec | Sonnet | Structural tasks with explicit schemas |
| Feedback classification | Haiku | Mechanical routing, no creativity needed |

Routing produced +0.8 improvement on PRFAQ fidelity scores (3.2 to 4.0/5) while reducing cost by 60%.

### Harness and Replay

Every pipeline run can be recorded and replayed without API calls:

```bash
# Record a run (writes a golden recording to the given path)
uv run python -c "import yaml; from tests.harness import run_crew; from pm_agent_system.crew import PmAgentSystem; inputs = yaml.safe_load(open('examples/input.yaml')); crew = PmAgentSystem().research_crew(skip_validation=True); run_crew(crew, inputs, output_path='tests/recordings/research_baseline.json')"

# Replay (instant, no API cost)
uv run python -c "import yaml; from tests.harness import run_crew; from pm_agent_system.crew import PmAgentSystem; inputs = yaml.safe_load(open('examples/input.yaml')); crew = PmAgentSystem().research_crew(skip_validation=True); run_crew(crew, inputs, replay_path='tests/recordings/research_baseline.json')"
```

Golden recordings in `tests/recordings/` serve as regression baselines. CI replays them on every push.

### Quality Evals

Three LLM-as-judge evaluators score outputs on a 1-5 rubric:

- **PRFAQ fidelity**: em dashes, contrast hooks, inverted pyramid, paragraph discipline, inline citations
- **Citation accuracy**: sourced claims ratio, citation validity, claim-support strength
- **AWS alignment**: service defaults, unauthorized vendors, specificity

### Verification Gate

An advisory quality gate checks the approved PRFAQ before the BRD stage consumes it. Add `--verify` to the `brd` command:

```bash
uv run pm_agent_system brd input/my-product.md --prfaq-path output/prfaq_v1.0.md --verify
```

It reports style drift, factual inconsistencies, citation loss, and customer-problem grounding failures, then asks before proceeding if it finds an error. It warns rather than hard-blocking, and degrades to a warning if the verifier itself cannot run.

### Trend Reporting and Trace Export

```bash
# Cost/latency/quality trends across recordings. --since filters by
# recording creation date, so widen the window to include older baselines
# (the bundled recordings predate a 7-day window).
uv run python -m pm_agent_system.harness_trends --since 365d

# Visual flamegraph timeline (self-contained HTML)
uv run python -m pm_agent_system.trace_export tests/recordings/prfaq_baseline.json
```

## Known limitations

- The system has been tested on a small number of product problems. It works well for "we want to build X for Y users" but has not been stress-tested on M&A diligence, pricing strategy, or pure platform engineering problems.
- In the OSS default, Agent 1 only knows what it can find via Tavily, Dovetail, your Obsidian vault, and any files you point it at — it cannot access paywalled research or internal systems. (Inside Amazon, the optional internal read integrations extend this to wikis, Pippin, QuickSight, and the software catalog; Slack is available only via the separate `ingest-feedback` command, not to Agent 1 directly.)
- Output quality depends heavily on the input. A vague input gets a vague output. The example in `examples/input.yaml` shows the level of specificity that produces good results.
- A full pipeline run costs roughly $1-3 in API usage at current Claude pricing. Run `research` first if you want a cheap sanity check before committing.
- This is research software. It is not enterprise-ready. There is no auth, no multi-tenancy, no audit log.

## License

[MIT](LICENSE). Use it, fork it, ship it.

## Contributing

Pull requests welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the short version of how to help.
