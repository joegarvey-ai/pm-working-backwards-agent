# Implementation Plan: Internal MCP Integration

## Overview

This plan integrates three internal Amazon MCP servers (builder-mcp, aws-outlook-mcp, midway cookie sharing) into the existing PM Working Backwards CrewAI pipeline, following the Dovetail optional-tool pattern as the reference for every detail. The implementation lands in strict dependency order: the shared `_mcp_jsonrpc.py` helper first (consumed by both tools), then `BuilderMCPTool` and `OutlookMCPTool` (each with its own property and example tests), then conditional crew wiring with predicates, then agent and task prompt updates, then env config and docs, then the optional Requirement 9 and 10 schema and renderer extensions, and finally integration and smoke tests.

The implementation language is Python 3.11+, matching the existing codebase. The design uses concrete Python examples, so no language-selection question is needed.

Testing follows the project's existing convention (`uv run pytest tests/`) with fixtures under `tests/fixtures/` and property-based tests powered by `hypothesis` (already in the `dev` dependency group of `pyproject.toml`). Property tests are scoped to the eight correctness properties named in the design document. HTTP calls are mocked at the `httpx.post` level; no test calls a real MCP server.

Requirement 12 (Deferred Future Work) is intentionally out of scope for this task list. Requirements 9 and 10 are SHOULD-have; their tasks are marked optional so MUST-have tasks alone produce a complete, shippable feature.

## Tasks

- [x] 1. Implement the shared `_mcp_jsonrpc.py` helper module
  - [x] 1.1 Create `src/pm_agent_system/tools/_mcp_jsonrpc.py` with the `MCPAuth` dataclass and core functions
    - Add the frozen `MCPAuth` dataclass with `bearer_token: Optional[str]` and `cookie_header: Optional[str]` fields
    - Implement `jsonrpc_envelope(tool_name, arguments, request_id=1) -> dict` returning `{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": tool_name, "arguments": arguments}, "id": request_id}` exactly as specified in the design
    - Implement `extract_text(response_json) -> str` mirroring `DovetailSearchTool._extract_text` (joins `result.content[*].text` with `"\n\n---\n\n"`, returns `""` on empty)
    - Implement `build_headers(auth: MCPAuth) -> dict` producing `Content-Type: application/json`, `Accept: application/json, text/event-stream`, plus either `Authorization: Bearer {token}` or `Cookie: {cookie_header}` based on which field is set
    - Module uses a leading underscore so `tools/__init__.py` does not re-export it
    - _Requirements: 1.3, 1.5, 3.3, 3.5_
  - [x] 1.2 Implement `resolve_auth` with cookie-first, token-fallback precedence
    - `resolve_auth(cookie_path_env: str, token_env: str, logger) -> MCPAuth` reads `os.getenv(cookie_path_env)` first
    - When the cookie path is set and the file exists and is non-empty, read its contents and return `MCPAuth(bearer_token=None, cookie_header=<contents>)`
    - When the cookie path is set but the file is missing or empty, log a warning-level record and fall through to the token path
    - When `os.getenv(token_env)` is non-empty, return `MCPAuth(bearer_token=<token>, cookie_header=None)`
    - Otherwise return `MCPAuth(bearer_token=None, cookie_header=None)` (caller converts this to an auth error string)
    - Resolve on every call; do not cache (cookies expire)
    - _Requirements: 5.2, 5.3, 5.4, 5.5_
  - [x] 1.3 Implement `post_with_retry` and `call_mcp`
    - `post_with_retry(url, json_payload, headers, timeout)` wrapped with `@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)`, calls `httpx.post(...)` then `response.raise_for_status()`
    - `call_mcp(endpoint_url, auth, tool_name, arguments, timeout=30.0) -> str` builds the envelope, builds headers, calls `post_with_retry`, extracts text, returns the text string
    - Raises `httpx.HTTPStatusError` or the underlying exception on final failure; callers convert to descriptive error strings
    - _Requirements: 1.3, 1.5, 3.3, 3.5, 7.4, 7.5_
  - [x] 1.4 Implement `log_call` for per-tool JSONL call logs
    - `log_call(log_path: Path, event: str, details: dict) -> None` appends one JSON line (timestamp + event + details) to the given path
    - Creates parent directories as needed and swallows all exceptions (logging must never break a tool), matching the Dovetail `_log_call` contract
    - _Requirements: 7.6_
  - [x] 1.5 Property test for Property 1: JSON-RPC envelope structural invariants
    - Add `tests/tools/test_mcp_jsonrpc_properties.py::test_property_1_envelope_invariants`
    - **Property 1: JSON-RPC envelope structural invariants**
    - **Validates: Requirements 1.3, 3.3**
  - [x] 1.6 Property test for Property 7: auth resolver precedence
    - Add `tests/tools/test_mcp_jsonrpc_properties.py::test_property_7_auth_resolver_precedence`
    - Parameterize via Hypothesis over `cookie_path_state in {unset, set-and-missing, set-and-present-with-content}` and `token_state in {unset, empty, non-empty}`
    - Use `tmp_path` for cookie file presence; use `monkeypatch` for env vars; capture logs with `caplog` and assert a warning is emitted for the set-and-missing case
    - **Property 7: Auth resolver precedence**
    - **Validates: Requirements 5.2, 5.3, 5.4, 5.5**
  - [x] 1.7 Unit tests for `extract_text` and `log_call`
    - Add `tests/tools/test_mcp_jsonrpc.py` covering: `extract_text` on representative MCP response shapes (single text, multi-text, empty content, missing keys); `log_call` writes exactly one JSON line per call and swallows exceptions (for example, when the directory cannot be created)
    - _Requirements: 7.6_

