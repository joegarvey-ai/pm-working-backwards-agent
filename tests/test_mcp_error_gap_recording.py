"""Integration test: MCP error causes agent to note gap, not raise.

Validates Requirements 7.1, 7.2, 7.3: when an MCP call fails with an
HTTP error, the tool returns a non-empty descriptive error string and
does not raise. The error string contains an identifiable MCP error
marker so the agent can record it in its gap field.

Tests cover both BuilderMCPTool and OutlookMCPTool.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from pm_agent_system.tools.builder_mcp import BuilderMCPTool
from pm_agent_system.tools.outlook_mcp import OutlookMCPTool


def _make_http_status_error(status_code: int = 500, body: str = "Internal Server Error"):
    """Create an httpx.HTTPStatusError with a mocked response."""
    request = httpx.Request("POST", "https://fake-endpoint/api/mcp")
    response = httpx.Response(status_code, request=request, text=body)
    return httpx.HTTPStatusError(
        message=f"Server error '{status_code}'",
        request=request,
        response=response,
    )


# ---------------------------------------------------------------------------
# BuilderMCPTool: HTTP error returns descriptive string, does not raise
# ---------------------------------------------------------------------------


class TestBuilderMCPErrorGap:
    """BuilderMCPTool returns error strings on MCP failures."""

    def test_http_error_returns_string_not_raises(self, monkeypatch):
        """An HTTP 500 from call_mcp returns a descriptive error string."""
        monkeypatch.setenv("BUILDER_MCP_TOKEN", "test-token")
        monkeypatch.setenv("BUILDER_MCP_ENDPOINT", "https://fake-builder/api/mcp")

        error = _make_http_status_error(500, "Internal Server Error")

        with patch("pm_agent_system.tools._mcp_jsonrpc.call_mcp", side_effect=error):
            tool = BuilderMCPTool()
            result = tool._run(query="test", action="wiki_search")

        assert isinstance(result, str)
        assert len(result) > 0
        assert "error" in result.lower() or "HTTP" in result

    def test_http_403_returns_descriptive_string(self, monkeypatch):
        """An HTTP 403 returns a string containing the status code."""
        monkeypatch.setenv("BUILDER_MCP_TOKEN", "test-token")
        monkeypatch.setenv("BUILDER_MCP_ENDPOINT", "https://fake-builder/api/mcp")

        error = _make_http_status_error(403, "Forbidden")

        with patch("pm_agent_system.tools._mcp_jsonrpc.call_mcp", side_effect=error):
            tool = BuilderMCPTool()
            result = tool._run(query="test", action="wiki_search")

        assert isinstance(result, str)
        assert "403" in result
        assert "HTTP" in result

    def test_generic_exception_returns_error_string(self, monkeypatch):
        """A generic connection error returns a descriptive string."""
        monkeypatch.setenv("BUILDER_MCP_TOKEN", "test-token")
        monkeypatch.setenv("BUILDER_MCP_ENDPOINT", "https://fake-builder/api/mcp")

        with patch(
            "pm_agent_system.tools._mcp_jsonrpc.call_mcp",
            side_effect=ConnectionError("Connection refused"),
        ):
            tool = BuilderMCPTool()
            result = tool._run(query="test", action="wiki_search")

        assert isinstance(result, str)
        assert len(result) > 0
        assert "error" in result.lower() or "Error" in result


# ---------------------------------------------------------------------------
# OutlookMCPTool: HTTP error returns descriptive string, does not raise
# ---------------------------------------------------------------------------


class TestOutlookMCPErrorGap:
    """OutlookMCPTool returns error strings on MCP failures."""

    def test_http_error_returns_string_not_raises(self, monkeypatch):
        """An HTTP 500 from call_mcp returns a descriptive error string."""
        monkeypatch.setenv("OUTLOOK_MCP_TOKEN", "test-token")
        monkeypatch.setenv("OUTLOOK_MCP_ENDPOINT", "https://fake-outlook/api/mcp")

        error = _make_http_status_error(500, "Internal Server Error")

        with patch("pm_agent_system.tools._mcp_jsonrpc.call_mcp", side_effect=error):
            tool = OutlookMCPTool()
            result = tool._run(query="test", action="calendar_search")

        assert isinstance(result, str)
        assert len(result) > 0
        assert "error" in result.lower() or "HTTP" in result

    def test_http_403_returns_descriptive_string(self, monkeypatch):
        """An HTTP 403 returns a string containing the status code."""
        monkeypatch.setenv("OUTLOOK_MCP_TOKEN", "test-token")
        monkeypatch.setenv("OUTLOOK_MCP_ENDPOINT", "https://fake-outlook/api/mcp")

        error = _make_http_status_error(403, "Forbidden")

        with patch("pm_agent_system.tools._mcp_jsonrpc.call_mcp", side_effect=error):
            tool = OutlookMCPTool()
            result = tool._run(query="test", action="calendar_search")

        assert isinstance(result, str)
        assert "403" in result
        assert "HTTP" in result

    def test_generic_exception_returns_error_string(self, monkeypatch):
        """A generic connection error returns a descriptive string."""
        monkeypatch.setenv("OUTLOOK_MCP_TOKEN", "test-token")
        monkeypatch.setenv("OUTLOOK_MCP_ENDPOINT", "https://fake-outlook/api/mcp")

        with patch(
            "pm_agent_system.tools._mcp_jsonrpc.call_mcp",
            side_effect=ConnectionError("Connection refused"),
        ):
            tool = OutlookMCPTool()
            result = tool._run(query="test", action="calendar_search")

        assert isinstance(result, str)
        assert len(result) > 0
        assert "error" in result.lower() or "Error" in result
