"""Unit tests for BuilderMCPTool action mapping, error handling, and call logging.

The tool now uses the canonical Amazon ``builder-mcp`` binary over stdio
(via ``_mcp_stdio.call_stdio_mcp``) rather than HTTP/JSON-RPC. Tests mock
the stdio call and the PATH-availability check.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pm_agent_system.tools.builder_mcp import BuilderMCPTool


# ---------------------------------------------------------------------------
# Action-to-canonical-tool mapping (mirrors _ACTION_MAP in builder_mcp.py)
# ---------------------------------------------------------------------------

_ACTION_TO_REMOTE = {
    "wiki_search": "InternalSearch",
    "code_search": "InternalCodeSearch",
    "taskei_search": "TaskeiListTasks",
    "quip_search": "ReadInternalWebsites",
    "pipeline_search": "GetPipelineDetails",
}


def _patch_binary_present():
    """Make is_binary_available return True regardless of host PATH."""
    return patch(
        "pm_agent_system.tools._mcp_stdio.is_binary_available",
        return_value=True,
    )


# ---------------------------------------------------------------------------
# Action mapping tests
# ---------------------------------------------------------------------------


class TestActionMapping:
    """Each action dispatches to the correct canonical builder-mcp tool."""

    @pytest.mark.parametrize("action,expected_remote", list(_ACTION_TO_REMOTE.items()))
    def test_action_maps_to_correct_remote_tool(
        self,
        action: str,
        expected_remote: str,
    ) -> None:
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=60.0):
            captured["binary"] = binary
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return "mocked result"

        tool = BuilderMCPTool()

        with _patch_binary_present(), patch(
            "pm_agent_system.tools.builder_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=fake_call,
        ):
            result = tool._run(query="test query", action=action)

        assert captured["binary"] == "builder-mcp"
        assert captured["tool_name"] == expected_remote
        assert "test query" in str(captured["arguments"])
        assert result == "mocked result"


# ---------------------------------------------------------------------------
# Argument-shape tests for actions whose canonical tools take structured args
# ---------------------------------------------------------------------------


class TestArgumentShape:
    """Action argument builders produce the shapes the canonical tools expect."""

    def test_wiki_search_supplies_domain_wiki(self) -> None:
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=60.0):
            captured["arguments"] = arguments
            return ""

        tool = BuilderMCPTool()
        with _patch_binary_present(), patch(
            "pm_agent_system.tools.builder_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=fake_call,
        ):
            tool._run(query="anything", action="wiki_search", limit=5)

        assert captured["arguments"]["domain"] == "WIKI"
        assert captured["arguments"]["pageSize"] == 5

    def test_code_search_supplies_searchtype_code(self) -> None:
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=60.0):
            captured["arguments"] = arguments
            return ""

        tool = BuilderMCPTool()
        with _patch_binary_present(), patch(
            "pm_agent_system.tools.builder_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=fake_call,
        ):
            tool._run(query="MyClass", action="code_search")

        assert captured["arguments"]["searchType"] == "code"
        assert captured["arguments"]["query"] == "MyClass"

    def test_taskei_search_uses_contains_filter(self) -> None:
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=60.0):
            captured["arguments"] = arguments
            return ""

        tool = BuilderMCPTool()
        with _patch_binary_present(), patch(
            "pm_agent_system.tools.builder_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=fake_call,
        ):
            tool._run(
                query="needle",
                action="taskei_search",
                project_id="room-uuid-123",
                limit=20,
            )

        assert captured["arguments"]["name"]["queryOperator"] == "contains"
        assert captured["arguments"]["name"]["value"] == "needle"
        assert captured["arguments"]["roomId"] == "room-uuid-123"
        assert captured["arguments"]["pagination"]["maxResults"] == 20

    def test_pipeline_search_uses_pipelinename(self) -> None:
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=60.0):
            captured["arguments"] = arguments
            return ""

        tool = BuilderMCPTool()
        with _patch_binary_present(), patch(
            "pm_agent_system.tools.builder_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=fake_call,
        ):
            tool._run(query="MyPipeline", action="pipeline_search")

        assert captured["arguments"]["pipelineName"] == "MyPipeline"


# ---------------------------------------------------------------------------
# Error-path tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """The tool returns descriptive error strings, never raising."""

    def test_missing_binary_returns_install_hint(self) -> None:
        tool = BuilderMCPTool()
        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ), patch(
            "pm_agent_system.tools.builder_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=FileNotFoundError(
                "'builder-mcp' is not on PATH. Install it via "
                "'toolbox install mcp-registry && mcp-registry install builder-mcp'."
            ),
        ):
            result = tool._run(query="x", action="wiki_search")
        assert isinstance(result, str)
        assert "not found on PATH" in result
        assert "mcp-registry install builder-mcp" in result

    def test_timeout_returns_string(self) -> None:
        tool = BuilderMCPTool()
        with _patch_binary_present(), patch(
            "pm_agent_system.tools.builder_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=asyncio.TimeoutError(),
        ):
            result = tool._run(query="x", action="wiki_search")
        assert isinstance(result, str)
        assert "timed out" in result.lower()

    def test_generic_exception_returns_string(self) -> None:
        tool = BuilderMCPTool()
        with _patch_binary_present(), patch(
            "pm_agent_system.tools.builder_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=RuntimeError("boom"),
        ):
            result = tool._run(query="x", action="wiki_search")
        assert isinstance(result, str)
        assert "boom" in result

    def test_unknown_action_returns_descriptive_string(self) -> None:
        tool = BuilderMCPTool()
        with _patch_binary_present():
            result = tool._run(query="x", action="not_a_real_action")
        assert isinstance(result, str)
        assert "Unknown action" in result


# ---------------------------------------------------------------------------
# Call logging
# ---------------------------------------------------------------------------


class TestCallLogging:
    """BuilderMCPTool logs invocation and response events to the call log."""

    def test_logs_invocation_and_response_events(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        log_file = tmp_path / "builder_mcp_calls.log"

        import pm_agent_system.tools.builder_mcp as builder_mod
        monkeypatch.setattr(builder_mod, "_CALL_LOG_PATH", log_file)

        def fake_call(binary, tool_name, arguments, args=(), timeout=60.0):
            return "ok"

        tool = BuilderMCPTool()
        with _patch_binary_present(), patch(
            "pm_agent_system.tools.builder_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=fake_call,
        ):
            tool._run(query="log test", action="wiki_search")

        assert log_file.exists()
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) >= 2

        events = [json.loads(line) for line in lines]
        event_types = [e["event"] for e in events]
        assert event_types[0] == "invocation"
        assert "response" in event_types

        invocation = events[0]
        assert invocation["action"] == "wiki_search"
        assert invocation["query"] == "log test"

        response_event = next(e for e in events if e["event"] == "response")
        assert "response_chars" in response_event
        assert "response_preview" in response_event

    def test_logs_binary_missing_event(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        log_file = tmp_path / "builder_mcp_calls.log"

        import pm_agent_system.tools.builder_mcp as builder_mod
        monkeypatch.setattr(builder_mod, "_CALL_LOG_PATH", log_file)

        tool = BuilderMCPTool()
        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ), patch(
            "pm_agent_system.tools.builder_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=FileNotFoundError("binary missing"),
        ):
            tool._run(query="x", action="wiki_search")

        events = [json.loads(line) for line in log_file.read_text().splitlines()]
        event_types = [e["event"] for e in events]
        assert "binary_missing" in event_types