- [x] 2. Implement `BuilderMCPTool`
  - [x] 2.1 Create `src/pm_agent_system/tools/builder_mcp.py` with the `BuilderMCPInput` args schema
    - Implement the Pydantic schema exactly as in the design: required `query: str`, `action: str = "wiki_search"`, optional `project_id: str = ""`, `document_id: str = ""`, `limit: int = 10`
    - Field descriptions enumerate valid action values: `wiki_search`, `code_search`, `taskei_search`, `quip_search`, `pipeline_search`
    - _Requirements: 1.1, 1.2, 1.4_
  - [x] 2.2 Implement the `BuilderMCPTool` class and its `_run` method
    - Extends `crewai.tools.BaseTool` with `name = "builder_mcp"`, a description naming its five actions, and `args_schema = BuilderMCPInput`
    - `_run` flow: `log_call("invocation", ...)` to `output/builder_mcp_calls.log`, call `resolve_auth("MIDWAY_COOKIE_PATH", "BUILDER_MCP_TOKEN", logger)`, read `BUILDER_MCP_ENDPOINT` from env (no default; return descriptive error when unset), dispatch on `action` to build the arguments dict, call `_mcp_jsonrpc.call_mcp(endpoint, auth, remote_tool_name, args, timeout=30.0)`, `log_call("response", ...)` with the first 300 chars
    - Error paths: auth failure returns `"BUILDER_MCP_TOKEN not set in environment variables; set token or MIDWAY_COOKIE_PATH to enable builder_mcp."`; `httpx.HTTPStatusError` returns `"Builder MCP error (HTTP {status}): {body[:300]}"`; generic `Exception` returns `"Error connecting to builder_mcp: {e}"`. `_run` never raises
    - `limit` is clamped to `max(1, min(int(limit or 10), 100))` before dispatch
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 5.2, 5.3, 5.5, 6.4, 7.1, 7.4, 7.6_
  - [x] 2.3 Implement `_dispatch` with the action-to-remote-tool mapping
    - Dispatch map: `wiki_search` → `search_wiki`, `code_search` → `search_code`, `taskei_search` → `search_taskei`, `quip_search` → `search_quip`, `pipeline_search` → `search_pipelines`
    - Each action builds its arguments dict from `query`, `limit`, and the optional `project_id`/`document_id` per the action mapping table in the design
    - Unknown action returns a descriptive error string listing the five valid actions
    - _Requirements: 1.2_
  - [x] 2.4 Export `BuilderMCPTool` from `tools/__init__.py`
    - Add `from pm_agent_system.tools.builder_mcp import BuilderMCPTool` and append to `__all__`
    - Do not re-export `_mcp_jsonrpc` (private)
    - _Requirements: 1.1_
  - [x] 2.5 Property test for Property 2: `BuilderMCPInput` args schema validation
    - Add `tests/tools/test_builder_mcp_properties.py::test_property_2_builder_input_validation`
    - Hypothesis strategy covers valid inputs (required `query`, `action` from the five-value set, optional `project_id`, `document_id`, `limit` in `[1, 100]`) and invalid inputs (missing `query`)
    - **Property 2: BuilderMCPInput args_schema validation**
    - **Validates: Requirements 1.4**
  - [x] 2.6 Property test for Property 8 (Builder half): `_run` never raises on transport errors
    - Add `tests/tools/test_builder_mcp_properties.py::test_property_8_builder_run_never_raises`
    - Mock `_mcp_jsonrpc.call_mcp` to raise `httpx.HTTPStatusError` (any status), `httpx.TimeoutException`, `httpx.ConnectError`, or a generic `Exception`; assert `_run` returns a non-empty string in every case
    - **Property 8: MCP tool `_run` never raises on error (Builder half)**
    - **Validates: Requirements 7.1**
  - [x] 2.7 Unit tests for `BuilderMCPTool` action mapping, retry, timeout, and call logging
    - Add `tests/tools/test_builder_mcp.py` with: one mocked MCP response per action asserting the remote tool name in the outgoing payload matches the mapping; a retry test asserting three attempts on transient HTTP 500 then the final error string; a timeout test asserting the default 30-second timeout reaches `httpx.post`; a call-log test asserting one JSON line each for invocation and response events under `output/builder_mcp_calls.log`
    - Use `respx` or `pytest-mock` to mock `httpx.post`
    - _Requirements: 1.2, 1.3, 7.4, 7.6_

