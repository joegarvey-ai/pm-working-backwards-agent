"""Unit tests for VirtualPMCritiqueTool.

The tool speaks stdio to the virtual-pm-mcp binary (same pattern as
working_backwards_ai), so these tests patch _mcp_stdio.call_stdio_mcp and
is_binary_available rather than a live service.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from pm_agent_system.tools.virtual_pm_mcp import VirtualPMCritiqueTool


def _patch_binary_present():
    return patch(
        "pm_agent_system.tools._mcp_stdio.is_binary_available",
        return_value=True,
    )


def _patch_call(side_effect):
    return patch(
        "pm_agent_system.tools.virtual_pm_mcp._mcp_stdio.call_stdio_mcp",
        side_effect=side_effect,
    )


class TestRelay:
    def test_forwards_document_verbatim_and_returns_result(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            captured["binary"] = binary
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return "SCORE: 72/100. Weak success metrics."

        draft = "# Press Release\n\nToday we launch Foo."
        with _patch_binary_present(), _patch_call(fake_call):
            result = VirtualPMCritiqueTool()._run(document_text=draft, focus="the metrics")

        assert captured["tool_name"] == "sentinel_review"
        # Draft forwarded verbatim under the assumed 'spec' arg.
        assert captured["arguments"]["spec"] == draft
        assert captured["arguments"]["focus"] == "the metrics"
        assert result == "SCORE: 72/100. Weak success metrics."

    def test_focus_omitted_when_blank(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            captured["arguments"] = arguments
            return "ok"

        with _patch_binary_present(), _patch_call(fake_call):
            VirtualPMCritiqueTool()._run(document_text="draft")

        assert "focus" not in captured["arguments"]


class TestGuards:
    def test_empty_document_returns_error(self):
        result = VirtualPMCritiqueTool()._run(document_text="   ")
        assert isinstance(result, str)
        assert "required" in result.lower()

    def test_missing_binary_returns_descriptive_string(self):
        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ):
            result = VirtualPMCritiqueTool()._run(document_text="draft")
        assert isinstance(result, str)
        assert "not found" in result.lower()

    def test_transport_error_returns_string_not_raises(self):
        with _patch_binary_present(), _patch_call(RuntimeError("stdio failed")):
            result = VirtualPMCritiqueTool()._run(document_text="draft")
        assert isinstance(result, str)
        assert "error" in result.lower()

    def test_timeout_returns_error_string(self):
        with _patch_binary_present(), _patch_call(asyncio.TimeoutError()):
            result = VirtualPMCritiqueTool()._run(document_text="draft")
        assert isinstance(result, str)
        assert "timed out" in result.lower()


class TestCallLogging:
    def test_logs_invocation_and_response(self, monkeypatch, tmp_path: Path):
        log_file = tmp_path / "virtual_pm_mcp_calls.log"
        import pm_agent_system.tools.virtual_pm_mcp as mod
        monkeypatch.setattr(mod, "_CALL_LOG_PATH", log_file)

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            return "critique"

        with _patch_binary_present(), _patch_call(fake_call):
            VirtualPMCritiqueTool()._run(document_text="draft")

        assert log_file.exists()
        import json

        events = [json.loads(line) for line in log_file.read_text().strip().splitlines()]
        types = [e["event"] for e in events]
        assert types[0] == "invocation"
        assert "response" in types
