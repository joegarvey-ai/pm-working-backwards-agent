# Internal MCP Setup Guide

This guide covers three optional integrations that connect the PM Working
Backwards pipeline to internal systems. All three are additive. When their
environment variables are unset, the pipeline runs unchanged.

## What each integration does

### Builder MCP

Builder MCP connects the research and BRD agents to internal wiki pages,
code repositories, task tracking tickets, document collaboration tools,
and pipeline data. Enable it when you need the research brief or BRD to
include internal technical context that public web searches cannot reach.

**Agents that use it:** `external_research_agent`, `brd_agent`

The pipeline talks to the canonical Amazon `builder-mcp` server (a
stdio MCP binary distributed by ASBX). No environment variables are
required. The tool is enabled automatically when the `builder-mcp`
binary is on PATH. Auth is handled by the binary using your Midway
session.

**Install on a Cloud Desktop or internal Linux dev box:**

```bash
toolbox install mcp-registry && mcp-registry install builder-mcp
mwinit -f
```

After installation, run `which builder-mcp` to confirm the binary is on
PATH. The pipeline registers `BuilderMCPTool` automatically on the next
run.

When the binary is not installed (the OSS variant of the pipeline, or
any environment without ASBX tooling), the tool stays unregistered and
the pipeline runs unchanged.

### Outlook MCP

Outlook MCP connects the PRFAQ and BRD agents to calendar, email metadata,
room booking, and schedule summary data. Enable it when you want the
Internal FAQ or Timeline and Milestones sections to reflect real
stakeholder availability and scheduling constraints.

**Agents that use it:** `prfaq_agent`, `brd_agent`

### Read integrations: Pippin, QuickSight, Software Catalog, Virtual PM

Four additional read tools attach to agents when their MCP binary is on PATH,
each gated by a binary-presence predicate so the OSS pipeline is unchanged when
the binary is absent. Like Builder MCP, auth is handled by each binary; no env
vars are required beyond the optional binary/tool overrides.

| Tool | Binary (env override) | Reads | Attached to |
|---|---|---|---|
| `pippin_read` | `python-pippin-mcp` (`PIPPIN_MCP_BINARY`) | Prior PRFAQs/BRDs + reviewer comments from Pippin (read-only) | `external_research_agent` |
| `quicksight_dashboard` | `quicksight-mcp` (`QUICKSIGHT_MCP_BINARY`) | QuickSight dashboard/analysis data (returns CSV **file paths**, not inline data) | `brd_agent` |
| `software_catalog` | `software-catalog-mcp` (`SOFTWARE_CATALOG_MCP_BINARY`) | SoftwareCatalog knowledge graph (products/services/features/org/costs) | `external_research_agent`, `brd_agent` |
| `virtual_pm_critique` | `virtual-pm-mcp` (`VIRTUAL_PM_MCP_BINARY`) | Virtual PM spec review (0-100, 8 personas) — a second critique lens alongside Working Backwards AI | `prfaq_agent` |

Notes:

- **Read-only.** These agents get *read* capability only. Pippin *writes*
  (create_artifact) stay in the human-gated `publish-doc --target pippin` path,
  never on an agent.
- **QuickSight returns file paths.** `quicksight_dashboard` surfaces the CSV
  path + row count so the agent decides whether to read the file, rather than
  inlining potentially large CSV content. Auth uses `mwinit -o` (headless
  browser + Midway SSO).