- [x] 3. Implement `OutlookMCPTool` with email privacy scrubbing
  - [x] 3.1 Create `src/pm_agent_system/tools/outlook_mcp.py` with the `OutlookMCPInput` args schema
    - Implement the Pydantic schema exactly as in the design: required `query: str`, `action: str = "calendar_search"`, optional `start_date: str = ""`, `end_date: str = ""`, `participants: str = ""`, `limit: int = 10`
    - Field descriptions enumerate valid action values: `calendar_search`, `email_search`, `room_availability`, `schedule_summary`
    - _Requirements: 3.1, 3.2, 3.4_
  - [x] 3.2 Implement the `OutlookMCPTool` class, `_run`, and `_dispatch`
    - Mirrors the Builder shape: `log_call("invocation", ...)` to `output/outlook_mcp_calls.log`, call `resolve_auth("MIDWAY_COOKIE_PATH", "OUTLOOK_MCP_TOKEN", logger)`, read `OUTLOOK_MCP_ENDPOINT` from env, dispatch, `call_mcp(..., timeout=30.0)`, log response
    - Error paths mirror Builder with `OUTLOOK_MCP_TOKEN` and `outlook_mcp` substituted; `_run` never raises
    - Dispatch map: `calendar_search` → `search_calendar`, `email_search` → `search_email`, `room_availability` → `check_room_availability`, `schedule_summary` → `summarize_schedule`
    - Each action builds its arguments dict from `query`, `limit`, and the optional date/participant fields per the action mapping table in the design
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 5.2, 5.3, 5.5, 6.4, 7.2, 7.5, 7.6_
  - [x] 3.3 Implement `_scrub_email_bodies` for the `email_search` action
    - `_scrub_email_bodies(raw_text: str) -> str` parses the MCP response JSON, recursively walks nested dicts and lists at any depth, drops any occurrence of the keys `body`, `body_preview`, or `body_html`, and preserves `subject`, `from`, `date`, `to`, `cc`, and `summary` (or a first-200-character `preview` when `summary` is absent), then re-serializes
    - When the raw response shape is unrecognized (non-JSON or missing expected keys), return a conservative error string rather than forwarding the raw body
    - `email_search` is the only action that runs through the scrubber; other actions return the raw extracted text unchanged
    - _Requirements: 3.6_
  - [x] 3.4 Export `OutlookMCPTool` from `tools/__init__.py`
    - Add `from pm_agent_system.tools.outlook_mcp import OutlookMCPTool` and append to `__all__`
    - _Requirements: 3.1_
  - [x] 3.5 Property test for Property 3: `OutlookMCPInput` args schema validation
    - Add `tests/tools/test_outlook_mcp_properties.py::test_property_3_outlook_input_validation`
    - Hypothesis strategy covers valid inputs (required `query`, `action` from the four-value set, optional ISO-8601 dates, comma-separated `participants`, `limit` in `[1, 100]`) and invalid inputs (missing `query`)
    - **Property 3: OutlookMCPInput args_schema validation**
    - **Validates: Requirements 3.4**
  - [x] 3.6 Property test for Property 6: email body scrubbing at any depth
    - Add `tests/tools/test_outlook_mcp_properties.py::test_property_6_email_body_scrubbing`
    - Hypothesis strategy generates arbitrary nested JSON structures with any subset of `body`, `body_preview`, `body_html` keys at any depth; assert `json.loads(_scrub_email_bodies(json.dumps(input)))` contains none of those three keys at any depth and that preserved keys round-trip unchanged
    - **Property 6: Email body scrubbing**
    - **Validates: Requirements 3.6**
  - [x] 3.7 Property test for Property 8 (Outlook half): `_run` never raises on transport errors
    - Add `tests/tools/test_outlook_mcp_properties.py::test_property_8_outlook_run_never_raises`
    - Same structure as the Builder half (task 2.6) with `OutlookMCPTool._run` substituted
    - **Property 8: MCP tool `_run` never raises on error (Outlook half)**
    - **Validates: Requirements 7.2**
  - [x] 3.8 Unit tests for `OutlookMCPTool` action mapping, retry, timeout, scrubber, and call logging
    - Add `tests/tools/test_outlook_mcp.py` mirroring `tests/tools/test_builder_mcp.py` with: one mocked response per action asserting remote-tool-name routing; a retry test; a timeout test; a call-log test under `output/outlook_mcp_calls.log`; a scrubber example test that feeds a realistic `email_search` MCP response with a `body` field and asserts the returned string contains `subject`, `from`, `date` but no `body`, `body_preview`, `body_html`; a scrubber conservative-fallback test for an unrecognized response shape
    - _Requirements: 3.2, 3.3, 3.6, 7.5, 7.6_

