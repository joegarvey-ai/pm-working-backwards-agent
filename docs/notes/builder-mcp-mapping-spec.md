# Builder MCP — Capability-to-Deliverable Mapping Spec

Spec for how Builder MCP capabilities feed each pipeline deliverable.
Treat this as the source of truth when updating `tasks.yaml` prompts and
when extending `tools/builder_mcp.py`. The mapping is defined at the
output-field level, not the phase level, so prompts can be precise about
what to extract and where to put it.

## Canonical action set

The internal-Amazon variant of `BuilderMCPTool` should expose the
following actions, mapping to the canonical builder-mcp tools:

| Action (pipeline) | Canonical tool | Primary use |
|---|---|---|
| `internal_search` | `InternalSearch` | Cross-domain keyword search (WIKI, BUILDER_HUB, SAGE_HORDE, SYSTEM_DESIGN_HUB, SPYGLASS, BROADCAST, INSIDE, POLICY, AWS_DOCS, PHONETOOL, WIKI_TEST, EVERGREEN). Pagination, prefix filters, sort by score or modification date. |
| `read_internal_websites` | `ReadInternalWebsites` | Deep fetch of a specific internal URL. The follow-up to a successful `internal_search` hit. Handles `w.amazon.com`, `code.amazon.com`, `quip-amazon.com`, `taskei.amazon.dev`, `pipelines.amazon.com`, `t.corp.amazon.com`, `phonetool.amazon.com`, `oncall.corp.amazon.com`, `bindles.amazon.com`, `sas.corp.amazon.com`, etc. |
| `internal_code_search` | `InternalCodeSearch` | Search Amazon-internal source. Boolean operators, file-path filters, repo filters. |
| `software_recommendations_search` | `SearchSoftwareRecommendations` | Golden Path / blessed-tooling lookup for a problem space. |
| `software_recommendation_get` | `GetSoftwareRecommendation` | Detailed recommendation by ID. |
| `taskei_list` | `TaskeiListTasks` | Enumerate tasks in a Taskei room. |
| `taskei_get` | `TaskeiGetTask` | Detail on a single task. |
| `acronym_lookup` | `SearchAcronymCentral` | Resolve internal acronyms encountered in PM input. |
| `pipeline_get` | `GetPipelineDetails` | Get pipeline structure when referenced in build spec or BRD technical context. |

Existing actions (`wiki_search`, `quip_search`, `taskei_search`,
`code_search`, `pipeline_search`) become thin aliases over the canonical
set during migration, then are deprecated.

## Output-field mapping by task

For every row: the action gets called, the result gets parsed, and a
specific field in the typed task output gets populated. Prompts must
name the action AND the destination field. Generic "use it if available"
language is removed.

### `external_research_task` (Stage 2 split research)