- **Assumed contracts, flagged.** The `software-catalog-mcp` and `virtual-pm-mcp`
  binaries would not install on the build host this session (both "In
  development" in the AIM registry), so their exact remote tool names / arg
  shapes are unverified and env-overridable (`SOFTWARE_CATALOG_LOOKUP_TOOL`,
  `SOFTWARE_CATALOG_CYPHER_TOOL`, `VIRTUAL_PM_MCP_TOOL`).

#### Live verification status (2026-07-14)

| Path | Status | Notes |
|---|---|---|
| Pippin read (`list_projects` / `list_artifacts` / `get_artifact` / `get_comments`) | ✅ **verified live** | Exercised against a real project; the tool forwards the server JSON verbatim. |
| Pippin publish (`create_artifact`) | ✅ **verified live** | Arg shape `{project_id, name, content}` confirmed (no `format`). The response is JSON with **no URL** — the artifact URL is now built from `projectId` + `designId` (see `_pippin_extract_url`; `PIPPIN_BASE_URL` overrides the host). |
| QuickSight `get_dashboard_data` | contract from registry doc, **not run** | Binary would not install (below). |
| SharePoint / software-catalog / virtual-pm / WB AI | **assumed, blocked** | Binaries would not install (below). |

**Why the "In development" binaries would not install (diagnosed, not an auth
issue).** `aim mcp install <id>` delegates to `toolbox install <id>`, which
searches only the toolbox registries configured on the host
(`toolbox registry list`). The `sharepoint-mcp`, `quicksight-mcp`,
`software-catalog-mcp`, `virtual-pm-mcp`, and `wb-ai-mcp` bundles are published
to registries not on that list, so `toolbox install` returns "Unable to find a
registry containing these tools" even with a live Midway session. Re-running
`mwinit` does **not** fix this. To install one, add its registry with
`toolbox registry add <s3-location>` (get the location from the server's
BuilderHub page) or wait until it graduates from "In development" into a
standard registry. `python-pippin-mcp` works because its bundle is materialized
locally at `~/.aim/bundles/python-pippin-mcp-data/`, not via `toolbox install`.

### Gated write-back (publish-doc, seed-taskei, ingest-feedback)

Unlike the integrations above — which are *read* tools an agent invokes
mid-run — the write-back commands **write to outward-facing systems** and are
invoked by *you*, from the CLI, after you approve an artifact. They are never
attached to an agent, and each external write requires an explicit `[y/N]`
confirmation that defaults to No.

**Used by:** the `publish-doc`, `seed-taskei`, and `ingest-feedback` CLI
commands (no agent).

| Command | Writes to | Binary | Remote tool |
|---|---|---|---|
| `publish-doc --target quip` | Quip document store | `builder-mcp` | `QuipEditor` |
| `publish-doc --target sharepoint` | SharePoint document library | `sharepoint-mcp` | `create_document` *(assumed)* |
| `publish-doc --target pippin` | Pippin artifact (needs `--pippin-project`) | `python-pippin-mcp` | `create_artifact` |
| `seed-taskei` | Taskei (one task per BRD FR, under a parent EPIC) | `builder-mcp` | `TaskeiCreateTask` |
| `ingest-feedback` | The **local** `output/feedback/` inbox (reads Slack) | `slack-mcp` | `get_messages` |

Notes:

- **Three publish targets, three binaries.** `publish-doc` routes through a
  pluggable provider registry, and each provider names the binary it speaks to:
  - `quip` → `builder-mcp` (Midway auth). Amazon is migrating document
    collaboration off Quip toward SharePoint / Word-on-cloud.
  - `sharepoint` → `sharepoint-mcp`, a **separate** binary with **FedAuth
    cookie** auth (not the builder-mcp Midway path). The binary owns its own
    auth, so the fail-soft contract is identical; only the binary and auth
    mechanism differ. ⚠️ The create-document **tool name and arg shape are
    assumed** — the `sharepoint-mcp` binary would not install on the build host
    (AIM registry lists it "In development"), so its 12-tool contract is
    unverified. `create_document` is the default guess; override it with
    `WRITE_BACK_SHAREPOINT_TOOL` after a live smoke test if it differs.
  - `pippin` → `python-pippin-mcp`. The `create_artifact(project_id, name,
    content)` contract is confirmed against the connected Pippin MCP. Pippin has
    no sensible default project, so `publish-doc --target pippin` **requires**
    `--pippin-project <id>` (or `PIPPIN_PROJECT_ID`) and refuses without one,
    exactly like `seed-taskei`'s `--taskei-room`.
- **`seed-taskei` needs a room.** There is no sensible default room for an OSS
  tool, so you must pass `--taskei-room <uuid>` or set `TASKEI_ROOM_ID`. The
  command refuses to run without one. Use `--dry-run` to print the exact tasks
  it would create without writing anything.
- **Remote tool names and binaries are overridable.** The remote MCP tool names
  default to the live gateway names, but each is overridable via an env var
  (`WRITE_BACK_QUIP_TOOL`, `WRITE_BACK_TASKEI_TOOL`, `WRITE_BACK_SHAREPOINT_TOOL`,
  `WRITE_BACK_PIPPIN_TOOL`, `SLACK_MCP_MESSAGES_TOOL`, and the `*_MCP_BINARY`
  names) so a registry that registers them differently can be pointed at
  without a code change.
- **Fail-soft.** When the binary is not on PATH or Midway is expired, these
  commands print a descriptive message and write nothing — they never crash.
- **Call logging.** All write attempts are logged as JSONL to
  `output/write_back_calls.log`.

Install is the same as Builder MCP (`slack-mcp` installs the same way via
`mcp-registry`). No environment variables are required beyond the optional
`TASKEI_ROOM_ID`.

### Midway cookie sharing

Midway cookie sharing lets both MCP tools authenticate using a single
cookie file instead of separate API tokens. One `mwinit -f` command
refreshes the cookie for both Windows and WSL. Enable it when you work
across both environments and want a single authentication flow.

**Used by:** Builder MCP and Outlook MCP (as a shared auth fallback)

---

## Cookie refresh workflow

Run the following command from a Windows terminal to refresh your
authentication cookie:

```bash
mwinit -f
```

This writes a cookie file that both MCP tools can read. The cookie has a
limited lifetime (typically 12 hours). Re-run `mwinit -f` when the cookie
expires.

If you work in WSL, you do not need to run `mwinit -f` again inside WSL.
Instead, point `MIDWAY_COOKIE_PATH` at the same file that Windows wrote
(see the next section).

---

## Cookie file location and cross-environment sharing

### Where the cookie lives on Windows

After running `mwinit -f`, the cookie file is written to your Windows
user profile directory. The exact path depends on your system
configuration, but it is typically under your home folder (for example,
`C:\Users\<username>\.midway\cookie`).

### What path to set in WSL

In your `.env` file (or shell environment), set `MIDWAY_COOKIE_PATH` to
the location where WSL can read the cookie. You have three options:

**Option A: Use the Windows path directly from WSL**

WSL mounts the Windows `C:` drive at `/mnt/c/`. Point at the cookie file
through that mount:

```dotenv
MIDWAY_COOKIE_PATH=/mnt/c/Users/<username>/.midway/cookie
```

This is the simplest approach. No extra setup is needed.

**Option B: Create a symlink inside WSL**

Create a symlink in your WSL home directory that points to the Windows
cookie file:

```bash
ln -s /mnt/c/Users/<username>/.midway/cookie ~/.midway/cookie
```

Then set:

```dotenv
MIDWAY_COOKIE_PATH=~/.midway/cookie
```

This keeps your `.env` file portable across machines with different
Windows usernames.

**Option C: Use a shared mount**

If your team uses a shared network mount or a custom mount point, set
`MIDWAY_COOKIE_PATH` to wherever the cookie file is accessible from both
environments.

### When the cookie is not needed

If you set `BUILDER_MCP_TOKEN` and `OUTLOOK_MCP_TOKEN` directly, the
tools use those tokens and ignore the cookie path. The cookie path is
only needed when you prefer cookie-based authentication.

---

## Verifying your setup

Run the environment check script to confirm that all MCP variables are
configured correctly:

```bash
uv run python scripts/check_env.py
```

The script reports each variable as SET, UNSET, or MISCONFIGURED. For
`MIDWAY_COOKIE_PATH`, it also checks whether the file exists at the
specified path.

A healthy configuration looks like one of these patterns:

- **Builder MCP enabled:** `which builder-mcp` returns a path, and
  `mwinit -f` was run within the cookie lifetime. Outlook MCP env vars
  may be set or unset independently.
- **Outlook MCP enabled (token):** `OUTLOOK_MCP_TOKEN` is SET,
  `OUTLOOK_MCP_ENDPOINT` is SET.
- **Outlook MCP enabled (cookie):** `MIDWAY_COOKIE_PATH` is SET (file
  exists), `OUTLOOK_MCP_ENDPOINT` is SET, `OUTLOOK_MCP_TOKEN` is UNSET.
- **Disabled:** the `builder-mcp` binary is not on PATH and Outlook MCP
  variables are unset. The pipeline runs without internal MCP tools.

---

## Troubleshooting

### Expired cookies

**Symptom:** MCP tool calls return authentication errors after working
earlier in the day.

**Fix:** Re-run `mwinit -f` from a Windows terminal to refresh the
cookie. The cookie has a limited lifetime and must be refreshed
periodically.

### Endpoint URL discovery

Each MCP endpoint URL is specific to your team or account. The endpoint
is not published in this repository. Ask your team lead or check your
team's internal documentation for the correct values of
`BUILDER_MCP_ENDPOINT` and `OUTLOOK_MCP_ENDPOINT`.

### Auth error strings

When authentication fails, the tools return descriptive error strings
instead of raising exceptions. Common messages:

- `"builder-mcp binary not found on PATH; install via 'toolbox install
  mcp-registry && mcp-registry install builder-mcp'."` means the
  canonical Amazon binary is not installed or not on PATH.
- `"Error connecting to builder_mcp: ..."` means the binary started but
  the call failed. Check the call log under
  `output/builder_mcp_calls.log` for the full error type. Common cause:
  expired Midway session — re-run `mwinit -f`.
- `"Builder MCP call timed out (action=...)."` means a single call
  exceeded the per-call timeout. Re-run with a more specific query.
- For Outlook MCP, the original token-and-endpoint error patterns
  still apply: `"OUTLOOK_MCP_TOKEN not set in environment variables;
  set token or MIDWAY_COOKIE_PATH to enable outlook_mcp."` and
  `"Outlook MCP error (HTTP 401|403): ..."`.

### Per-tool call logs

Both tools write a JSONL log of every invocation and response:

- **Builder MCP:** `output/builder_mcp_calls.log`
- **Outlook MCP:** `output/outlook_mcp_calls.log`

Each line is a JSON object with a timestamp, event type (`invocation` or
`response`), and a details payload. Use these logs to inspect what the
tool sent and what the server returned.

To view the last five log entries:

```bash
tail -5 output/builder_mcp_calls.log
```

### Cookie file not found

**Symptom:** `check_env.py` reports `MIDWAY_COOKIE_PATH` as
MISCONFIGURED (set but file missing).

**Fix:** Verify the path in your `.env` file. If you are using a
`/mnt/c/...` path from WSL, confirm that the Windows file exists at
that location. If you created a symlink, confirm the symlink target
is valid with `ls -la ~/.midway/cookie`.
