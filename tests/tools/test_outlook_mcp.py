"""Unit tests for OutlookMCPTool action mapping, retry, timeout, scrubber, and call logging.

Validates: Requirements 3.2, 3.3, 3.6, 7.5, 7.6
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from pm_agent_system.tools.outlook_mcp import OutlookMCPTool, _scrub_email_bodies


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code: int = 200, json_body: dict | None = None) -> httpx.Response:
    """Build a mock httpx.Response with the given status and JSON body."""
    if json_body is None:
        json_body = {
            "jsonrpc": "2.0",
            "result": {
                "content": [{"type": "text", "text": "mocked result"}],
            },
            "id": 1,
        }
    request = httpx.Request("POST", "https://fake-outlook.example.com/mcp")
    response = httpx.Response(status_code, json=json_body, request=request)
    return response


# ---------------------------------------------------------------------------
# Action mapping tests: one per action, asserting the remote tool name
# ---------------------------------------------------------------------------

_ACTION_TO_REMOTE = {
    "calendar_search": "search_calendar",
    "email_search": "search_email",
    "room_availability": "check_room_availability",
    "schedule_summary": "summarize_schedule",
}


class TestActionMapping:
    """Each action dispatches to the correct remote MCP tool name."""

    @pytest.mark.parametrize("action,expected_remote", list(_ACTION_TO_REMOTE.items()))
    def test_action_maps_to_correct_remote_tool(
        self,
        action: str,
        expected_remote: str,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("OUTLOOK_MCP_TOKEN", "test-token")
        monkeypatch.setenv("OUTLOOK_MCP_ENDPOINT", "https://fake-outlook.example.com/mcp")

        captured_payloads: list[dict] = []

        def fake_post(url, *, json, headers, timeout):
            captured_payloads.append(json)
            return _mock_response()

        tool = OutlookMCPTool()

        with patch("pm_agent_system.tools._mcp_jsonrpc.httpx.post", side_effect=fake_post):
            result = tool._run(query="test query", action=action)

        assert len(captured_payloads) == 1
        payload = captured_payloads[0]
        # The JSON-RPC envelope params.name must be the remote tool name.
        assert payload["params"]["name"] == expected_remote
        assert payload["method"] == "tools/call"
        # schedule_summary sends participants instead of query.
        if action != "schedule_summary":
            assert "test query" in str(payload["params"]["arguments"])


# ---------------------------------------------------------------------------
# Retry test: three attempts on transient HTTP 500
# ---------------------------------------------------------------------------


class TestRetry:
    """OutlookMCPTool retries three times on transient HTTP errors."""

    def test_retries_three_times_on_http_500(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OUTLOOK_MCP_TOKEN", "test-token")
        monkeypatch.setenv("OUTLOOK_MCP_ENDPOINT", "https://fake-outlook.example.com/mcp")

        call_count = 0

        def fake_post(url, *, json, headers, timeout):
            nonlocal call_count
            call_count += 1
            request = httpx.Request("POST", url)
            response = httpx.Response(500, request=request, text="Internal Server Error")
            response.raise_for_status()
            return response  # never reached

        tool = OutlookMCPTool()

        with patch("pm_agent_system.tools._mcp_jsonrpc.httpx.post", side_effect=fake_post):
            result = tool._run(query="retry test", action="calendar_search")

        # tenacity retries 3 times total (stop_after_attempt(3)).
        assert call_count == 3
        # The final result is an error string, not an exception.
        assert isinstance(result, str)
        assert "500" in result or "error" in result.lower()


# ---------------------------------------------------------------------------
# Timeout test: default 30-second timeout reaches httpx.post
# ---------------------------------------------------------------------------


class TestTimeout:
    """The default 30-second timeout is passed to httpx.post."""

    def test_default_timeout_is_30_seconds(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OUTLOOK_MCP_TOKEN", "test-token")
        monkeypatch.setenv("OUTLOOK_MCP_ENDPOINT", "https://fake-outlook.example.com/mcp")

        captured_timeouts: list[float] = []

        def fake_post(url, *, json, headers, timeout):
            captured_timeouts.append(timeout)
            return _mock_response()

        tool = OutlookMCPTool()

        with patch("pm_agent_system.tools._mcp_jsonrpc.httpx.post", side_effect=fake_post):
            tool._run(query="timeout test", action="calendar_search")

        assert len(captured_timeouts) == 1
        assert captured_timeouts[0] == 30.0


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
        monkeypatch.setenv("OUTLOOK_MCP_TOKEN", "test-token")
        monkeypatch.setenv("OUTLOOK_MCP_ENDPOINT", "https://fake-outlook.example.com/mcp")

        log_file = tmp_path / "outlook_mcp_calls.log"
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))

        # Patch the module-level _CALL_LOG_PATH to use our tmp_path.
        import pm_agent_system.tools.outlook_mcp as outlook_mod
        monkeypatch.setattr(outlook_mod, "_CALL_LOG_PATH", log_file)

        def fake_post(url, *, json, headers, timeout):
            return _mock_response()

        tool = OutlookMCPTool()

        with patch("pm_agent_system.tools._mcp_jsonrpc.httpx.post", side_effect=fake_post):
            tool._run(query="log test", action="calendar_search")

        # The log file should exist and contain at least two JSON lines.
        assert log_file.exists()
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) >= 2

        events = [json.loads(line) for line in lines]
        event_types = [e["event"] for e in events]

        # First event is invocation, last is response.
        assert event_types[0] == "invocation"
        assert "response" in event_types

        # Invocation event contains the action and query.
        invocation = events[0]
        assert invocation["action"] == "calendar_search"
        assert invocation["query"] == "log test"

        # Response event contains response metadata.
        response_event = next(e for e in events if e["event"] == "response")
        assert "response_chars" in response_event
        assert "response_preview" in response_event


# ---------------------------------------------------------------------------
# Scrubber example test: realistic email_search response
# ---------------------------------------------------------------------------


class TestScrubber:
    """Email body scrubbing for the email_search action."""

    def test_scrubs_body_from_email_search_response(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Feed a realistic email_search MCP response with a body field.

        Assert the returned string contains subject, from, date but no
        body, body_preview, or body_html.
        """
        monkeypatch.setenv("OUTLOOK_MCP_TOKEN", "test-token")
        monkeypatch.setenv("OUTLOOK_MCP_ENDPOINT", "https://fake-outlook.example.com/mcp")

        # Simulate a realistic MCP response with email body content.
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
        email_response = {
            "jsonrpc": "2.0",
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(email_data),
                    }
                ],
            },
            "id": 1,
        }

        def fake_post(url, *, json, headers, timeout):
            return _mock_response(json_body=email_response)

        tool = OutlookMCPTool()

        with patch("pm_agent_system.tools._mcp_jsonrpc.httpx.post", side_effect=fake_post):
            result = tool._run(query="Q4 planning", action="email_search")

        # The result should contain metadata fields.
        assert "Q4 Planning Review" in result
        assert "alice@example.com" in result
        assert "2024-01-15" in result

        # Parse the result and verify no scrub keys remain.
        parsed = json.loads(result)
        assert not _has_scrub_keys(parsed)

    def test_scrubber_conservative_fallback_for_non_json(self) -> None:
        """When the MCP response is not valid JSON, the scrubber returns
        a conservative error string rather than forwarding the raw body.
        """
        result = _scrub_email_bodies("this is not json at all")
        assert "could not be parsed" in result
        assert "privacy" in result.lower()

    def test_scrubber_conservative_fallback_for_scalar_json(self) -> None:
        """When the MCP response is valid JSON but a scalar (not dict/list),
        the scrubber returns a conservative error string.
        """
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
