"""Shared stdio helpers for internal Amazon MCP tools that run as a
subprocess.

Private module (leading underscore) consumed by `builder_mcp.py`. Not
re-exported from `tools/__init__.py`.

The canonical Amazon `builder-mcp` server is distributed as a CLI binary
that an MCP client launches over stdio. There is no public HTTP/JSON-RPC
endpoint. Auth (Midway cookie) is handled internally by the binary, so
this module does not deal with auth material at all.

Design notes:
- Spawn-per-call. The `builder-mcp` binary takes ~1-2s to start; the
  pipeline calls each MCP tool only a handful of times per run, so the
  startup cost is acceptable in exchange for zero process-lifecycle
  complexity.
- Sync-over-async. The `mcp` Python SDK is async. CrewAI tools have a
  sync `_run`. We wrap each call with `asyncio.run`.
- Fail-soft. When the `builder-mcp` binary is not on PATH, callers
  receive a descriptive error string and the agent continues.
- Consistent JSONL call logging via `log_call`, mirroring the pattern
  in `_mcp_jsonrpc.py`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


def is_binary_available(binary_name: str = "builder-mcp") -> bool:
    """True when *binary_name* is present on PATH."""
    return shutil.which(binary_name) is not None


def call_stdio_mcp(
    binary: str,
    tool_name: str,
    arguments: dict,
    args: Iterable[str] = (),
    timeout: float = 60.0,
) -> str:
    """Spawn an MCP stdio server, call one tool, return the text content.

    Parameters
    ----------
    binary
        Name or path of the MCP server executable. Looked up on PATH.
    tool_name
        Canonical MCP tool name to invoke (e.g. "InternalSearch").
    arguments
        Argument dict passed verbatim to the tool.
    args
        Optional CLI args for the binary (e.g. ``--include-tools=...``).
    timeout
        Per-call timeout in seconds. Covers both subprocess startup and
        the tool call itself.

    Returns
    -------
    str
        The concatenated text content from the MCP response.

    Raises
    ------
    FileNotFoundError
        When *binary* is not on PATH. Callers should convert this into
        a descriptive error string for the agent.
    asyncio.TimeoutError
        When the call exceeds *timeout* seconds.
    Exception
        Any other transport-level or protocol-level failure. Callers
        convert these into descriptive error strings for the agent.
    """
    if not is_binary_available(binary):
        raise FileNotFoundError(
            f"{binary!r} is not on PATH. Install it via "
            f"'toolbox install mcp-registry && mcp-registry install {binary}'."
        )

    return asyncio.run(_call_async(binary, tool_name, arguments, args, timeout))


async def _call_async(
    binary: str,
    tool_name: str,
    arguments: dict,
    args: Iterable[str],
    timeout: float,
) -> str:
    """Async core: open a stdio session, call one tool, extract text."""
    # Imported lazily so importing this module does not require the mcp
    # SDK to be installed (the OSS variant ships without it on PATH).
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=binary, args=list(args))

    async def _run() -> str:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return _extract_text(result)

    return await asyncio.wait_for(_run(), timeout=timeout)


def _extract_text(result: object) -> str:
    """Concatenate text-typed content blocks from an MCP CallToolResult.

    The MCP SDK returns a structured `CallToolResult` whose `content`
    list holds one or more content blocks. Text blocks expose a `text`
    attribute; non-text blocks are ignored. Multiple text blocks are
    joined with the same separator used by the JSON-RPC variant for
    consistency.
    """
    content = getattr(result, "content", None) or []
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n\n---\n\n".join(parts)


def log_call(log_path: Path, event: str, details: dict) -> None:
    """Append one JSON line to a per-tool call log. Never raises.

    Mirrors `_mcp_jsonrpc.log_call` so that downstream log-tailing
    tooling treats both transports identically.
    """
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"timestamp": datetime.now().isoformat(), "event": event, **details}
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:  # noqa: BLE001 — intentionally broad
        pass