| Action | Destination field | Extraction rule |
|---|---|---|
| `internal_search` (`domain=ALL`, query=`{feature_summary}`) | `external_sources[]` | Each hit: prefix URL with `[internal]`, include displayTitle and modificationDate. Top 5 by score. |
| `internal_search` (`domain=WIKI`, query=`{feature_summary}` plus PM's problem-domain keyword) | `external_sources[]` (subsection: `prior_art_teams`) | For each Wiki hit, extract owning team or LDAP group from the page metadata. Output one bullet per team with the URL. |
| `internal_search` (`domain=SPYGLASS`, query=`{feature_summary}`) | `external_sources[]` | Community-recommended internal services that solve the same or adjacent problem. |
| `internal_search` (`domain=SYSTEM_DESIGN_HUB`, query=`{feature_summary}`) | `external_sources[]` | Architecture / design references that may inform the technical context later in BRD. |
| `read_internal_websites` (top Wiki hit URL) | `external_sources[]` deep content | Full page content for the most relevant prior-art Wiki page. Quoted excerpts get inline citations. |
| `acronym_lookup` (any Amazon acronym in `{feature_summary}` or `{user_summary}`) | inline gloss in the brief | Optional. Avoids the synthesis agent guessing what an internal acronym means. |

Failure modes: if any action returns 4xx or 5xx, log to `external_gaps`
with the action name, query, and HTTP status. Do not fabricate.

### `customer_evidence_task`

| Action | Destination field | Extraction rule |
|---|---|---|
| `internal_search` (`domain=WIKI`, query: PM's user-pain keyword) | `customer_evidence[]` | Internal anecdote programs (Voice of Customer, Voice of Developer, anecdote pipelines). Pull quantified metrics with attribution: "Appstore VOD reduced functional Contact Us cases 60% (750 → 299, Jan-Apr 2024 vs Jan-Apr 2025), [Appstore VOD SOP](url)". |
| `internal_search` (`domain=SAGE_HORDE`, query: user-pain keyword) | `customer_evidence[]` | Engineering Q&A may surface customer-facing pain reported by builders. |
| `internal_search` (`domain=BROADCAST`, query: user-pain keyword) | `customer_evidence[]` | Internal video transcripts can surface VP-level statements about a problem space. |
| `read_internal_websites` (top hit per domain) | `customer_evidence[]` quote material | Direct quotes pulled from the page, in quotation marks, with source URL. |

Rule: do not include this action set in the existing Dovetail-only
prompt. Add a new section to the task: "Internal anecdote programs and
prior art are valid customer evidence sources alongside Dovetail."

### `research_synthesis_task`

No tool calls. Existing prompt already preserves `[internal]`-prefixed
entries. Tighten the rule:

- New paragraph in `internal_state_assessment`: "Teams already operating
  in this space." Lists each team / LDAP group / Wiki page surfaced by
  the upstream tasks. Names them. Forces the join-vs-build conversation
  into the next phase.
- Rank prior-art teams by overlap (high / medium / low) based on the
  Wiki page descriptions. No invention; if the description doesn't
  state scope, mark as "scope unclear, flag in PRFAQ internal FAQ".

### `generate_prfaq` and `generate_prfaq` chained

| Action | Destination field | Extraction rule |
|---|---|---|
| `internal_search` (`domain=BUILDER_HUB`, query=`{feature_summary}`) | new internal FAQ entry | Forces "Why not use the official ASBX / Golden Path approach for X?" question to land in the doc. |
| `software_recommendations_search` (`{feature_summary}` keyword) | new internal FAQ entry | Generates the "Why not use the recommended software?" question with concrete recommendation IDs cited. |
| `read_internal_websites` (Phonetool URL for owning LDAP groups from research) | press release fictional quote tone, plus stakeholder names in internal FAQ | Borrow real-team tone for the customer quote. Name actual stakeholders in "Who needs to be aligned?" |
| `read_internal_websites` (Heartbeat or canonical-system Wiki page if surfaced) | new internal FAQ: "Why are we not extending the canonical system?" | Required when research surfaced a canonical / official internal solution. |

New required internal FAQs when prior-art teams exist:
1. "What is already running internally and why are we not joining or extending it?"
2. "Who owns the closest existing system, and have we discussed scope with them?"
3. "What would have to change in our scope for us to consume their data or front-end instead?"

Banned: PRFAQ goes to print without these questions when the research
brief's `internal_state_assessment` named a prior-art team.

### `generate_design_brief`

| Action | Destination field | Extraction rule |
|---|---|---|
| `internal_search` (`domain=WIKI` + `domain=BUILDER_HUB`, query=`{feature_summary} UI`) | `competitive_ui_patterns[]` | Internal-tool UI patterns to match or avoid, sourced from real internal product Wiki pages. |
| `read_internal_websites` (any internal product Wiki surfaced) | `competitive_ui_patterns[]` deep content | Specific UI patterns named in the page (e.g. "anecdote tagging table", "sentiment-rated card"). |
| `internal_code_search` (front-end repo names from prior research) | `screen_inventory[]` `source_section` enrichment | If an existing internal package implements a similar screen, name the package. Designer can reuse rather than recreate. |

Rule change: `competitive_ui_patterns` currently expects external
competitors only. Extend the field semantics so internal Amazon products
are valid entries, distinguished by an `origin` field (`internal` vs
`external`).

### `brd_structure_task`

| Action | Destination field | Extraction rule |
|---|---|---|
| `internal_code_search` (architecture keyword from PRFAQ solution overview) | `technical_context_and_dependencies` Mermaid diagram nodes | Real package and service IDs, not invented names. |
| `internal_search` (`domain=SYSTEM_DESIGN_HUB`, query: solution-overview keyword) | `technical_context_and_dependencies` prose | Architecture references with inline citations. |
| `read_internal_websites` (any `rome.aws.dev/services/...` URL surfaced) | `technical_context_and_dependencies` prose | Service ownership, dependencies, CTIs. |
| `pipeline_get` (any pipeline named in research) | `technical_context_and_dependencies` prose | Real pipeline structure, not a fabricated one. |

### `brd_cost_risk_task`

| Action | Destination field | Extraction rule |
|---|---|---|
| `internal_search` (`domain=WIKI`, query=`{feature_summary}` plus team-overlap keyword) | `risks[]` | "Initiative overlap with [Team X]" risks. Cite the Wiki page. Likelihood = high if multiple teams found; medium if one. |
| `internal_search` (`domain=POLICY`, query: data-handling or compliance keyword from PRFAQ) | `risks[]` | Policy risks by reference; deeper handling lives in the compliance task. |

### `brd_compliance_task`

| Action | Destination field | Extraction rule |
|---|---|---|
| `internal_search` (`domain=POLICY`, query: data-classification keyword) | `compliance_gates[]`, `vendor_scenarios_applied[]` | Backed by real Amazon policy URLs. Avoids generic SOC2-speak. |
| `read_internal_websites` (Shepherd, Bindles, Talos, Aristotle URLs) | `compliance_gates[]` notes | Real review processes named, with the verbatim "start early, run in parallel" note still attached. |
| `internal_search` (`domain=BUILDER_HUB`, query: KMS, Cognito, CloudWatch keyword from PRFAQ) | `privacy_considerations` | AWS service guidance from internal docs. |

### `generate_build_spec_*`

| Action | Destination field | Extraction rule |
|---|---|---|
| `internal_code_search` (architecture keyword from BRD) | `current_state_context` | Real package layouts to mirror (Brazil package structure, build configs). |
| `pipeline_get` (any pipeline named in BRD technical context) | `current_state_context` | Pipeline stage names, deployment patterns. |
| `taskei_list` (room from PM input or research) | `out_of_scope` enrichment | Existing tasks in the relevant Taskei room may already cover items the spec is about to duplicate. |

### `feedback_classify_task` (future enhancement)

| Action | Destination field | Extraction rule |
|---|---|---|
| `internal_search` (`domain=WIKI`, query: feedback topic phrase) | `classifier_notes` | "Has another team already resolved this contradiction?" — surfaces prior decisions. Lower priority than the phases above. |

## Prompt-update rules

Across every task that uses Builder MCP:

1. Name the action and the destination field. Do not write "use it if available."
2. Specify the `domain` parameter when calling `internal_search`. Default `ALL` is wasteful when the phase has a known scope.
3. State the failure mode: every action that returns an error logs to a `*_gaps` field, never to fabricated content.
4. Cite inline. Every Builder MCP-sourced claim gets a markdown link in the source URL the action returned.
5. Acronym handling: if the PM input contains a token that looks like an Amazon acronym (3-5 uppercase letters, or a token followed by a parenthetical), call `acronym_lookup` once and inline the gloss.

## Open questions for the implementation pass

- Confirm whether the canonical builder-mcp is reachable as plain HTTP/JSON-RPC from a CrewAI tool, or whether it is only exposed through Claude Code's MCP-client transport. If the latter, `_mcp_jsonrpc.py` may need a small protocol adapter, or the internal variant launches a stdio MCP subprocess.
- Confirm hosted-builder-mcp endpoint URL and whether the Midway cookie is the only auth path.
- Decide whether the GitHub variant ships with a stub backend that returns descriptive "not configured" errors, or whether it ships with no backend and the tool refuses to register. The current code already handles "not configured" gracefully, so the cheaper path is to keep that behavior.
- Decide on action-naming: keep `wiki_search` / `code_search` as backward-compatible aliases, or rename to `internal_search` / `internal_code_search` and update prompts in one pass.
