"""Unit tests for SoftwareCatalogTool.

The tool speaks stdio to the software-catalog-mcp binary (same pattern as
builder_mcp), so these tests patch _mcp_stdio.call_stdio_mcp and
is_binary_available rather than a live service.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from pm_agent_system.tools.software_catalog_mcp import SoftwareCatalogTool


def _patch_binary_present():
    return patch(
        "pm_agent_system.tools._mcp_stdio.is_binary_available",
        return_value=True,
    )


def _patch_call(side_effect):
    return patch(
        "pm_agent_system.tools.software_catalog_mcp._mcp_stdio.call_stdio_mcp",
        side_effect=side_effect,
    )


class TestActions:
    def test_lookup_forwards_name_and_returns_result(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=60.0):
            captured["binary"] = binary
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return "Service: WidgetService (owner: team-x)"

        with _patch_binary_present(), _patch_call(fake_call):
            result = SoftwareCatalogTool()._run(query="WidgetService", action="lookup", limit=5)

        assert captured["tool_name"] == "lookup_entity"
        assert captured["arguments"]["name"] == "WidgetService"
        assert captured["arguments"]["limit"] == 5
        assert result == "Service: WidgetService (owner: team-x)"

    def test_cypher_forwards_query(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=60.0):
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return "rows: 3"

        with _patch_binary_present(), _patch_call(fake_call):
            SoftwareCatalogTool()._run(action="cypher", cypher="MATCH (n) RETURN n LIMIT 3")

        assert captured["tool_name"] == "run_cypher"
        assert captured["arguments"]["query"] == "MATCH (n) RETURN n LIMIT 3"

    def test_limit_clamped(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=60.0):
            captured["arguments"] = arguments
            return "ok"

        with _patch_binary_present(), _patch_call(fake_call):
            SoftwareCatalogTool()._run(query="x", action="lookup", limit=999)

        assert captured["arguments"]["limit"] == 50


class TestGuards:
    def test_unknown_action_returns_string(self):
        result = SoftwareCatalogTool()._run(query="x", action="delete_everything")
        assert isinstance(result, str)
        assert "unknown action" in result.lower()

    def test_lookup_requires_query(self):
        result = SoftwareCatalogTool()._run(query="  ", action="lookup")
        assert "requires" in result.lower()

    def test_cypher_requires_query(self):
        result = SoftwareCatalogTool()._run(action="cypher", cypher="")
        assert "requires" in result.lower()

    def test_missing_binary_returns_descriptive_string(self):
        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ):
            result = SoftwareCatalogTool()._run(query="x", action="lookup")
        assert isinstance(result, str)
        assert "not found" in result.lower()

    def test_transport_error_returns_string_not_raises(self):
        with _patch_binary_present(), _patch_call(RuntimeError("neptune boom")):
            result = SoftwareCatalogTool()._run(query="x", action="lookup")
        assert isinstance(result, str)
        assert "error" in result.lower()

    def test_timeout_returns_error_string(self):
        with _patch_binary_present(), _patch_call(asyncio.TimeoutError()):
            result = SoftwareCatalogTool()._run(query="x", action="lookup")
        assert isinstance(result, str)
        assert "timed out" in result.lower()


class TestCallLogging:
    def test_logs_invocation_and_response(self, monkeypatch, tmp_path: Path):
        log_file = tmp_path / "software_catalog_mcp_calls.log"
        import pm_agent_system.tools.software_catalog_mcp as mod
        monkeypatch.setattr(mod, "_CALL_LOG_PATH", log_file)

        def fake_call(binary, tool_name, arguments, args=(), timeout=60.0):
            return "ok"

        with _patch_binary_present(), _patch_call(fake_call):
            SoftwareCatalogTool()._run(query="x", action="lookup")

        assert log_file.exists()
        import json

        events = [json.loads(line) for line in log_file.read_text().strip().splitlines()]
        types = [e["event"] for e in events]
        assert types[0] == "invocation"
        assert "response" in types