- [x] 4. Checkpoint - tools are self-contained and verified
  - Ensure all tests pass with `uv run pytest tests/`, ask the user if questions arise.

- [x] 5. Wire the MCP tools into crew agents with conditional predicates
  - [x] 5.1 Add `_builder_mcp_enabled` and `_outlook_mcp_enabled` predicates in `crew.py`
    - Implement `_builder_mcp_enabled() -> bool`: returns True when `BUILDER_MCP_TOKEN` is set and non-empty, or when `MIDWAY_COOKIE_PATH` is set and the file exists
    - Implement `_outlook_mcp_enabled() -> bool`: same logic with `OUTLOOK_MCP_TOKEN`
    - Place the predicates at module scope near the existing `_llm` helper; import `pathlib.Path` if not already imported
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 4.1, 4.2, 4.3, 4.4, 5.2, 5.3, 5.4_
  - [x] 5.2 Attach `BuilderMCPTool` to `external_research_agent` and `brd_agent` conditionally
    - Edit `external_research_agent`: build `tools` as a list, append `BuilderMCPTool()` when `_builder_mcp_enabled()` returns True
    - Edit `brd_agent`: same pattern, append `BuilderMCPTool()` when the predicate returns True
    - Do not change any other agent's tool list; do not remove any existing tool
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [x] 5.3 Attach `OutlookMCPTool` to `prfaq_agent` and `brd_agent` conditionally
    - Edit `prfaq_agent`: build `tools` as a list, append `OutlookMCPTool()` when `_outlook_mcp_enabled()` returns True
    - Edit `brd_agent`: append `OutlookMCPTool()` when `_outlook_mcp_enabled()` returns True (in addition to the Builder attachment from task 5.2)
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - [x] 5.4 Import `BuilderMCPTool` and `OutlookMCPTool` in `crew.py`
    - Extend the `from pm_agent_system.tools import (...)` block with `BuilderMCPTool` and `OutlookMCPTool`
    - Keep the import list alphabetized to match existing convention
    - _Requirements: 2.1, 4.1_
  - [x] 5.5 Add a single startup log line naming which optional integrations are enabled
    - In `PmAgentSystem.__init__` (or a module-level helper invoked from `main.py` startup), log one informational line such as `"Optional integrations: builder_mcp=<enabled|disabled>, outlook_mcp=<enabled|disabled>, dovetail=<enabled|disabled>"`
    - The log fires once per process startup; no repeated warnings during execution
    - _Requirements: 6.4_
  - [x] 5.6 Property test for Property 4: conditional attachment for `BuilderMCPTool`
    - Add `tests/test_crew_wiring.py::test_property_4_builder_attachment`
    - Parameterize via Hypothesis over the Cartesian product of `BUILDER_MCP_TOKEN in {unset, empty, non-empty}` and `MIDWAY_COOKIE_PATH in {unset, set-and-missing, set-and-present}` (use `monkeypatch` plus `tmp_path`)
    - Build a fresh `PmAgentSystem` instance per state; assert `BuilderMCPTool` is in `external_research_agent.tools` and `brd_agent.tools` if and only if `_builder_mcp_enabled()` returns True
    - **Property 4: Conditional attachment for BuilderMCPTool**
    - **Validates: Requirements 2.1, 2.2, 2.3**
  - [x] 5.7 Property test for Property 5: conditional attachment for `OutlookMCPTool`
    - Add `tests/test_crew_wiring.py::test_property_5_outlook_attachment`
    - Same shape as task 5.6 with `OUTLOOK_MCP_TOKEN` and `_outlook_mcp_enabled()` substituted; assert presence in `prfaq_agent.tools` and `brd_agent.tools`
    - **Property 5: Conditional attachment for OutlookMCPTool**
    - **Validates: Requirements 4.1, 4.2, 4.3**
  - [x] 5.8 Unit tests for predicate edge cases and default-off behavior
    - In `tests/test_crew_wiring.py`, add: a test asserting `external_research_agent.tools` length is unchanged when `BUILDER_MCP_TOKEN` and `MIDWAY_COOKIE_PATH` are both unset (Requirement 2.2); a test asserting `prfaq_agent.tools` contains only the original four tools when `OUTLOOK_MCP_TOKEN` and `MIDWAY_COOKIE_PATH` are both unset (Requirement 4.3); a test asserting the startup log line names the three integrations with their enabled/disabled status
    - _Requirements: 2.2, 4.3, 6.4_

