"""Ingest stakeholder feedback from Slack into the local feedback inbox.

This is the ingestion half of audit item #19. Unlike ``publish-doc`` /
``seed-taskei``, ingestion writes into the *local* ``output/feedback/``
directory (via ``feedback_inbox.write_feedback_item``), not to an external
system — so it needs no outward-facing write confirmation. It does, however,
*read* from Slack over the same MCP stdio transport as the other internal
integrations, and fails soft the same way when the binary / Midway session is
absent.

Transport:
- Slack is exposed by its own MCP Gateway client binary (default
  ``slack-mcp``, override with ``SLACK_MCP_BINARY``). The remote tool that
  returns channel messages is ``get_messages`` (override with
  ``SLACK_MCP_MESSAGES_TOOL``).
- The tool returns JSON text; we parse it defensively and tolerate a range of
  plausible shapes (a top-level ``messages`` array, a bare array, etc.) since
  the exact envelope is not pinned by the tool schema. Anything we cannot
  parse yields zero items and a descriptive (non-raising) error string.

Each Slack message becomes one ``FeedbackItem`` with ``status="open"``,
source attribution in both the ``source`` field and the markdown body, and a
generated ``fb-YYYY-MM-DD-NNN`` id.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from pm_agent_system.models.feedback_item import FeedbackItem
from pm_agent_system.tools import _mcp_stdio

logger = logging.getLogger(__name__)

_CALL_LOG_PATH = Path(os.getenv("OUTPUT_DIR", "./output")) / "write_back_calls.log"

_SLACK_BINARY = os.getenv("SLACK_MCP_BINARY", "slack-mcp").strip() or "slack-mcp"
_SLACK_MESSAGES_TOOL = os.getenv("SLACK_MCP_MESSAGES_TOOL", "get_messages").strip() or "get_messages"

_FETCH_TIMEOUT = 60.0
# Cap how many messages we pull in one ingest, to keep the inbox sane.
_DEFAULT_LIMIT = int(os.getenv("SLACK_MCP_INGEST_LIMIT", "50") or "50")


def _parse_messages(raw: str) -> list[dict]:
    """Best-effort extraction of a list of message dicts from the tool output.

    Tolerates several plausible envelopes:
    - ``{"messages": [ ... ]}``
    - a bare JSON array ``[ ... ]``
    - ``{"results"/"items"/"data": [ ... ]}``

    Returns an empty list when nothing parseable is found. Never raises.
    """
    if not raw or not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []

    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        candidates = None
        for key in ("messages", "results", "items", "data"):
            value = data.get(key)
            if isinstance(value, list):
                candidates = value
                break
        if candidates is None:
            # A single message object.
            candidates = [data] if data else []
    else:
        return []

    return [m for m in candidates if isinstance(m, dict)]


def _message_text(msg: dict) -> str:
    """Extract the human-readable text of a Slack message dict."""
    for key in ("text", "body", "message", "content"):
        value = msg.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _message_author(msg: dict) -> str:
    """Extract a human-readable author/source label from a message dict."""
    # Enriched slack-mcp responses often nest user details.
    user = msg.get("user")
    if isinstance(user, dict):
        for key in ("real_name", "name", "display_name", "id"):
            value = user.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("user_name", "username", "real_name", "user", "author"):
        value = msg.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown"


def _message_timestamp(msg: dict) -> datetime:
    """Best-effort parse of a Slack message timestamp to a tz-aware datetime.

    Slack ``ts`` is a stringified epoch-seconds float (e.g. "1710000000.123").
    Falls back to now (UTC) when absent/unparseable, so ingestion never fails
    on a missing timestamp.
    """
    ts = msg.get("ts") or msg.get("timestamp") or msg.get("date")
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return datetime.now(timezone.utc)
    if isinstance(ts, str) and ts.strip():
        # Epoch-seconds form.
        try:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            pass
        # ISO-8601 form.
        try:
            parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _to_feedback_item(msg: dict, channel: str, fb_id: str) -> FeedbackItem:
    """Map a Slack message dict to a FeedbackItem (status=open)."""
    author = _message_author(msg)
    text = _message_text(msg) or "(no text content)"
    received = _message_timestamp(msg)
    permalink = msg.get("permalink") or msg.get("permalink_public") or ""

    source = f"Slack {channel} ({author})"
    body_lines = [
        text,
        "",
        "---",
        f"_Ingested from Slack channel {channel}, author: {author}._",
    ]
    if isinstance(permalink, str) and permalink.strip():
        body_lines.append(f"_Permalink: {permalink.strip()}_")
    raw_text = "\n".join(body_lines)

    return FeedbackItem(
        id=fb_id,
        source=source,
        received=received,
        status="open",
        summary=text.splitlines()[0][:200] if text else "",
        raw_text=raw_text,
    )


def fetch_slack_feedback(channel: str, since: str | None = None) -> tuple[list[str], str | None]:
    """Fetch Slack messages and write them into the feedback inbox.

    Parameters
    ----------
    channel
        Slack channel name or ID.
    since
        Optional ISO-8601 start date passed through to the Slack tool.

    Returns
    -------
    (written_ids, error)
        ``written_ids`` is the list of feedback IDs written (possibly empty).
        ``error`` is ``None`` on success, or a descriptive string when the
        fetch failed (missing binary, timeout, transport error). Never raises;
        a fetch failure returns ``([], "Error: ...")``.
    """
    # Imported here (not at module load) so the feedback_inbox output dir is
    # resolved against the current OUTPUT_DIR at call time (tests set it).
    from pm_agent_system.feedback_inbox import next_feedback_id, write_feedback_item

    arguments: dict = {"channel": channel, "limit": _DEFAULT_LIMIT}
    if since:
        arguments["since"] = since

    _mcp_stdio.log_call(
        _CALL_LOG_PATH,
        "invocation",
        {"tool": _SLACK_MESSAGES_TOOL, "channel": channel, "since": since or ""},
    )

    if not _mcp_stdio.is_binary_available(_SLACK_BINARY):
        msg = (
            f"Error: {_SLACK_BINARY} binary not found on PATH; cannot ingest "
            f"Slack feedback. Install the Slack MCP client and run 'mwinit -f', "
            f"or set SLACK_MCP_BINARY to the installed client name."
        )
        _mcp_stdio.log_call(_CALL_LOG_PATH, "binary_missing", {"tool": _SLACK_MESSAGES_TOOL})
        return [], msg

    try:
        raw = _mcp_stdio.call_stdio_mcp(
            _SLACK_BINARY,
            _SLACK_MESSAGES_TOOL,
            arguments,
            timeout=_FETCH_TIMEOUT,
        )
    except FileNotFoundError as exc:
        _mcp_stdio.log_call(_CALL_LOG_PATH, "binary_missing", {"tool": _SLACK_MESSAGES_TOOL, "message": str(exc)})
        return [], f"Error: Slack MCP binary not found: {exc}"
    except asyncio.TimeoutError:
        _mcp_stdio.log_call(_CALL_LOG_PATH, "timeout", {"tool": _SLACK_MESSAGES_TOOL})
        return [], f"Error: Slack fetch timed out after {_FETCH_TIMEOUT:.0f}s."
    except Exception as exc:  # noqa: BLE001 — fail soft like the read tools
        _mcp_stdio.log_call(
            _CALL_LOG_PATH,
            "exception",
            {"tool": _SLACK_MESSAGES_TOOL, "type": type(exc).__name__, "message": str(exc)},
        )
        return [], f"Error: could not fetch Slack messages: {exc}"

    messages = _parse_messages(raw)
    _mcp_stdio.log_call(
        _CALL_LOG_PATH,
        "response",
        {"tool": _SLACK_MESSAGES_TOOL, "message_count": len(messages), "response_chars": len(raw)},
    )
    if not messages:
        return [], None

    written_ids: list[str] = []
    for msg in messages:
        # Skip messages with no usable text (join/leave system messages, etc.).
        if not _message_text(msg):
            continue
        fb_id = next_feedback_id()
        item = _to_feedback_item(msg, channel, fb_id)
        write_feedback_item(item)
        written_ids.append(fb_id)

    return written_ids, None
