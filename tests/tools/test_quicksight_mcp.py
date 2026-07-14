"""Unit tests for QuickSightTool.

The tool speaks stdio to the quicksight-mcp binary (same pattern as
builder_mcp), so these tests patch _mcp_stdio.call_stdio_mcp and
is_binary_available rather than a live service.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from pm_agent_system.tools.quicksight_mcp import QuickSightTool


def _patch_binary_present():
    return patch(
        "pm_agent_system.tools._mcp_stdio.is_binary_available",
        return_value=True,
    )


def _patch_call(side_effect):
    return patch(
        "pm_agent_system.tools.quicksight_mcp._mcp_stdio.call_stdio_mcp",
        side_effect=side_effect,
    )


_URL = "https://us-east-1.quicksight.aws.amazon.com/sn/dashboards/abc"


class TestForwarding:
    def test_url_only_discovery_call(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            captured["binary"] = binary
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return '{"sheets": ["Sheet One"]}'

        with _patch_binary_present(), _patch_call(fake_call):
            result = QuickSightTool()._run(url=_URL)

        assert captured["tool_name"] == "get_dashboard_data"
        assert captured["arguments"] == {"url": _URL}
        # Blank sheet/visual/filters are NOT forwarded (they drive the flow).
        assert "sheet" not in captured["arguments"]
        assert result == '{"sheets": ["Sheet One"]}'

    def test_export_call_forwards_all_supplied_args(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            captured["arguments"] = arguments
            return "CSV: /tmp/out.csv (rows: 128)"

        with _patch_binary_present(), _patch_call(fake_call):
            result = QuickSightTool()._run(
                url=_URL, sheet="Sheet One", visual="all", filters="manager=someone"
            )

        args = captured["arguments"]
        assert args["url"] == _URL
        assert args["sheet"] == "Sheet One"
        assert args["visual"] == "all"
        assert args["filters"] == "manager=someone"
        # The tool surfaces the CSV path + row count verbatim (does not inline).
        assert "/tmp/out.csv" in result
        assert "rows: 128" in result


class TestGuards:
    def test_missing_url_returns_error(self):
        result = QuickSightTool()._run(url="   ")
        assert isinstance(result, str)
        assert "url" in result.lower() and "required" in result.lower()

    def test_missing_binary_returns_descriptive_string(self):
        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ):
            result = QuickSightTool()._run(url=_URL)
        assert isinstance(result, str)
        assert "not found" in result.lower()

    def test_transport_error_returns_string_not_raises(self):
        with _patch_binary_present(), _patch_call(RuntimeError("chromium boom")):
            result = QuickSightTool()._run(url=_URL)
        assert isinstance(result, str)
        assert "error" in result.lower()

    def test_timeout_returns_error_string(self):
        with _patch_binary_present(), _patch_call(asyncio.TimeoutError()):
            result = QuickSightTool()._run(url=_URL)
        assert isinstance(result, str)
        assert "timed out" in result.lower()


class TestCallLogging:
    def test_logs_invocation_and_response(self, monkeypatch, tmp_path: Path):
        log_file = tmp_path / "quicksight_mcp_calls.log"
        import pm_agent_system.tools.quicksight_mcp as mod
        monkeypatch.setattr(mod, "_CALL_LOG_PATH", log_file)

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            return "ok"

        with _patch_binary_present(), _patch_call(fake_call):
            QuickSightTool()._run(url=_URL)

        assert log_file.exists()
        import json

        events = [json.loads(line) for line in log_file.read_text().strip().splitlines()]
        types = [e["event"] for e in events]
        assert types[0] == "invocation"
        assert "response" in types