- [x] 6. Update agent and task prompts for MCP context
  - [x] 6.1 Update `external_research_agent` backstory in `agents.yaml`
    - Append a paragraph using conditional language ("If the builder_mcp tool is available...") instructing the agent to use `BuilderMCPTool` for internal wiki, code search, Taskei, and Quip context the public web cannot reach, and to note unavailability in `external_gaps` when the tool is absent or returns an error
    - Banned-word rules from the existing backstory continue to apply; no em dashes as punctuation; no organization-internal portal names, service brands, policy numbers, or internal URL patterns
    - _Requirements: 8.1, 8.5_
  - [x] 6.2 Update `prfaq_agent` backstory in `agents.yaml`
    - Append a paragraph using conditional language instructing the agent to use `OutlookMCPTool` for stakeholder scheduling context in the Internal FAQ section when the tool is available, and to proceed without scheduling data when it is not
    - Apply the same style constraints as task 6.1
    - _Requirements: 8.2, 8.5_
  - [x] 6.3 Update `brd_agent` backstory in `agents.yaml`
    - Append a paragraph using conditional language instructing the agent to use `BuilderMCPTool` for internal technical prior art and architecture context, and `OutlookMCPTool` for stakeholder availability in Timeline and Milestones, when those tools are available
    - Apply the same style constraints as task 6.1
    - _Requirements: 8.3, 8.5_
  - [x] 6.4 Update task descriptions in `tasks.yaml` for MCP tool usage
    - Add a short paragraph in `external_research_task` referencing `BuilderMCPTool` as an optional source for internal Amazon context with instructions on how to incorporate its output
    - Add a short paragraph in `research_synthesis_task` referencing internal findings from the prior task if present
    - Add a short paragraph in `generate_prfaq` referencing `OutlookMCPTool` for stakeholder scheduling context in the Internal FAQ
    - Add a short paragraph in `brd_structure_task` (and `generate_brd_standalone` if applicable) referencing both tools as optional sources
    - Preserve every existing `{variable}` template placeholder; conditional language only
    - _Requirements: 8.4, 8.5_
  - [x] 6.5 Grep the updated prompt content for banned words and em dashes
    - Run the project's existing banned-word and em-dash check against the newly added blocks in `agents.yaml` and `tasks.yaml`
    - The banned word list is defined in the existing agent prompts and style steering; reuse that list
    - Fix any hits and re-run until clean
    - _Requirements: 8.5_
  - [x] 6.6 Prompt-rendering test
    - Add `tests/test_mcp_prompt_rendering.py` that loads `agents.yaml` and `tasks.yaml`, renders the updated backstories and task descriptions with a representative payload, and asserts: zero banned words, zero em dashes used as punctuation, presence of conditional language ("If the builder_mcp tool is available", "If the outlook_mcp tool is available" or equivalent phrasing) in each of the three updated agent blocks, presence of MCP tool references in each of the four updated task blocks
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 7. Extend `.env.example` and `scripts/check_env.py` with MCP configuration
  - [x] 7.1 Add the new variables to `.env.example`
    - Append an "Internal Amazon MCP integrations (optional)" section with the five documented variables: `BUILDER_MCP_TOKEN`, `BUILDER_MCP_ENDPOINT`, `OUTLOOK_MCP_TOKEN`, `OUTLOOK_MCP_ENDPOINT`, `MIDWAY_COOKIE_PATH`
    - Each variable is commented out; each endpoint line carries a placeholder comment indicating the user must set it to their internal endpoint
    - Explain the midway cookie fallback-to-token behavior and reference `docs/internal-mcp-setup.md` for the `mwinit -f` workflow
    - _Requirements: 5.1, 6.1, 6.2, 6.3_
  - [x] 7.2 Extend `scripts/check_env.py` to validate the new variables
    - Add `BUILDER_MCP_TOKEN`, `BUILDER_MCP_ENDPOINT`, `OUTLOOK_MCP_TOKEN`, `OUTLOOK_MCP_ENDPOINT`, `MIDWAY_COOKIE_PATH` to the check list
    - For `MIDWAY_COOKIE_PATH`, when set, also check whether the file exists; report SET, UNSET, or MISCONFIGURED (set but file missing) in the same style as the existing token checks
    - Do not log secret values; follow the existing `len(v)` reveal pattern
    - _Requirements: 6.5_
  - [x] 7.3 Unit test for `check_env.py` reporting across env state combinations
    - Add `tests/test_check_env_mcp.py` that runs the script via `subprocess` or by importing and calling its logic with `monkeypatch` controlling the env vars and a `tmp_path` cookie file
    - Assert the output for each of the three MIDWAY states (unset, set-and-missing, set-and-present) and for SET vs UNSET on each of the four token and endpoint variables
    - _Requirements: 6.5_

