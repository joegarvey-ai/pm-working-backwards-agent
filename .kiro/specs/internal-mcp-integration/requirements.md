# Requirements Document

## Introduction

This feature integrates three internal Amazon MCP servers into the existing PM Working Backwards multi-agent CrewAI pipeline. The three MCPs are:

1. **builder-mcp**: Pulls data and content from internal Amazon systems including wikis, code search, Taskei, Quip, and pipelines.
2. **aws-outlook-mcp**: Provides calendar, email, and room booking access via Outlook.
3. **midway cookie sharing**: A single `mwinit -f` command refreshes authentication cookies for both Windows and WSL environments.

Each MCP follows the same optional-tool pattern established by the Dovetail integration: when the relevant environment variable or token is unset, the tool is silently skipped and the pipeline continues without it. The integration enriches existing agent outputs (research briefs, PRFAQs, BRDs, build specs) with internal Amazon context, stakeholder scheduling data, and simplified cross-platform authentication.

All three integrations are additive. No existing agent behavior changes when the MCPs are unavailable. The pipeline remains fully functional for users who do not have access to these internal systems.

## Glossary

- **Builder_MCP**: The internal Amazon MCP server that provides access to wikis, code search, Taskei task tracking, Quip documents, and pipeline data.
- **Outlook_MCP**: The aws-outlook-mcp server that provides calendar, email, and room booking access via Microsoft Outlook.
- **Midway_Cookie_Sharing**: The authentication mechanism where a single `mwinit -f` command refreshes cookies for both Windows and WSL, enabling MCP servers to authenticate without separate credential flows.
- **Research_Agent**: The existing CrewAI agent (external_research_agent) that gathers public market data and competitive intelligence using Tavily and CompetitiveIntelTool.
- **PRFAQ_Agent**: The existing CrewAI agent that produces Working Backwards documents validated against PRFAQOutput.
- **BRD_Agent**: The existing CrewAI agent that produces BRDOutput with requirements, cost flags, and build specs.
- **BRD_Compliance_Agent**: The existing async BRD agent that produces BRDComplianceOutput.
- **Pipeline**: The full agent sequence: Research Agent, PRFAQ Agent, BRD Agent, Build Spec.
- **Optional_Tool_Pattern**: The established code pattern where a tool is conditionally attached to an agent based on the presence of an environment variable (e.g., DOVETAIL_API_TOKEN). When unset, the tool is not loaded and the agent proceeds without it.
- **CrewAI_Tool**: A Python class extending `crewai.tools.BaseTool` with a name, description, args_schema, and `_run` method.
- **Builder_MCP_Endpoint**: The JSON-RPC endpoint URL for the builder-mcp server, configured via environment variable.
- **Outlook_MCP_Endpoint**: The JSON-RPC endpoint URL for the aws-outlook-mcp server, configured via environment variable.
- **Banned_Word_List**: The project-standard list of prohibited words enforced across agent prompts and outputs.

## Scope Summary

- **MUST-have (Priority 1)**: Requirements 1 through 8 cover the builder-mcp tool, Outlook MCP tool, midway cookie sharing, environment configuration, error handling, agent prompt updates, and the optional-tool wiring in crew.py.
- **SHOULD-have (Priority 2)**: Requirements 9 and 10 cover output schema extensions and renderer updates for surfacing MCP-sourced content in artifacts.
- **NICE-to-have (Priority 3)**: Requirement 11 covers unit and integration tests. Requirement 12 captures deferred future work.

## Requirements

### Requirement 1: Builder MCP CrewAI Tool

**User Story:** As a PM using the pipeline inside Amazon, I want the research agent to pull data from internal wikis, code search, Taskei, and Quip, so that the research brief includes internal context that public search cannot reach.

#### Acceptance Criteria

1. THE `src/pm_agent_system/tools/` directory SHALL contain a `builder_mcp.py` module that defines a `BuilderMCPTool` class extending `crewai.tools.BaseTool`.
2. THE BuilderMCPTool SHALL support the following actions: `wiki_search`, `code_search`, `taskei_search`, `quip_search`, and `pipeline_search`.
3. WHEN the BuilderMCPTool receives a valid action and query, THE BuilderMCPTool SHALL send a JSON-RPC request to the Builder_MCP_Endpoint and return the text content from the response.
4. THE BuilderMCPTool SHALL define a Pydantic `args_schema` with required fields for `query` and `action`, and optional fields for resource-specific identifiers (e.g., `project_id`, `document_id`).
5. THE BuilderMCPTool SHALL use `httpx` for HTTP calls and `tenacity` for retry logic, matching the patterns in `dovetail_research.py`.

