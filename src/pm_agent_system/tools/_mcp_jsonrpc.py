"""Shared JSON-RPC helpers for internal Amazon MCP tools.

Private module (leading underscore) consumed by `builder_mcp.py` and
`outlook_mcp.py`. Not re-exported from `tools/__init__.py`.

This module provides the common plumbing for any CrewAI tool that talks
to a JSON-RPC MCP endpoint: the `MCPAuth` dataclass, envelope
construction, response text extraction, and header building. Auth
resolution, HTTP transport with retry, the end-to-end `call_mcp` helper,
and JSONL call logging live alongside these primitives and are added in
subsequent tasks (resolve_auth, post_with_retry, call_mcp, log_call).

All helpers here mirror the patterns established by
`DovetailSearchTool` so the two MCP tools can share one implementation
without drifting from the reference.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """Retry only transient failures.

    Transport-level errors and server-side / rate-limit statuses (429, 5xx)
    are worth retrying; other 4xx responses (400/401/403/404) are not — a
    retry cannot fix a bad request, expired auth, or a missing resource, so
    we fast-fail rather than burning exponential backoff first.
    """
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


@dataclass(frozen=True)
class MCPAuth:
    """Resolved auth material for one MCP call.

    Exactly one of `bearer_token` or `cookie_header` is set when auth
    succeeded. Both are None when no auth material is available; callers
    convert that state into a descriptive error string for the agent.
    """

    bearer_token: Optional[str]
    cookie_header: Optional[str]


def jsonrpc_envelope(
    tool_name: str,
    arguments: dict,
    request_id: int = 1,
) -> dict:
    """Produce the JSON-RPC 2.0 envelope for an MCP ``tools/call`` request.

    Invariants (see design Property 1):
      1. Top-level keys are exactly ``jsonrpc``, ``method``, ``params``, ``id``.
      2. ``jsonrpc`` is ``"2.0"``.
      3. ``method`` is ``"tools/call"``.
      4. ``params`` is ``{"name": tool_name, "arguments": arguments}`` with
         the caller's ``arguments`` dict nested verbatim.
      5. The envelope serializes to JSON and round-trips back to an equal
         dict.
    """
    return {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
        "id": request_id,
    }


def extract_text(response_json: dict) -> str:
    """Extract the text content from an MCP ``tools/call`` response.

    Mirrors ``DovetailSearchTool._extract_text``: joins ``result.content[*].text``
    with ``"\\n\\n---\\n\\n"``, returns ``""`` when the content list is empty
    or missing. Safe against missing keys and non-dict inputs.
    """
    if not isinstance(response_json, dict):
        return ""
    content = response_json.get("result", {}).get("content", [])
    if not content:
        return ""
    parts = [item.get("text", "") for item in content if item.get("text")]
    return "\n\n---\n\n".join(parts)


def build_headers(auth: MCPAuth) -> dict:
    """Produce HTTP headers for an MCP JSON-RPC call.

    Always includes ``Content-Type`` and ``Accept``. Adds either
    ``Authorization: Bearer {token}`` when ``auth.bearer_token`` is set,
    or ``Cookie: {cookie_header}`` when ``auth.cookie_header`` is set.
    When both fields are None, returns only the base headers; callers
    should detect that state before calling and return an auth error.
    """
    headers: dict = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if auth.bearer_token:
        headers["Authorization"] = f"Bearer {auth.bearer_token}"
    elif auth.cookie_header:
        headers["Cookie"] = auth.cookie_header
    return headers


def resolve_auth(
    cookie_path_env: str,
    token_env: str,
    logger,
) -> MCPAuth:
    """Resolve auth with cookie-first, token-fallback precedence.

    Called on every MCP invocation (no caching) because cookies expire.

    Precedence:
      1. If ``os.getenv(cookie_path_env)`` is set AND the file exists AND
         is non-empty, return ``MCPAuth(cookie_header=<contents stripped>)``.
      2. If the cookie path is set but the file is missing or empty, log a
         warning and fall through to the token path.
      3. If ``os.getenv(token_env)`` is non-empty, return
         ``MCPAuth(bearer_token=<token>)``.
      4. Otherwise return ``MCPAuth(bearer_token=None, cookie_header=None)``
         so the caller can convert to an auth error string.
    """
    cookie_path_raw = os.getenv(cookie_path_env, "").strip()
    if cookie_path_raw:
        cookie_file = Path(cookie_path_raw)
        if cookie_file.exists():
            try:
                contents = cookie_file.read_text().strip()
            except OSError:
                contents = ""
            if contents:
                return MCPAuth(bearer_token=None, cookie_header=contents)
            # File exists but is empty — fall through to token
            logger.warning(
                "%s is set to %s but the file is empty; "
                "falling back to token auth (%s)",
                cookie_path_env,
                cookie_path_raw,
                token_env,
            )
        else:
            logger.warning(
                "%s is set to %s but the file does not exist; "
                "falling back to token auth (%s)",
                cookie_path_env,
                cookie_path_raw,
                token_env,
            )

    # Token fallback
    token = os.getenv(token_env, "").strip()
    if token:
        return MCPAuth(bearer_token=token, cookie_header=None)

    # No auth material available
    return MCPAuth(bearer_token=None, cookie_header=None)


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def post_with_retry(
    url: str,
    json_payload: dict,
    headers: dict,
    timeout: float,
) -> httpx.Response:
    """POST with 3-retry exponential backoff; raises on final failure.

    Uses ``httpx.post`` for the HTTP call and calls
    ``response.raise_for_status()`` so that non-2xx responses trigger
    retries via tenacity. After three failed attempts the underlying
    ``httpx.HTTPStatusError`` (or transport-level exception) is reraised
    for the caller to convert into a descriptive error string.
    """
    response = httpx.post(url, json=json_payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response


def call_mcp(
    endpoint_url: str,
    auth: MCPAuth,
    tool_name: str,
    arguments: dict,
    timeout: float = 30.0,
) -> str:
    """End-to-end: build envelope, send with retry, extract text.

    Orchestrates the full JSON-RPC call lifecycle:
      1. Build the JSON-RPC 2.0 envelope via :func:`jsonrpc_envelope`.
      2. Build HTTP headers via :func:`build_headers`.
      3. POST with retry via :func:`post_with_retry`.
      4. Extract the text content via :func:`extract_text`.

    Returns the extracted text string on success.

    Raises ``httpx.HTTPStatusError`` or the underlying transport
    exception on final failure after retries; callers convert these
    to descriptive error strings for the agent.
    """
    envelope = jsonrpc_envelope(tool_name, arguments)
    headers = build_headers(auth)
    response = post_with_retry(endpoint_url, envelope, headers, timeout)
    return extract_text(response.json())


def log_call(log_path: Path, event: str, details: dict) -> None:
    """Append one JSON line to a per-tool call log. Never raises.

    Each line is a JSON object with ``timestamp``, ``event``, and all
    keys from ``details`` merged in.  Creates parent directories as
    needed.  Swallows **all** exceptions so that logging can never
    break a tool invocation, matching the Dovetail ``_log_call``
    contract.
    """
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"timestamp": datetime.now().isoformat(), "event": event, **details}
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:  # noqa: BLE001 — intentionally broad
        pass