- [x] 8. Create `docs/internal-mcp-setup.md`
  - [x] 8.1 Write the internal MCP setup guide
    - New file `docs/internal-mcp-setup.md` covering, in order: what each of the three integrations does and when to enable it; the `mwinit -f` workflow for refreshing cookies across Windows and WSL; where the cookie file lives on Windows, what path to set in WSL, and how to share one file across the two environments (symlink, shared mount, or a direct Windows path reachable from WSL via `/mnt/c/...`); how to verify setup via `uv run python scripts/check_env.py`; troubleshooting (expired cookies, endpoint URL discovery, auth error strings, per-tool call logs under `output/builder_mcp_calls.log` and `output/outlook_mcp_calls.log`)
    - Use generic language only; no organization-internal portal names, service brands, policy numbers, or internal URL patterns
    - No em dashes as punctuation; no banned words
    - _Requirements: 5.6_
  - [x] 8.2 Smoke test that the docs and env config mention the expected keys
    - Add `tests/test_docs_present.py` (or extend an existing docs test) with greps asserting `.env.example` contains each of the five new variable names, `docs/internal-mcp-setup.md` contains `mwinit -f`, `agents.yaml` contains conditional MCP language in each of the three updated backstories
    - _Requirements: 5.6, 6.1, 8.1, 8.2, 8.3_