### Requirement 2: Builder MCP Optional Wiring

**User Story:** As an engineer, I want the builder-mcp tool to follow the optional-tool pattern, so that the pipeline works identically for users without access to internal Amazon systems.

#### Acceptance Criteria

1. THE `src/pm_agent_system/crew.py` module SHALL attach BuilderMCPTool to the `external_research_agent` only when the `BUILDER_MCP_TOKEN` environment variable is set and non-empty.
2. IF `BUILDER_MCP_TOKEN` is unset or empty, THEN THE `external_research_agent` SHALL be constructed without BuilderMCPTool and SHALL operate using only its existing tools (TavilySearchTool, CompetitiveIntelTool, FileReaderTool, PriorArtSearchTool, ObsidianSearchTool, ObsidianReadTool).
3. THE `src/pm_agent_system/crew.py` module SHALL also conditionally attach BuilderMCPTool to the `brd_agent` when `BUILDER_MCP_TOKEN` is set, so that the BRD stage can reference internal wiki and code search data for technical context and prior art.
4. THE conditional attachment logic SHALL follow the same pattern used for DovetailSearchTool on the `customer_evidence_agent`.

### Requirement 3: Outlook MCP CrewAI Tool

**User Story:** As a PM, I want the pipeline to access my Outlook calendar, email, and room booking data, so that stakeholder analysis, timeline planning, and meeting coordination are informed by real scheduling context.

#### Acceptance Criteria

1. THE `src/pm_agent_system/tools/` directory SHALL contain an `outlook_mcp.py` module that defines an `OutlookMCPTool` class extending `crewai.tools.BaseTool`.
2. THE OutlookMCPTool SHALL support the following actions: `calendar_search`, `email_search`, `room_availability`, and `schedule_summary`.
3. WHEN the OutlookMCPTool receives a valid action and query, THE OutlookMCPTool SHALL send a JSON-RPC request to the Outlook_MCP_Endpoint and return the text content from the response.
4. THE OutlookMCPTool SHALL define a Pydantic `args_schema` with required fields for `query` and `action`, and optional fields for date ranges and participant filters.
5. THE OutlookMCPTool SHALL use `httpx` for HTTP calls and `tenacity` for retry logic, matching the patterns in `dovetail_research.py`.
6. THE OutlookMCPTool SHALL NOT expose raw email body content in agent output. THE OutlookMCPTool SHALL return only metadata (subject, sender, date, recipients) and summaries for email search results.

### Requirement 4: Outlook MCP Optional Wiring

**User Story:** As an engineer, I want the Outlook MCP tool to follow the optional-tool pattern, so that the pipeline works for users without Outlook MCP access.

#### Acceptance Criteria

1. THE `src/pm_agent_system/crew.py` module SHALL attach OutlookMCPTool to the `prfaq_agent` only when the `OUTLOOK_MCP_TOKEN` environment variable is set and non-empty.
2. THE `src/pm_agent_system/crew.py` module SHALL also conditionally attach OutlookMCPTool to the `brd_agent` when `OUTLOOK_MCP_TOKEN` is set, so that the BRD stage can reference stakeholder availability for timeline and milestone planning.
3. IF `OUTLOOK_MCP_TOKEN` is unset or empty, THEN THE `prfaq_agent` and `brd_agent` SHALL be constructed without OutlookMCPTool and SHALL operate using only their existing tools.
4. THE conditional attachment logic SHALL follow the same pattern used for DovetailSearchTool on the `customer_evidence_agent`.

### Requirement 5: Midway Cookie Sharing Configuration

**User Story:** As a developer working across Windows and WSL, I want a single `mwinit -f` command to refresh authentication cookies for both environments, so that I do not need separate credential flows for each MCP server.

#### Acceptance Criteria

