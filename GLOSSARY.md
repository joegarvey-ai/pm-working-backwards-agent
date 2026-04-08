# Glossary

Plain-English definitions for the terms used in this project. If a term in the README or SETUP isn't here, open an issue and we'll add it.

**Agent.** A program that uses an LLM (here, Claude) to do one specific job. This project has four: Research, PRFAQ, BRD, and Build Spec. Each agent has a role description, instructions, and a set of tools it can call.

**Orchestrator.** The piece of code that decides which agent runs when, and passes the output of one agent to the next. In this project, CrewAI is the orchestrator.

**CrewAI.** An open-source Python framework for building multi-agent systems. It handles the boring parts: passing messages between agents, retrying failed steps, validating outputs. We use it so we don't have to write that infrastructure ourselves. See [crewai.com](https://www.crewai.com/).

**YAML.** A file format for configuration. It looks like a list of `key: value` pairs and is designed to be readable by humans. Our agent definitions and your input files are both YAML.

**API Key.** A long string of characters that proves to an external service (Anthropic, Tavily) that you're allowed to use it. Treat API keys like passwords. Never share them, never commit them to git.

**Pydantic.** A Python library that defines what a piece of data should look like and validates it. We use it to make sure each agent's output has the right shape (e.g., a research brief always has a "Sources" section). If an agent returns the wrong shape, Pydantic catches it before the next agent runs.

**MCP.** Model Context Protocol. A standard for letting LLMs talk to external tools and data sources. The optional Dovetail integration uses MCP under the hood.

**PRFAQ.** "Press Release plus Frequently Asked Questions." An Amazon-popularized format for product proposals. You write the press release as if the product already exists, then a FAQ that answers the hard questions a stakeholder would ask. Forces clarity about what you're really building and why.

**BRD.** "Business Requirements Document." The translation of an approved PRFAQ into specific functional and non-functional requirements that an engineering team can build against. Where the PRFAQ says "merchants can drill into a SKU's funnel," the BRD says "FR-3: Filter by SKU (single or multi-select), priority P0."

**Tavily.** A web search API designed for LLMs. The research agent uses it to find market data, competitor information, and customer reviews on the public internet. See [tavily.com](https://tavily.com).

**Dovetail.** A UX research repository product. If your team uses Dovetail to store customer interview transcripts, the research agent can pull quotes from it. Optional. See [dovetail.com](https://dovetail.com).

**Kiro.** A coding agent IDE built around spec-driven development. The build spec agent can format its output specifically for Kiro's expected spec structure. See [kiro.dev](https://kiro.dev).

**Human-in-the-loop.** A system design where the AI does the heavy lifting but a human reviews and approves at each handoff. In this project, the agents do not auto-advance from research to PRFAQ to BRD. You read each output, decide if it's good, and either approve it or run a `revise` command.

**Working Backwards.** A product development practice where you start by writing the press release for the finished product, then work backward to figure out what you have to build. The PRFAQ is the artifact of Working Backwards. The point is to force you to articulate the customer benefit before you commit any engineering effort.
