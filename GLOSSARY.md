# Glossary

Plain-English definitions for the terms used in this project. If a term in the README or SETUP isn't here, open an issue and we'll add it.

**Agent.** A program that uses an LLM (here, Claude) to do one specific job. This project has three: Research, PRFAQ, and BRD + Build Spec. Each agent has a role description, instructions, and a set of tools it can call.

**API Key.** A long string of characters that proves to an external service (Anthropic, Tavily) that you're allowed to use it. Treat API keys like passwords. Never share them, never commit them to git.

**BRD (Business Requirements Document).** A structured document that translates a product concept into engineer-ready requirements. Includes user stories, functional requirements with acceptance criteria, non-functional requirements, cost flags, and risk assessments. In this system, Agent 3 produces the BRD from an approved PRFAQ. Where the PRFAQ says "merchants can drill into a SKU's funnel," the BRD says "FR-3: Filter by SKU (single or multi-select), priority P0."

**Build Spec.** A formatted document that a coding agent (Kiro, Claude Code, Cursor, or Lovable) can execute against. It contains user flows, feature specs with acceptance criteria, technical constraints, and an architecture reference — everything the coding tool needs to start building. Agent 3 produces this from the approved BRD, formatted for your chosen tool.

**Cost flag.** An entry in the BRD that identifies an architectural decision with cost implications. Cost flags describe the decision, the tradeoff, and specific AWS pricing data — but they do not estimate total project cost. The PM and engineering lead evaluate cost using these flags as a starting point.

**CrewAI.** An open-source Python framework for building multi-agent systems. It handles the boring parts: passing messages between agents, retrying failed steps, validating outputs. We use it so we don't have to write that infrastructure ourselves. See [crewai.com](https://www.crewai.com/).

**Divergence detection.** The mechanism that detects when a PM has edited a vault artifact after the pipeline generated it. Compares a hash of the document body (stored in frontmatter as `original_hash`) against the current body content. Frontmatter-only changes (e.g., changing status from draft to approved) do not trigger divergence — only body edits do. When divergence is detected during a pipeline read, the PM is prompted to choose between the vault version and the output/ version.

**Dovetail.** A UX research repository product. If your team uses Dovetail to store customer interview transcripts, the research agent can pull quotes from it. Optional. See [dovetail.com](https://dovetail.com).

**Frontmatter.** A block of metadata at the top of a markdown file, enclosed in `---` lines, formatted as YAML. Obsidian uses frontmatter for tags, aliases, and custom properties. This system adds artifact type, version, status, and traceability links as frontmatter.

**Human-in-the-loop checkpoint.** A pause between agents where the system stops and waits for your review. You read the output, decide if it's good enough, and either approve it (the next agent runs) or revise it (using the `revise` command). The system never auto-advances from one stage to the next without your approval.

**Input brief.** The starting document you fill out to describe your product idea. Contains your product name, goals, target users, constraints, and any internal context. The pipeline reads this file and uses it as the foundation for all generated artifacts. Can be a markdown file (`.md`, recommended for most PMs) or a YAML file (`.yaml`/`.yml`, recommended for developers and automation). Both formats produce identical results. See `examples/input-brief-example.md` and `examples/input.yaml` for references.

**Kiro.** A coding agent IDE built around spec-driven development. The build spec agent can format its output specifically for Kiro's expected spec structure. See [kiro.dev](https://kiro.dev).

**MCP.** Model Context Protocol. A standard for letting LLMs talk to external tools and data sources. The optional Dovetail integration uses MCP under the hood.

**Obsidian vault.** A folder on your computer that Obsidian uses to store notes as plain markdown files. Each vault is self-contained. In this system, setting `OBSIDIAN_VAULT_PATH` tells the pipeline to write artifact copies into your vault for easy editing and navigation.

**Orchestrator.** The piece of code that decides which agent runs when, and passes the output of one agent to the next. In this project, CrewAI is the orchestrator.

**PRFAQ (Press Release / Frequently Asked Questions).** A product planning document popularized by Amazon's "Working Backwards" process. You write a fictional press release announcing the product as if it already launched, then answer the hard questions (from customers and stakeholders) in an FAQ section. The idea is to force clarity about what you're building and why before any engineering starts. In this system, Agent 2 produces the PRFAQ from approved research.

**Pydantic.** A Python library that defines what a piece of data should look like and validates it. We use it to make sure each agent's output has the right shape (e.g., a research brief always has a "Sources" section). If an agent returns the wrong shape, Pydantic catches it before the next agent runs.

**Reconciliation (requirements).** When you provide a pre-existing requirements file via `--requirements-path`, Agent 3 compares your requirements against the approved PRFAQ. Requirements that align are kept. Requirements that contradict the PRFAQ are flagged. Gaps in your list (requirements implied by the PRFAQ but not in your file) are filled by the agent and marked as "agent-generated."

**Tavily.** A web search API designed for LLMs. The research agent uses it to find market data, competitor information, and customer reviews on the public internet. See [tavily.com](https://tavily.com).

**Wikilink.** A link between notes in Obsidian, written as `[[note name]]`. This system uses wikilinks to connect the artifact chain so you can navigate from research to PRFAQ to BRD to build spec using Obsidian's graph view.

**Working Backwards.** A product development approach where you start from the customer experience and work backward to the technology required to deliver it. The PRFAQ is the primary artifact of this process. This system automates the first draft of the Working Backwards artifacts.

**YAML.** A file format for configuration. It looks like a list of `key: value` pairs and is designed to be readable by humans. Our agent definitions and your input files are both YAML.
