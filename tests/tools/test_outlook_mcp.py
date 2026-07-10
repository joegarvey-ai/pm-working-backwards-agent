"""Unit tests for OutlookMCPTool: stdio action mapping, binary-missing
handling, scrubber, and call logging.

The tool speaks stdio to the canonical aws-outlook-mcp binary (same
pattern as builder_mcp), so these tests patch _mcp_stdio.call_stdio_mcp
and is_binary_available rather than an HTTP transport.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pm_agent_system.tools.outlook_mcp import OutlookMCPTool, _scrub_email_bodies


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_binary_present():
    """Make is_binary_available return True regardless of host PATH."""
    return patch(
        "pm_agent_system.tools._mcp_stdio.is_binary_available",
        return_value=True,
    )


# ---------------------------------------------------------------------------
# Action mapping tests: one per action, asserting the remote tool name
# ---------------------------------------------------------------------------

_ACTION_TO_REMOTE = {
    "calendar_search": "calendar_search",
    "email_search": "email_search",
    "room_availability": "calendar_room_booking",
    "schedule_summary": "calendar_availability",
}


class TestActionMapping:
    """Each action dispatches to the correct canonical aws-outlook-mcp tool."""

    @pytest.mark.parametrize("action,expected_remote", list(_ACTION_TO_REMOTE.items()))
    def test_action_maps_to_correct_remote_tool(
        self,
        action: str,
        expected_remote: str,
    ) -> None:
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=30.0):
            captured["binary"] = binary
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return "mocked result"

        tool = OutlookMCPTool()

        with _patch_binary_present(), patch(
            "pm_agent_system.tools.outlook_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=fake_call,
        ):
            result = tool._run(
                query="test query",
                action=action,
                participants="alice@example.com",
                building="SEA33",
                start_date="2026-01-01",
                end_date="2026-01-02",
            )

        assert captured["binary"] == "aws-outlook-mcp"
        assert captured["tool_name"] == expected_remote
        # email_search runs the result through the body scrubber, which
        # rewrites a non-JSON payload; the other actions pass it through.
        if action != "email_search":
            assert result == "mocked result"


class TestArgShapes:
    """Arguments match the real aws-outlook-mcp tool schemas."""

    def test_schedule_summary_sends_users_list(self) -> None:
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=30.0):
            captured["arguments"] = arguments
            return "ok"

        with _patch_binary_present(), patch(
            "pm_agent_system.tools.outlook_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=fake_call,
        ):
            OutlookMCPTool()._run(
                query="",
                action="schedule_summary",
                participants="alice@example.com, bob@example.com",
                start_date="2026-01-01",
                end_date="2026-01-02",
            )

        assert captured["arguments"]["users"] == [
            "alice@example.com",
            "bob@example.com",
        ]
        assert captured["arguments"]["startDate"] == "2026-01-01"
        assert captured["arguments"]["endDate"] == "2026-01-02"

    def test_room_availability_sends_building_and_times(self) -> None:
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=30.0):
            captured["arguments"] = arguments
            return "ok"

        with _patch_binary_present(), patch(
            "pm_agent_system.tools.outlook_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=fake_call,
        ):
            OutlookMCPTool()._run(
                query="",
                action="room_availability",
                building="SEA33",
                start_date="2026-01-01T09:00:00",
                end_date="2026-01-01T10:00:00",
            )

        assert captured["arguments"]["building"] == "SEA33"
        assert captured["arguments"]["startTime"] == "2026-01-01T09:00:00"
        assert captured["arguments"]["endTime"] == "2026-01-01T10:00:00"


# ---------------------------------------------------------------------------
# Binary-missing handling: never raises, returns a descriptive string
# ---------------------------------------------------------------------------


class TestBinaryMissing:
    """When the binary is absent, _run returns an error string, never raises."""

    def test_missing_binary_returns_error_string(self) -> None:
        tool = OutlookMCPTool()
        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ):
            result = tool._run(query="anything", action="calendar_search")
        assert isinstance(result, str)
        assert "aws-outlook-mcp" in result
        assert "not found" in result.lower()

    def test_unknown_action_returns_error_string(self) -> None:
        tool = OutlookMCPTool()
        with _patch_binary_present():
            result = tool._run(query="x", action="not_a_real_action")
        assert isinstance(result, str)
        assert "Unknown action" in result


# ---------------------------------------------------------------------------
# Call logging test: invocation and response events
# ---------------------------------------------------------------------------


class TestCallLogging:
    """OutlookMCPTool logs invocation and response events to the call log."""

    def test_logs_invocation_and_response_events(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        log_file = tmp_path / "outlook_mcp_calls.log"
        import pm_agent_system.tools.outlook_mcp as outlook_mod
        monkeypatch.setattr(outlook_mod, "_CALL_LOG_PATH", log_file)

        def fake_call(binary, tool_name, arguments, args=(), timeout=30.0):
            return "mocked result"

        tool = OutlookMCPTool()

        with _patch_binary_present(), patch(
            "pm_agent_system.tools.outlook_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=fake_call,
        ):
            tool._run(query="log test", action="calendar_search")

        assert log_file.exists()
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) >= 2

        events = [json.loads(line) for line in lines]
        event_types = [e["event"] for e in events]
        assert event_types[0] == "invocation"
        assert "response" in event_types

        invocation = events[0]
        assert invocation["action"] == "calendar_search"
        assert invocation["query"] == "log test"

        response_event = next(e for e in events if e["event"] == "response")
        assert "response_chars" in response_event
        assert "response_preview" in response_event


# ---------------------------------------------------------------------------
# Scrubber tests: email body content is removed for email_search
# ---------------------------------------------------------------------------


class TestScrubber:
    """Email body scrubbing for the email_search action."""

    def test_scrubs_body_from_email_search_response(self) -> None:
        email_data = {
            "emails": [
                {
                    "subject": "Q4 Planning Review",
                    "from": "alice@example.com",
                    "date": "2024-01-15T10:00:00Z",
                    "to": "bob@example.com",
                    "cc": "carol@example.com",
                    "body": "This is the full email body with sensitive content that should be scrubbed.",
                    "body_preview": "This is the preview...",
                    "body_html": "<html><body>Full HTML body</body></html>",
                    "summary": "Discussion about Q4 planning milestones.",
                }
            ]
        }

        def fake_call(binary, tool_name, arguments, args=(), timeout=30.0):
            return json.dumps(email_data)

        tool = OutlookMCPTool()

        with _patch_binary_present(), patch(
            "pm_agent_system.tools.outlook_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=fake_call,
        ):
            result = tool._run(query="Q4 planning", action="email_search")

        assert "Q4 Planning Review" in result
        assert "alice@example.com" in result
        assert "2024-01-15" in result

        parsed = json.loads(result)
        assert not _has_scrub_keys(parsed)

    def test_scrubber_conservative_fallback_for_non_json(self) -> None:
        result = _scrub_email_bodies("this is not json at all")
        assert "could not be parsed" in result
        assert "privacy" in result.lower()

    def test_scrubber_conservative_fallback_for_scalar_json(self) -> None:
        result = _scrub_email_bodies('"just a string"')
        assert "unrecognized shape" in result
        assert "privacy" in result.lower()


def _has_scrub_keys(node) -> bool:
    """Return True if any of body, body_preview, body_html appear at any depth."""
    scrub = {"body", "body_preview", "body_html"}
    if isinstance(node, dict):
        for key, value in node.items():
            if key in scrub:
                return True
            if _has_scrub_keys(value):
                return True
    elif isinstance(node, list):
        for item in node:
            if _has_scrub_keys(item):
                return True
    return False
