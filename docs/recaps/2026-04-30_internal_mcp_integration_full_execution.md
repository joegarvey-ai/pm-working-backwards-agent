# Internal MCP Integration - Full Execution Recap

**Date:** 2026-04-30
**Spec:** `.kiro/specs/internal-mcp-integration/`
**Status:** All 13 tasks complete, 446 tests passing, 0 failures
**Duration:** Single session execution

---

## What Was Built

Three internal Amazon MCP servers integrated into the PM Working Backwards CrewAI pipeline following the established Dovetail optional-tool pattern:

1. **Builder MCP** - wiki, code search, Taskei, Quip, pipelines
2. **Outlook MCP** - calendar, email metadata, room booking, schedule summary
3. **Midway cookie sharing** - single `mwinit -f` refreshes auth for both Windows and WSL

All three are additive. The pipeline runs unchanged when tokens are unset.

---

## Architecture Decisions

### Shared JSON-RPC Helper (`_mcp_jsonrpc.py`)
- Private module (leading underscore, not re-exported)
- Provides: `MCPAuth` dataclass, `resolve_auth`, `jsonrpc_envelope`, `extract_text`, `build_headers`, `post_with_retry`, `call_mcp`, `log_call`
- Both tools consume it; no code duplication
- Auth resolves fresh on every call (cookies expire)

### Authentication Flow
- Cookie-first, token-fallback precedence
- `MIDWAY_COOKIE_PATH` checked first; if file exists and is non-empty, use cookie
- If cookie path set but file missing/empty, log warning, fall through to token
- If token set, use bearer auth
- If neither available, return descriptive error string (never raise)

### Conditional Wiring
- `_builder_mcp_enabled()` and `_outlook_mcp_enabled()` predicates in `crew.py`
- OR logic: enabled when token is set OR when cookie path points to existing file
- `BuilderMCPTool` attaches to `external_research_agent` and `brd_agent`
- `OutlookMCPTool` attaches to `prfaq_agent` and `brd_agent`
- Single startup log line reports enabled/disabled status for all three integrations

### Email Privacy (Requirement 3.6)
- `_scrub_email_bodies()` recursively walks JSON at any depth
- Drops `body`, `body_preview`, `body_html` keys
- Preserves `subject`, `from`, `date`, `to`, `cc`, `summary`
- Generates 200-char `preview` when `summary` absent
- Returns conservative error string for unrecognized response shapes

---

## Files Created

### Source Code
| File | Purpose |
|------|---------|
| `src/pm_agent_system/tools/_mcp_jsonrpc.py` | Shared JSON-RPC client |
| `src/pm_agent_system/tools/builder_mcp.py` | BuilderMCPTool (5 actions) |
| `src/pm_agent_system/tools/outlook_mcp.py` | OutlookMCPTool (4 actions) |

### Modified Source
| File | Changes |
|------|---------|
| `src/pm_agent_system/tools/__init__.py` | Added BuilderMCPTool, OutlookMCPTool exports |
| `src/pm_agent_system/crew.py` | Predicates, conditional wiring, startup log |
| `src/pm_agent_system/config/agents.yaml` | MCP conditional paragraphs in 3 backstories |
| `src/pm_agent_system/config/tasks.yaml` | MCP references in 5 task descriptions |
| `src/pm_agent_system/models/research_intermediate.py` | `internal_findings` field |
| `src/pm_agent_system/models/research_output.py` | `internal_sources` field |
| `src/pm_agent_system/utils/render_markdown.py` | Internal Sources subsection |
| `src/pm_agent_system/utils/render_prfaq.py` | Design decision comment |
| `src/pm_agent_system/utils/render_brd.py` | Design decision comments |
| `.env.example` | 5 new MCP variables documented |
| `scripts/check_env.py` | MCP variable validation |

### Documentation
| File | Purpose |
|------|---------|
| `docs/internal-mcp-setup.md` | Full setup guide (cookie workflow, troubleshooting) |

### Tests (141 new)
| File | Tests | Coverage |
|------|-------|----------|
| `tests/tools/test_mcp_jsonrpc.py` | 14 | extract_text, log_call |
| `tests/tools/test_mcp_jsonrpc_properties.py` | 2 | Property 1 (envelope), Property 7 (auth) |
| `tests/tools/test_builder_mcp.py` | 8 | Action mapping, retry, timeout, logging |
| `tests/tools/test_builder_mcp_properties.py` | 3 | Property 2 (schema), Property 8 (no-raise) |
| `tests/tools/test_outlook_mcp.py` | 10 | Action mapping, retry, timeout, scrubber, logging |
| `tests/tools/test_outlook_mcp_properties.py` | 4 | Property 3 (schema), Property 6 (scrub), Property 8 |
| `tests/test_crew_wiring.py` | 5 | Property 4, Property 5, predicate edge cases |
| `tests/test_mcp_prompt_rendering.py` | 27 | Conditional language, banned words, em dashes |
| `tests/test_check_env_mcp.py` | 13 | check_env.py reporting |
| `tests/test_docs_present.py` | 10 | Docs and config smoke tests |
| `tests/test_research_output_internal_sources.py` | 13 | Schema backward compat, renderer |
| `tests/test_render_prfaq_mcp.py` | 7 | PRFAQ renderer MCP content |
| `tests/test_render_brd_mcp.py` | 8 | BRD renderer MCP content |
| `tests/test_smoke_pipeline_mcp_unset.py` | 5 | Full pipeline smoke (no MCP) |
| `tests/test_midway_cookie_fallback.py` | 6 | Cookie fallback integration |
| `tests/test_mcp_error_gap_recording.py` | 6 | Error string surfacing |