- [x] 9. Checkpoint - MUST-have scope (Requirements 1-8) is wired and documented
  - Ensure all tests pass with `uv run pytest tests/`, ask the user if questions arise.

- [x] 10. Optional schema extension for internal sources (Requirement 9, SHOULD)
  - [x] 10.1 Extend `ExternalResearchOutput` with `internal_findings`
    - In `src/pm_agent_system/models/research_intermediate.py`, add `internal_findings: list[str] = Field(default_factory=list, description="Findings from internal Amazon systems (wiki, code search, Taskei, Quip)")`
    - Defaulting to an empty list preserves backward compatibility with existing fixtures
    - _Requirements: 9.2_
  - [x] 10.2 Extend `ResearchOutput` with `internal_sources`
    - In `src/pm_agent_system/models/research_output.py`, add `internal_sources: list[str] = Field(default_factory=list, description="Sources retrieved from internal MCP, separate from public sources")`
    - _Requirements: 9.1_
  - [x] 10.3 Update `render_research_to_markdown` to render an "Internal Sources" subsection
    - In `src/pm_agent_system/utils/render_research.py` (or the equivalent renderer module), render `internal_sources` as a dedicated "Internal Sources" subsection within the Sources section when non-empty; omit the subsection entirely when empty
    - _Requirements: 9.3_
  - [x] 10.4 Unit tests for schema backward compatibility and renderer output
    - Add `tests/test_research_output_internal_sources.py` asserting: existing fixtures without the new fields still validate; the new fields default to empty lists; `render_research_to_markdown` renders the "Internal Sources" subsection when populated and omits it when empty
    - _Requirements: 9.1, 9.2, 9.3_

- [x] 11. Optional renderer extensions for PRFAQ and BRD MCP content (Requirement 10, SHOULD)
  - [x] 11.1 Update `render_prfaq_to_markdown` for Outlook stakeholder scheduling context
    - In `src/pm_agent_system/utils/render_prfaq.py` (or equivalent), render stakeholder scheduling context (sourced from Outlook MCP, surfaced by the agent in the Internal FAQ payload) in the Internal FAQ section when present; omit when absent
    - Do not introduce new `PRFAQOutput` schema fields; agents thread Outlook content through existing Internal FAQ entries
    - _Requirements: 10.1_
  - [x] 11.2 Update `render_brd_to_markdown` for Builder MCP technical context
    - In `src/pm_agent_system/utils/render_brd.py`, render internal technical context (sourced from Builder MCP, surfaced by the agent in the Technical Context payload) in the Technical Context section when present; omit when absent
    - _Requirements: 10.2_
  - [x] 11.3 Update `render_brd_to_markdown` for stakeholder availability in Timeline and Milestones
    - In the same renderer, render stakeholder availability data (sourced from Outlook MCP) in the Timeline and Milestones section when present; omit when absent
    - _Requirements: 10.3_
  - [x] 11.4 Unit tests for renderer output
    - Add `tests/test_render_prfaq_mcp.py` and `tests/test_render_brd_mcp.py` asserting: each new section renders when the expected content is present; each is omitted when absent; no banned words or em dashes in any static string introduced by the renderer changes
    - _Requirements: 10.1, 10.2, 10.3_

