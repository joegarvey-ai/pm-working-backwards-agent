"""Outlook MCP tool for internal Amazon systems.

Wraps the canonical ``aws-outlook-mcp`` server, a stdio MCP binary, and
exposes four actions mapped to the server's real tool names:

  calendar_search    -> calendar_search       (search events by keyword)
  email_search       -> email_search          (search email; bodies scrubbed)
  room_availability  -> calendar_room_booking (find open meeting rooms)
  schedule_summary   -> calendar_availability (free/busy for attendees)

Transport is stdio (same pattern as ``builder_mcp``): the binary is
launched per call and auth (Midway cookie) is handled by the binary
itself. When ``aws-outlook-mcp`` is not on PATH, ``_run`` returns a
descriptive error string and never raises, so the OSS variant of the
pipeline runs unchanged outside Amazon.

Email privacy: the ``email_search`` action runs its result through
``_scrub_email_bodies`` before returning. The scrubber drops ``body``,
``body_preview``, and ``body_html`` keys at any depth and preserves only
metadata and summaries.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from pm_agent_system.tools import _mcp_stdio

logger = logging.getLogger(__name__)

_CALL_LOG_PATH = Path(os.getenv("OUTPUT_DIR", "./output")) / "outlook_mcp_calls.log"

_BINARY_NAME = "aws-outlook-mcp"

# ---------------------------------------------------------------------------
# Action -> (canonical aws-outlook-mcp tool name) mapping
# ---------------------------------------------------------------------------
_ACTION_MAP: dict[str, str] = {
    "calendar_search": "calendar_search",
    "email_search": "email_search",
    "room_availability": "calendar_room_booking",
    "schedule_summary": "calendar_availability",
}

_VALID_ACTIONS = ", ".join(f"'{a}'" for a in _ACTION_MAP)


# ---------------------------------------------------------------------------
# Pydantic args schema
# ---------------------------------------------------------------------------
class OutlookMCPInput(BaseModel):
    """Input schema for OutlookMCPTool."""

    query: str = Field(
        ...,
        description="Free-text query (event/email keywords). Required.",
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
        description="Optional start date (YYYY-MM-DD) for date-ranged queries.",
    )
    end_date: str = Field(
        default="",
        description="Optional end date (YYYY-MM-DD) for date-ranged queries.",
    )
    participants: str = Field(
        default="",
        description=(
            "Comma-separated attendee emails for schedule_summary "
            "(free/busy). Required for that action."
        ),
    )
    building: str = Field(
        default="",
        description=(
            "Building code for room_availability (e.g. 'SEA33'). Required "
            "for that action."
        ),
    )
    limit: int = Field(
        default=10,
        description="Max results (1 to 100).",
    )


# ---------------------------------------------------------------------------
# Email body scrubber
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
    room_availability, and schedule_summary. Requires the
    ``aws-outlook-mcp`` binary on PATH and a valid Midway session
    (``mwinit -f``). Auth is handled by the binary; no env vars are
    required from this tool.
    """

    name: str = "outlook_mcp"
    description: str = (
        "Search Outlook calendar, email metadata, meeting-room availability, "
        "and attendee free/busy via aws-outlook-mcp. "
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
        building: str = "",
        limit: int = 10,
    ) -> str:
        _mcp_stdio.log_call(
            _CALL_LOG_PATH,
            "invocation",
            {
                "action": action,
                "query": query,
                "start_date": start_date,
                "end_date": end_date,
                "participants": participants,
                "building": building,
                "limit": limit,
            },
        )

        # --- clamp limit --------------------------------------------------
        limit = max(1, min(int(limit or 10), 100))

        # --- dispatch -----------------------------------------------------
        try:
            remote_tool_name, arguments = self._dispatch(
                action, query, start_date, end_date, participants, building, limit
            )
        except ValueError as exc:
            return str(exc)

        # --- call ---------------------------------------------------------
        try:
            result = _mcp_stdio.call_stdio_mcp(
                _BINARY_NAME,
                remote_tool_name,
                arguments,
                timeout=30.0,
            )

            # Email privacy: scrub body content before returning.
            if action == "email_search":
                result = _scrub_email_bodies(result)

            _mcp_stdio.log_call(
                _CALL_LOG_PATH,
                "response",
                {
                    "action": action,
                    "response_chars": len(result),
                    "response_preview": result[:300],
                },
            )
            return result
        except FileNotFoundError as exc:
            msg = (
                f"aws-outlook-mcp binary not found on PATH; install via "
                f"'toolbox install mcp-registry && mcp-registry install "
                f"aws-outlook-mcp' and run 'mwinit -f'. ({exc})"
            )
            _mcp_stdio.log_call(
                _CALL_LOG_PATH, "binary_missing", {"action": action, "message": str(exc)}
            )
            return msg
        except asyncio.TimeoutError:
            msg = f"Outlook MCP call timed out (action={action})."
            _mcp_stdio.log_call(_CALL_LOG_PATH, "timeout", {"action": action})
            return msg
        except Exception as exc:  # noqa: BLE001
            msg = f"Error connecting to outlook_mcp: {exc}"
            _mcp_stdio.log_call(
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
        building: str,
        limit: int,
    ) -> tuple[str, dict]:
        """Map *action* to the aws-outlook-mcp tool name and build its args.

        Returns ``(remote_tool_name, arguments)`` on success. Raises
        ``ValueError`` for unknown actions. Argument shapes match the
        server's real schemas (calendar_search/email_search take ``query``;
        calendar_availability takes ``users``/``startDate``/``endDate``;
        calendar_room_booking takes ``building``/``startTime``/``endTime``).
        """
        remote_tool = _ACTION_MAP.get(action)
        if remote_tool is None:
            raise ValueError(
                f"Unknown action '{action}'. Valid actions: {_VALID_ACTIONS}."
            )

        args: dict = {}

        if action == "calendar_search":
            args["query"] = query
            args["limit"] = limit

        elif action == "email_search":
            args["query"] = query
            args["limit"] = limit
            if start_date:
                args["startDate"] = start_date
            if end_date:
                args["endDate"] = end_date

        elif action == "schedule_summary":
            # calendar_availability: users + startDate + endDate (all required).
            users = [p.strip() for p in participants.split(",") if p.strip()]
            args["users"] = users
            if start_date:
                args["startDate"] = start_date
            if end_date:
                args["endDate"] = end_date

        elif action == "room_availability":
            # calendar_room_booking: building + startTime + endTime (required).
            args["building"] = building
            if start_date:
                args["startTime"] = start_date
            if end_date:
                args["endTime"] = end_date

        return remote_tool, args
