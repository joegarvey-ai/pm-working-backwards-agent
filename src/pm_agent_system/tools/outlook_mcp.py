"""Outlook MCP tool for internal Amazon systems.

Wraps aws-outlook-mcp's JSON-RPC endpoint and exposes four actions:
  calendar_search    Search calendar events.
  email_search       Search email metadata (bodies are scrubbed).
  room_availability  Check room availability for a date range.
  schedule_summary   Summarize a participant's schedule.

Authentication resolves via the shared ``_mcp_jsonrpc`` helper: midway
cookie first, ``OUTLOOK_MCP_TOKEN`` fallback. When neither is available,
``_run`` returns a descriptive error string and never raises.

Email privacy (Requirement 3.6): the ``email_search`` action runs its
result through ``_scrub_email_bodies`` before returning. The scrubber
drops ``body``, ``body_preview``, and ``body_html`` keys at any depth
and preserves only metadata and summaries.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Type

import httpx
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from pm_agent_system.tools import _mcp_jsonrpc

logger = logging.getLogger(__name__)

_CALL_LOG_PATH = Path(os.getenv("OUTPUT_DIR", "./output")) / "outlook_mcp_calls.log"

# ---------------------------------------------------------------------------
# Action to remote MCP tool name mapping
# ---------------------------------------------------------------------------
_ACTION_MAP: dict[str, str] = {
    "calendar_search": "search_calendar",
    "email_search": "search_email",
    "room_availability": "check_room_availability",
    "schedule_summary": "summarize_schedule",
}

_VALID_ACTIONS = ", ".join(f"'{a}'" for a in _ACTION_MAP)


# ---------------------------------------------------------------------------
# Pydantic args schema
# ---------------------------------------------------------------------------
class OutlookMCPInput(BaseModel):
    """Input schema for OutlookMCPTool."""

    query: str = Field(
        ...,
        description="Free-text query. Required.",
    )
    action: str = Field(
        default="calendar_search",
        description=(
            "Action: 'calendar_search' | 'email_search' | "
            "'room_availability' | 'schedule_summary'."
        ),
    )
    start_date: str = Field(
        default="",
        description=(
            "Optional ISO-8601 start date for date-ranged queries."
        ),
    )
    end_date: str = Field(
        default="",
        description=(
            "Optional ISO-8601 end date for date-ranged queries."
        ),
    )
    participants: str = Field(
        default="",
        description=(
            "Optional comma-separated participant aliases or emails."
        ),
    )
    limit: int = Field(
        default=10,
        description="Max results (1 to 100).",
    )


# ---------------------------------------------------------------------------
# Email body scrubber (Requirement 3.6)
# ---------------------------------------------------------------------------
_SCRUB_KEYS = frozenset({"body", "body_preview", "body_html"})


def _scrub_node(node: Any) -> Any:
    """Recursively walk *node*, dropping scrubbed keys from dicts."""
    if isinstance(node, dict):
        cleaned: dict[str, Any] = {}
        for key, value in node.items():
            if key in _SCRUB_KEYS:
                continue
            cleaned[key] = _scrub_node(value)
        # When 'summary' is absent, generate a 200-char preview from the
        # original body content (if it was present before scrubbing).
        if "summary" not in cleaned and "subject" in cleaned:
            for body_key in ("body", "body_preview", "body_html"):
                body_val = node.get(body_key)
                if body_val and isinstance(body_val, str):
                    cleaned["preview"] = body_val[:200]
                    break
        return cleaned
    if isinstance(node, list):
        return [_scrub_node(item) for item in node]
    return node


def _scrub_email_bodies(raw_text: str) -> str:
    """Strip email body content from an MCP ``email_search`` response.

    Parses *raw_text* as JSON, recursively removes ``body``,
    ``body_preview``, and ``body_html`` keys at any depth, preserves
    ``subject``, ``from``, ``date``, ``to``, ``cc``, and ``summary``
    (or a first-200-character ``preview`` when ``summary`` is absent),
    then re-serializes.

    Returns a conservative error string when the input is not valid JSON
    or has an unrecognized shape, rather than forwarding the raw body.
    """
    try:
        parsed = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        return (
            "[outlook_mcp] email_search response could not be parsed; "
            "raw body withheld for privacy."
        )

    if not isinstance(parsed, (dict, list)):
        return (
            "[outlook_mcp] email_search response had an unrecognized shape; "
            "raw body withheld for privacy."
        )

    scrubbed = _scrub_node(parsed)
    return json.dumps(scrubbed, indent=2)


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------
class OutlookMCPTool(BaseTool):
    """Search Outlook calendar, email, and room data via aws-outlook-mcp.

    Supports four actions: calendar_search, email_search,
    room_availability, and schedule_summary. Requires OUTLOOK_MCP_TOKEN
    (or MIDWAY_COOKIE_PATH) and OUTLOOK_MCP_ENDPOINT to be set.
    """

    name: str = "outlook_mcp"
    description: str = (
        "Search Outlook calendar, email metadata, and room availability "
        "via aws-outlook-mcp. "
        "Actions: calendar_search, email_search, room_availability, "
        "schedule_summary."
    )
    args_schema: Type[BaseModel] = OutlookMCPInput

    # -- public entry point ------------------------------------------------

    def _run(
        self,
        query: str = "",
        action: str = "calendar_search",
        start_date: str = "",
        end_date: str = "",
        participants: str = "",
        limit: int = 10,
    ) -> str:
        _mcp_jsonrpc.log_call(
            _CALL_LOG_PATH,
            "invocation",
            {
                "action": action,
                "query": query,
                "start_date": start_date,
                "end_date": end_date,
                "participants": participants,
                "limit": limit,
            },
        )

        # --- auth ---------------------------------------------------------
        auth = _mcp_jsonrpc.resolve_auth(
            "MIDWAY_COOKIE_PATH", "OUTLOOK_MCP_TOKEN", logger
        )
        if auth.bearer_token is None and auth.cookie_header is None:
            msg = (
                "OUTLOOK_MCP_TOKEN not set in environment variables; "
                "set token or MIDWAY_COOKIE_PATH to enable outlook_mcp."
            )
            _mcp_jsonrpc.log_call(_CALL_LOG_PATH, "auth_error", {"message": msg})
            return msg

        # --- endpoint -----------------------------------------------------
        endpoint = os.getenv("OUTLOOK_MCP_ENDPOINT", "").strip()
        if not endpoint:
            msg = (
                "OUTLOOK_MCP_ENDPOINT not set in environment variables; "
                "set it to the aws-outlook-mcp JSON-RPC endpoint URL."
            )
            _mcp_jsonrpc.log_call(_CALL_LOG_PATH, "config_error", {"message": msg})
            return msg

        # --- clamp limit --------------------------------------------------
        limit = max(1, min(int(limit or 10), 100))

        # --- dispatch and call --------------------------------------------
        try:
            remote_tool_name, args = self._dispatch(
                action, query, start_date, end_date, participants, limit
            )
        except ValueError as exc:
            # Unknown action
            return str(exc)

        try:
            result = _mcp_jsonrpc.call_mcp(
                endpoint, auth, remote_tool_name, args, timeout=30.0
            )

            # Email privacy: scrub body content before returning
            if action == "email_search":
                result = _scrub_email_bodies(result)

            _mcp_jsonrpc.log_call(
                _CALL_LOG_PATH,
                "response",
                {
                    "action": action,
                    "response_chars": len(result),
                    "response_preview": result[:300],
                },
            )
            return result
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300] if exc.response else ""
            status = exc.response.status_code if exc.response else "unknown"
            msg = f"Outlook MCP error (HTTP {status}): {body}"
            _mcp_jsonrpc.log_call(
                _CALL_LOG_PATH,
                "http_error",
                {"action": action, "status": status, "body": body},
            )
            return msg
        except Exception as exc:  # noqa: BLE001
            msg = f"Error connecting to outlook_mcp: {exc}"
            _mcp_jsonrpc.log_call(
                _CALL_LOG_PATH,
                "exception",
                {"action": action, "type": type(exc).__name__, "message": str(exc)},
            )
            return msg

    # -- dispatch ----------------------------------------------------------

    @staticmethod
    def _dispatch(
        action: str,
        query: str,
        start_date: str,
        end_date: str,
        participants: str,
        limit: int,
    ) -> tuple[str, dict]:
        """Map *action* to the remote MCP tool name and build the args dict.

        Returns ``(remote_tool_name, arguments)`` on success.
        Raises ``ValueError`` for unknown actions.
        """
        remote_tool = _ACTION_MAP.get(action)
        if remote_tool is None:
            raise ValueError(
                f"Unknown action '{action}'. "
                f"Valid actions: {_VALID_ACTIONS}."
            )

        args: dict = {}

        if action == "calendar_search":
            args["query"] = query
            args["limit"] = limit
            if start_date:
                args["start_date"] = start_date
            if end_date:
                args["end_date"] = end_date
            if participants:
                args["participants"] = participants

        elif action == "email_search":
            args["query"] = query
            args["limit"] = limit
            if start_date:
                args["start_date"] = start_date
            if end_date:
                args["end_date"] = end_date

        elif action == "room_availability":
            args["query"] = query
            if start_date:
                args["start_date"] = start_date
            if end_date:
                args["end_date"] = end_date

        elif action == "schedule_summary":
            args["participants"] = participants
            if start_date:
                args["start_date"] = start_date
            if end_date:
                args["end_date"] = end_date

        return remote_tool, args