- [x] 12. Integration and smoke tests (Requirement 11, NICE)
  - [x] 12.1 Full-pipeline smoke test with all MCP tokens unset
    - Add `tests/test_smoke_pipeline_mcp_unset.py` that delenvs `BUILDER_MCP_TOKEN`, `OUTLOOK_MCP_TOKEN`, `MIDWAY_COOKIE_PATH` via `monkeypatch`, builds `full_pipeline_crew`, and asserts the crew construction completes without raising and no MCP tool appears in any agent's tool list
    - No LLM calls; assert the crew object exists and tool lists match the pre-feature baseline
    - _Requirements: 11.6_
  - [x] 12.2 Integration test: midway cookie fallback when cookie file is missing
    - Add `tests/test_midway_cookie_fallback.py` that points `MIDWAY_COOKIE_PATH` at a nonexistent `tmp_path` file while `BUILDER_MCP_TOKEN` is set, runs `resolve_auth` (or exercises `BuilderMCPTool._run` with a mocked `call_mcp`), captures logs with `caplog`, and asserts: a warning was logged for the missing cookie; the resolver returned `MCPAuth` with `bearer_token` set and `cookie_header` None; the outgoing headers contain `Authorization: Bearer ...` and no `Cookie` header
    - Repeat with `OUTLOOK_MCP_TOKEN` and the Outlook tool
    - _Requirements: 5.5, 11.5_
  - [x] 12.3 Integration test: MCP error causes agent to note gap, not raise
    - Add `tests/test_mcp_error_gap_recording.py` that mocks `BuilderMCPTool._run` to return the descriptive HTTP error string and asserts the surrounding agent code (or a representative helper) consumes the error string without raising and the string is surfaceable through the agent's gap field (`external_gaps` / `appendix_gaps` / `risks`)
    - Because this exercises prompt-driven LLM behavior at runtime, the unit-level assertion is that the error string is non-empty, does not raise, and contains an identifiable MCP error marker (for example, `"error"` or `"HTTP"`)
    - _Requirements: 7.1, 7.2, 7.3_

- [x] 13. Final checkpoint - full suite passes and docs reference is clean
  - Ensure all tests pass with `uv run pytest tests/`
  - Run the banned-word and em-dash greps one more time across `agents.yaml`, `tasks.yaml`, `.env.example`, and `docs/internal-mcp-setup.md`
  - Confirm `scripts/check_env.py` reports the five new variables correctly against a sample `.env` with each variable toggled on and off
  - Ask the user if any questions arise before marking the feature ready for review

## Dependency and Infrastructure Notes

- **Property-based testing framework.** `hypothesis>=6.0` is already in the `dev` dependency group of `pyproject.toml`. No new top-level dependencies are introduced by this plan. HTTP mocking uses `pytest-mock` or `respx`; if `respx` is chosen, it lands as a `dev` dependency via `uv sync --group dev` and is captured in the sub-task that first requires it.
- **Banned-word list source.** The banned word list is defined in existing agent prompts and the project's style steering files. Tasks 6.1 through 6.5 and task 13 reuse that list; no new list is introduced.
- **Shared helper is private.** `src/pm_agent_system/tools/_mcp_jsonrpc.py` uses a leading underscore to prevent re-export from `tools/__init__.py`. Both `BuilderMCPTool` and `OutlookMCPTool` import from it directly.
- **No real network calls in tests.** `httpx.post` is mocked at the transport boundary for every tool-level test. The auth resolver reads real temp files for cookie presence tests (using `tmp_path`), which exercises the real filesystem code path cheaply.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP. Optional sub-tasks cover unit tests, property tests, integration tests, and the SHOULD-have Requirement 9 and 10 groups (tasks 10 and 11).
- Every task references specific sub-requirement IDs for traceability.
- Checkpoints (tasks 4, 9, 13) gate progress: each one ensures the preceding work is verified in isolation before the next stage builds on it.
- Property-based tests validate the eight universal correctness properties named in the design document. Each property is covered by its own sub-task and references its property number.
- Unit tests validate specific action mappings, retry counts, timeout values, log content, and rejection paths.
- Integration tests cover end-to-end pipeline wiring (smoke), cookie fallback behavior, and graceful error surfacing.
- Requirement 12 (Deferred Future Work) is intentionally out of scope for this task list. The PM will separately decide which items from Requirement 12 (if any) to promote into this spec or a follow-up.

## Workflow Completion

This workflow is complete once `tasks.md` is created. The Feature Requirements-First workflow produces planning artifacts only; no implementation happens during planning. To begin implementation, open `.kiro/specs/internal-mcp-integration/tasks.md` and click "Start task" next to the first unchecked item.
