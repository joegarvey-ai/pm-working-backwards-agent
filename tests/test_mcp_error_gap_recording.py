"""Integration test: MCP error causes agent to note gap, not raise.

Validates Requirements 7.1, 7.2, 7.3: when an MCP call fails, the tool
returns a non-empty descriptive error string and does not raise, so the
agent can record it in its gap field.

Both BuilderMCPTool and OutlookMCPTool speak stdio to their canonical
binaries, so these tests patch _mcp_stdio.call_stdio_mcp (with the binary
reported present) to simulate transport-level failures.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from pm_agent_system.tools.builder_mcp import BuilderMCPTool
from pm_agent_system.tools.outlook_mcp import OutlookMCPTool


def _patch_binary_present():
    return patch(
        "pm_agent_system.tools._mcp_stdio.is_binary_available",
        return_value=True,
    )


# ---------------------------------------------------------------------------
# BuilderMCPTool: stdio failure returns descriptive string, does not raise
# ---------------------------------------------------------------------------


class TestBuilderMCPErrorGap:
    """BuilderMCPTool returns error strings on MCP failures."""

    def test_transport_error_returns_string_not_raises(self):
        """A transport error from call_stdio_mcp returns a descriptive string."""
        with _patch_binary_present(), patch(
            "pm_agent_system.tools.builder_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=RuntimeError("stdio transport failed"),
        ):
            result = BuilderMCPTool()._run(query="test", action="wiki_search")

        assert isinstance(result, str)
        assert len(result) > 0
        assert "error" in result.lower()

    def test_missing_binary_returns_descriptive_string(self):
        """A missing binary returns a string naming the binary, not a raise."""
        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ):
            result = BuilderMCPTool()._run(query="test", action="wiki_search")

        assert isinstance(result, str)
        assert "builder-mcp" in result
        assert "not found" in result.lower()

    def test_timeout_returns_error_string(self):
        """A call timeout returns a descriptive string, not a raise."""
        with _patch_binary_present(), patch(
            "pm_agent_system.tools.builder_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=asyncio.TimeoutError(),
        ):
            result = BuilderMCPTool()._run(query="test", action="wiki_search")

        assert isinstance(result, str)
        assert "timed out" in result.lower()


# ---------------------------------------------------------------------------
# OutlookMCPTool: stdio failure returns descriptive string, does not raise
# ---------------------------------------------------------------------------


class TestOutlookMCPErrorGap:
    """OutlookMCPTool returns error strings on MCP failures."""

    def test_transport_error_returns_string_not_raises(self):
        with _patch_binary_present(), patch(
            "pm_agent_system.tools.outlook_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=RuntimeError("stdio transport failed"),
        ):
            result = OutlookMCPTool()._run(query="test", action="calendar_search")

        assert isinstance(result, str)
        assert len(result) > 0
        assert "error" in result.lower()

    def test_missing_binary_returns_descriptive_string(self):
        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ):
            result = OutlookMCPTool()._run(query="test", action="calendar_search")

        assert isinstance(result, str)
        assert "aws-outlook-mcp" in result
        assert "not found" in result.lower()

    def test_timeout_returns_error_string(self):
        with _patch_binary_present(), patch(
            "pm_agent_system.tools.outlook_mcp._mcp_stdio.call_stdio_mcp",
            side_effect=asyncio.TimeoutError(),
        ):
            result = OutlookMCPTool()._run(query="test", action="calendar_search")

        assert isinstance(result, str)
        assert "timed out" in result.lower()
