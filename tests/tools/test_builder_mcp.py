"""Unit tests for BuilderMCPTool action mapping, retry, timeout, and call logging.

Validates: Requirements 1.2, 1.3, 7.4, 7.6
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import httpx
import pytest

from pm_agent_system.tools.builder_mcp import BuilderMCPTool


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
    request = httpx.Request("POST", "https://fake-builder.example.com/mcp")
    response = httpx.Response(status_code, json=json_body, request=request)
    return response


# ---------------------------------------------------------------------------
# Action mapping tests: one per action, asserting the remote tool name
# ---------------------------------------------------------------------------

_ACTION_TO_REMOTE = {
    "wiki_search": "search_wiki",
    "code_search": "search_code",
    "taskei_search": "search_taskei",
    "quip_search": "search_quip",
    "pipeline_search": "search_pipelines",
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
        monkeypatch.setenv("BUILDER_MCP_TOKEN", "test-token")
        monkeypatch.setenv("BUILDER_MCP_ENDPOINT", "https://fake-builder.example.com/mcp")

        captured_payloads: list[dict] = []

        def fake_post(url, *, json, headers, timeout):
            captured_payloads.append(json)
            return _mock_response()

        tool = BuilderMCPTool()

        with patch("pm_agent_system.tools._mcp_jsonrpc.httpx.post", side_effect=fake_post):
            result = tool._run(query="test query", action=action)

        assert len(captured_payloads) == 1
        payload = captured_payloads[0]
        # The JSON-RPC envelope params.name must be the remote tool name.
        assert payload["params"]["name"] == expected_remote
        assert payload["method"] == "tools/call"
        assert "test query" in str(payload["params"]["arguments"])


# ---------------------------------------------------------------------------
# Retry test: three attempts on transient HTTP 500
# ---------------------------------------------------------------------------


class TestRetry:
    """BuilderMCPTool retries three times on transient HTTP errors."""

    def test_retries_three_times_on_http_500(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("BUILDER_MCP_TOKEN", "test-token")
        monkeypatch.setenv("BUILDER_MCP_ENDPOINT", "https://fake-builder.example.com/mcp")

        call_count = 0

        def fake_post(url, *, json, headers, timeout):
            nonlocal call_count
            call_count += 1
            request = httpx.Request("POST", url)
            response = httpx.Response(500, request=request, text="Internal Server Error")
            response.raise_for_status()
            return response  # never reached

        tool = BuilderMCPTool()

        with patch("pm_agent_system.tools._mcp_jsonrpc.httpx.post", side_effect=fake_post):
            result = tool._run(query="retry test", action="wiki_search")

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
        monkeypatch.setenv("BUILDER_MCP_TOKEN", "test-token")
        monkeypatch.setenv("BUILDER_MCP_ENDPOINT", "https://fake-builder.example.com/mcp")

        captured_timeouts: list[float] = []

        def fake_post(url, *, json, headers, timeout):
            captured_timeouts.append(timeout)
            return _mock_response()

        tool = BuilderMCPTool()

        with patch("pm_agent_system.tools._mcp_jsonrpc.httpx.post", side_effect=fake_post):
            tool._run(query="timeout test", action="wiki_search")

        assert len(captured_timeouts) == 1
        assert captured_timeouts[0] == 30.0


# ---------------------------------------------------------------------------
# Call logging test: invocation and response events
# ---------------------------------------------------------------------------


class TestCallLogging:
    """BuilderMCPTool logs invocation and response events to the call log."""

    def test_logs_invocation_and_response_events(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("BUILDER_MCP_TOKEN", "test-token")
        monkeypatch.setenv("BUILDER_MCP_ENDPOINT", "https://fake-builder.example.com/mcp")

        log_file = tmp_path / "builder_mcp_calls.log"
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))

        # Patch the module-level _CALL_LOG_PATH to use our tmp_path.
        import pm_agent_system.tools.builder_mcp as builder_mod
        monkeypatch.setattr(builder_mod, "_CALL_LOG_PATH", log_file)

        def fake_post(url, *, json, headers, timeout):
            return _mock_response()

        tool = BuilderMCPTool()

        with patch("pm_agent_system.tools._mcp_jsonrpc.httpx.post", side_effect=fake_post):
            tool._run(query="log test", action="wiki_search")

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
        assert invocation["action"] == "wiki_search"
        assert invocation["query"] == "log test"

        # Response event contains response metadata.
        response_event = next(e for e in events if e["event"] == "response")
        assert "response_chars" in response_event
        assert "response_preview" in response_event