---

## Correctness Properties (Property-Based Testing)

All 8 properties from the design document are covered:

| # | Property | Test Location |
|---|----------|---------------|
| 1 | JSON-RPC envelope structural invariants | `test_mcp_jsonrpc_properties.py` |
| 2 | BuilderMCPInput args_schema validation | `test_builder_mcp_properties.py` |
| 3 | OutlookMCPInput args_schema validation | `test_outlook_mcp_properties.py` |
| 4 | Conditional attachment for BuilderMCPTool | `test_crew_wiring.py` |
| 5 | Conditional attachment for OutlookMCPTool | `test_crew_wiring.py` |
| 6 | Email body scrubbing at any depth | `test_outlook_mcp_properties.py` |
| 7 | Auth resolver precedence | `test_mcp_jsonrpc_properties.py` |
| 8 | MCP tool _run never raises on error | Both `_properties.py` files |

---

## Requirements Coverage

| Requirement | Priority | Status |
|-------------|----------|--------|
| 1. Builder MCP CrewAI Tool | MUST | Done |
| 2. Builder MCP Optional Wiring | MUST | Done |
| 3. Outlook MCP CrewAI Tool | MUST | Done |
| 4. Outlook MCP Optional Wiring | MUST | Done |
| 5. Midway Cookie Sharing Config | MUST | Done |
| 6. Environment Variable Config | MUST | Done |
| 7. Error Handling for MCP Unavailability | MUST | Done |
| 8. Agent Prompt Updates for MCP Context | MUST | Done |
| 9. Research Output Schema Extension | SHOULD | Done |
| 10. PRFAQ and BRD Renderer Updates | SHOULD | Done |
| 11. Unit and Integration Tests | NICE | Done |
| 12. Deferred Future Work | NICE | Out of scope (by design) |

---

## Operational Notes

### How to Enable
1. Set `BUILDER_MCP_TOKEN` and `BUILDER_MCP_ENDPOINT` in `.env`
2. Set `OUTLOOK_MCP_TOKEN` and `OUTLOOK_MCP_ENDPOINT` in `.env`
3. Or set `MIDWAY_COOKIE_PATH` and run `mwinit -f` for cookie auth
4. Verify with `uv run python scripts/check_env.py`

### Call Logs
- `output/builder_mcp_calls.log` - JSONL, one line per invocation/response
- `output/outlook_mcp_calls.log` - same format

### Error Behavior
- Tools never raise; always return descriptive error strings
- Agents record errors in gap fields (`external_gaps`, `appendix_gaps`, `risks`)
- 3 retries with exponential backoff (2s, 4s, 8s max) before final error

---

## Housekeeping

- Disabled `sync-specs-obsidian.kiro.hook` and `publish-specs-obsidian.kiro.hook` to stop extra chat tab creation
- `test-on-save.kiro.hook` was already disabled

---

## Recommended Next Steps

### Immediate (This Sprint)
1. **Set up real endpoints** - Get the actual `BUILDER_MCP_ENDPOINT` and `OUTLOOK_MCP_ENDPOINT` URLs from the team and test with real data
2. **Cookie path validation** - Confirm the `mwinit -f` cookie file path on your Windows machine and set `MIDWAY_COOKIE_PATH` in `.env`
3. **Run a real pipeline** - Execute `uv run pm_agent_system research examples/input.yaml` with Builder MCP enabled and verify internal findings appear in the research brief

### Short-term Hardening
4. **Cookie expiry detection** - The current implementation reads the cookie file contents but does not parse expiry timestamps. Consider adding a check that warns when the cookie content looks stale (e.g., file modification time > 12 hours ago)
5. **Rate limiting** - If the MCP servers have rate limits, add a rate limiter to `post_with_retry` or a per-tool cooldown
6. **Endpoint health check CLI** - Add a `uv run pm_agent_system mcp-health` subcommand that pings both endpoints and reports latency/status (deferred in Requirement 12)
7. **Structured error classification** - Currently error strings are free-form. Consider an enum of error types (auth_failure, timeout, server_error, config_missing) for programmatic handling downstream

### Medium-term (Next Spec)
8. **Dedicated internal research agent** - Requirement 12 deferred a separate async agent for internal research (like the Dovetail `customer_evidence_agent`). This would let internal and external research run in parallel
9. **Taskei integration** - Auto-creating Taskei tasks from BRD requirements (deferred in Requirement 12)
10. **Quip document generation** - Writing PRFAQs or BRDs directly to Quip (deferred in Requirement 12)

### Testing Hardening
11. **Contract tests against real MCP servers** - The current tests mock at `httpx.post`. Add an optional integration test suite (gated behind an env var like `MCP_INTEGRATION_TESTS=1`) that hits real endpoints in a staging environment
12. **Property test coverage expansion** - Property 6 (email scrubbing) uses `max_depth=3`. Consider increasing to 5 for deeper nesting coverage
13. **Mutation testing** - Run `mutmut` against `_mcp_jsonrpc.py` and the two tool modules to verify the test suite catches real mutations

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Cookie expires mid-pipeline | Medium | Low | Tools fall back to token; warning logged |
| MCP server down during research | Low | Low | Error string returned; agent notes gap |
| Endpoint URL changes | Low | Medium | Centralized in `.env`; `check_env.py` validates |
| Email body leaks through scrubber | Low | High | Property 6 tests arbitrary depth; conservative fallback for unrecognized shapes |
| New MCP action added upstream | Medium | Low | Unknown action returns descriptive error listing valid actions |
