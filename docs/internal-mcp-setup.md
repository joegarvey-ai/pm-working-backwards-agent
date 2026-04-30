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

### Outlook MCP

Outlook MCP connects the PRFAQ and BRD agents to calendar, email metadata,
room booking, and schedule summary data. Enable it when you want the
Internal FAQ or Timeline and Milestones sections to reflect real
stakeholder availability and scheduling constraints.

**Agents that use it:** `prfaq_agent`, `brd_agent`

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

- **Token-based auth:** `BUILDER_MCP_TOKEN` is SET, `BUILDER_MCP_ENDPOINT`
  is SET, `MIDWAY_COOKIE_PATH` is UNSET.
- **Cookie-based auth:** `MIDWAY_COOKIE_PATH` is SET (file exists),
  `BUILDER_MCP_ENDPOINT` is SET, `BUILDER_MCP_TOKEN` is UNSET.
- **Disabled:** All five MCP variables are UNSET. The pipeline runs
  without internal MCP tools.

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

- `"BUILDER_MCP_TOKEN not set in environment variables; set token or
  MIDWAY_COOKIE_PATH to enable builder_mcp."` means neither the token
  nor the cookie path resolved to valid credentials.
- `"Builder MCP error (HTTP 401): ..."` or `"Builder MCP error
  (HTTP 403): ..."` means the token or cookie was rejected by the
  server. Refresh the cookie with `mwinit -f` or check that the token
  is still valid.
- The same patterns apply to Outlook MCP with `OUTLOOK_MCP_TOKEN` and
  `outlook_mcp` substituted.

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