1. THE `.env.example` file SHALL document the `MIDWAY_COOKIE_PATH` environment variable with a comment explaining that it points to the shared cookie file location accessible from both Windows and WSL.
2. WHEN `MIDWAY_COOKIE_PATH` is set, THE BuilderMCPTool and OutlookMCPTool SHALL read authentication cookies from the specified path instead of requiring separate token environment variables.
3. IF `MIDWAY_COOKIE_PATH` is set and the cookie file exists, THEN THE BuilderMCPTool SHALL use the cookie for authentication with the Builder_MCP_Endpoint.
4. IF `MIDWAY_COOKIE_PATH` is set and the cookie file exists, THEN THE OutlookMCPTool SHALL use the cookie for authentication with the Outlook_MCP_Endpoint.
5. IF `MIDWAY_COOKIE_PATH` is set but the cookie file does not exist or is expired, THEN THE tools SHALL log a warning and fall back to the token-based authentication path (BUILDER_MCP_TOKEN, OUTLOOK_MCP_TOKEN).
6. THE `docs/pm-pilot-getting-started-v2.md` or a new `docs/internal-mcp-setup.md` file SHALL document the `mwinit -f` workflow for refreshing cookies across Windows and WSL.

### Requirement 6: Environment Variable Configuration

**User Story:** As an engineer setting up the pipeline, I want all MCP configuration centralized in `.env` with sensible defaults, so that setup follows the existing pattern.

#### Acceptance Criteria

1. THE `.env.example` file SHALL document the following new environment variables: `BUILDER_MCP_TOKEN`, `BUILDER_MCP_ENDPOINT`, `OUTLOOK_MCP_TOKEN`, `OUTLOOK_MCP_ENDPOINT`, and `MIDWAY_COOKIE_PATH`.
2. THE `BUILDER_MCP_ENDPOINT` variable SHALL default to a placeholder URL with a comment indicating the user must set it to their internal endpoint.
3. THE `OUTLOOK_MCP_ENDPOINT` variable SHALL default to a placeholder URL with a comment indicating the user must set it to their internal endpoint.
4. WHEN any MCP token or endpoint variable is unset, THE pipeline SHALL log a single informational message at startup noting which optional integrations are disabled, and SHALL NOT log repeated warnings during execution.
5. THE `scripts/check_env.py` script SHALL validate the new environment variables and report their status (set, unset, or misconfigured) alongside existing variable checks.

### Requirement 7: Error Handling for MCP Unavailability

**User Story:** As a PM, I want the pipeline to continue producing artifacts when an MCP server is down or unreachable, so that a transient infrastructure issue does not block my work.

#### Acceptance Criteria

1. IF the Builder_MCP_Endpoint returns an HTTP error or times out, THEN THE BuilderMCPTool SHALL return a descriptive error string to the agent and SHALL NOT raise an unhandled exception.
2. IF the Outlook_MCP_Endpoint returns an HTTP error or times out, THEN THE OutlookMCPTool SHALL return a descriptive error string to the agent and SHALL NOT raise an unhandled exception.
3. WHEN an MCP tool returns an error, THE agent consuming the tool SHALL note the unavailability in its output gaps section and SHALL continue producing the artifact using other available data sources.
4. THE BuilderMCPTool SHALL use a configurable timeout (default 30 seconds) and retry up to 3 times with exponential backoff before returning an error, matching the Dovetail retry pattern.
5. THE OutlookMCPTool SHALL use a configurable timeout (default 30 seconds) and retry up to 3 times with exponential backoff before returning an error, matching the Dovetail retry pattern.
6. THE BuilderMCPTool and OutlookMCPTool SHALL each log tool invocations and responses to a dedicated log file under `output/` (e.g., `builder_mcp_calls.log`, `outlook_mcp_calls.log`), following the Dovetail call-logging pattern.

### Requirement 8: Agent Prompt Updates for MCP Context

**User Story:** As a PM, I want the agent prompts to instruct agents on how to use the new MCP tools, so that agents query internal systems when the tools are available and note their absence when they are not.

#### Acceptance Criteria

1. THE `external_research_agent` backstory in `agents.yaml` SHALL include instructions to use BuilderMCPTool for internal wiki, code search, and Taskei data when the tool is available, and to note in `external_gaps` when it is not.
2. THE `prfaq_agent` backstory in `agents.yaml` SHALL include instructions to use OutlookMCPTool for stakeholder scheduling context when the tool is available, and to proceed without scheduling data when it is not.
3. THE `brd_agent` backstory in `agents.yaml` SHALL include instructions to use BuilderMCPTool for internal technical context and prior art, and OutlookMCPTool for stakeholder availability in timeline planning, when those tools are available.
4. THE task descriptions in `tasks.yaml` for `external_research_task`, `research_synthesis_task`, `generate_prfaq`, and BRD tasks SHALL reference the new MCP tools as optional data sources with instructions on how to incorporate their output.
5. THE agent prompts SHALL NOT assume MCP tools are always present. THE prompts SHALL use conditional language (e.g., "If the builder_mcp tool is available, use it to...").

### Requirement 9: Research Output Schema Extension for Internal Sources (SHOULD)

**User Story:** As a PM, I want the research brief to distinguish internal sources from external sources, so that I can see which findings came from internal Amazon systems and which came from public research.

#### Acceptance Criteria

1. WHERE this requirement is approved for implementation, THE `ResearchOutput` model in `src/pm_agent_system/models/research_output.py` SHALL include an `internal_sources` field that lists sources retrieved from Builder_MCP, separate from the existing `sources` field.
2. WHERE this requirement is approved for implementation, THE `ExternalResearchOutput` model in `src/pm_agent_system/models/research_intermediate.py` SHALL include an `internal_findings` field for wiki, code search, Taskei, and Quip results.
3. WHERE this requirement is approved for implementation, THE `render_research_to_markdown` function SHALL render internal sources in a dedicated "Internal Sources" subsection within the Sources section.
4. WHERE this requirement is deferred, THE BuilderMCPTool output SHALL be incorporated into the existing `context` and `sources` fields without schema changes, and all other requirements SHALL remain satisfiable.

### Requirement 10: PRFAQ and BRD Renderer Updates for MCP Content (SHOULD)

**User Story:** As a PM, I want MCP-sourced content to appear in the rendered markdown artifacts, so that stakeholders reviewing the PRFAQ or BRD can see internal context alongside external research.

#### Acceptance Criteria

1. WHERE this requirement is approved for implementation, THE `render_prfaq_to_markdown` function SHALL render stakeholder scheduling context (from Outlook MCP) in the Internal FAQ section when present.
2. WHERE this requirement is approved for implementation, THE `render_brd_to_markdown` function SHALL render internal technical context (from Builder MCP) in the Technical Context section when present.
3. WHERE this requirement is approved for implementation, THE `render_brd_to_markdown` function SHALL render stakeholder availability data in the Timeline and Milestones section when present.
4. WHERE this requirement is deferred, THE MCP-sourced content SHALL be incorporated into existing prose fields by the agents without renderer changes, and all other requirements SHALL remain satisfiable.

### Requirement 11: Unit and Integration Tests (NICE)

**User Story:** As an engineer, I want tests that cover the new MCP tools, optional wiring, and error handling, so that regressions are caught early and the team can maintain the integration with confidence.

#### Acceptance Criteria

1. THE test suite under `tests/` SHALL include a unit test module that validates BuilderMCPTool returns expected output for mocked JSON-RPC responses and returns a descriptive error string for HTTP errors.
2. THE test suite SHALL include a unit test module that validates OutlookMCPTool returns expected output for mocked JSON-RPC responses and returns a descriptive error string for HTTP errors.
3. THE test suite SHALL include a test that validates the optional-tool wiring: when `BUILDER_MCP_TOKEN` is unset, the `external_research_agent` tool list SHALL NOT contain BuilderMCPTool.
4. THE test suite SHALL include a test that validates the optional-tool wiring: when `OUTLOOK_MCP_TOKEN` is unset, the `prfaq_agent` tool list SHALL NOT contain OutlookMCPTool.
5. THE test suite SHALL include a test that validates midway cookie fallback: when `MIDWAY_COOKIE_PATH` points to a nonexistent file, the tools SHALL fall back to token-based authentication.
6. THE test suite SHALL include a test that runs the pipeline with all MCP tokens unset and asserts that the pipeline completes without raising.

### Requirement 12: Deferred Future Work (NICE)

**User Story:** As a PM, I want future-work items captured in the spec, so that scope stays controlled now and the backlog is visible.

#### Acceptance Criteria

1. THE requirements document SHALL record the following items as out of scope for this feature: a dedicated "internal research agent" that runs as a separate async sibling (like the Dovetail customer_evidence_agent), auto-scheduling of stakeholder review meetings via Outlook MCP, pipeline status integration with Taskei (e.g., auto-creating Taskei tasks from BRD requirements), Quip document generation (writing PRFAQs or BRDs directly to Quip), and a CLI subcommand for MCP health checks.
2. THE requirements document SHALL NOT expand scope to include the deferred items unless the PM explicitly reopens scope in a later spec.
