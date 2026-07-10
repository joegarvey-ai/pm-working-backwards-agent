"""Unit tests for WorkingBackwardsAICritiqueTool.

The tool speaks stdio to the Working Backwards AI MCP client binary (same
pattern as builder_mcp), so these tests patch _mcp_stdio.call_stdio_mcp
and is_binary_available rather than a live service.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from pm_agent_system.tools.working_backwards_ai import WorkingBackwardsAICritiqueTool


def _patch_binary_present():
    return patch(
        "pm_agent_system.tools._mcp_stdio.is_binary_available",
        return_value=True,
    )


class TestRelay:
    """The tool forwards the draft verbatim and returns the critique verbatim."""

    def test_forwards_document_verbatim_and_returns_result(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            captured["binary"] = binary
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return "PERSONA CRITIQUE: the pricing assumption is unsupported."

        draft = "# Press Release\n\nToday we launch Foo. It costs $9/mo."
        with _patch_binary_present(), patch(
            "pm_agent_system.tools.working_backwards_ai._mcp_stdio.call_stdio_mcp",
            side_effect=fake_call,
        ):
            result = WorkingBackwardsAICritiqueTool()._run(
                document_text=draft, lens="senior_leader", focus="the pricing"
            )

        # Draft text is forwarded verbatim inside the prompt.
        assert draft in captured["arguments"]["prompt"]
        # The requested lens and focus are named in the prompt.
        assert "senior leader" in captured["arguments"]["prompt"].lower()
        assert "the pricing" in captured["arguments"]["prompt"]
        # Critique is returned verbatim.
        assert result == "PERSONA CRITIQUE: the pricing assumption is unsupported."

    def test_invalid_lens_falls_back_to_all(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            captured["arguments"] = arguments
            return "ok"

        with _patch_binary_present(), patch(
            "pm_agent_system.tools.working_backwards_ai._mcp_stdio.call_stdio_mcp",
            side_effect=fake_call,
        ):
            WorkingBackwardsAICritiqueTool()._run(
                document_text="draft", lens="not_a_real_lens"
            )

        # Unknown lens degrades to the all-lenses phrasing.
        assert "customer" in captured["arguments"]["prompt"].lower()


class TestGuards:
    """Input and transport guards never raise."""

    def test_empty_document_returns_error(self):
        result = WorkingBackwardsAICritiqueTool()._run(document_text="   ")
        assert isinstance(result, str)
        assert "required" in result.lower()

    def test_missing_binary_returns_descriptive_string(self):
        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ):
            result = WorkingBackwardsAICritiqueTool()._run(document_text="draft")
        assert isinstance(result, str)
        assert "not found" in result.lower()

    def test_transport_error_returns_string_not_raises(self):
        with _patch_binary_present(), patch(
            "pm_agent_system.tools.working_backwards_ai._mcp_stdio.call_stdio_mcp",
            side_effect=RuntimeError("stdio failed"),
        ):
            result = WorkingBackwardsAICritiqueTool()._run(document_text="draft")
        assert isinstance(result, str)
        assert "error" in result.lower()

    def test_timeout_returns_error_string(self):
        with _patch_binary_present(), patch(
            "pm_agent_system.tools.working_backwards_ai._mcp_stdio.call_stdio_mcp",
            side_effect=asyncio.TimeoutError(),
        ):
            result = WorkingBackwardsAICritiqueTool()._run(document_text="draft")
        assert isinstance(result, str)
        assert "timed out" in result.lower()


class TestCallLogging:
    """Invocation and response events are logged."""

    def test_logs_invocation_and_response(self, monkeypatch, tmp_path: Path):
        log_file = tmp_path / "wb_ai_mcp_calls.log"
        import pm_agent_system.tools.working_backwards_ai as wb_mod
        monkeypatch.setattr(wb_mod, "_CALL_LOG_PATH", log_file)

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            return "critique"

        with _patch_binary_present(), patch(
            "pm_agent_system.tools.working_backwards_ai._mcp_stdio.call_stdio_mcp",
            side_effect=fake_call,
        ):
            WorkingBackwardsAICritiqueTool()._run(document_text="draft", lens="customer")

        assert log_file.exists()
        import json

        events = [json.loads(line) for line in log_file.read_text().strip().splitlines()]
        types = [e["event"] for e in events]
        assert types[0] == "invocation"
        assert "response" in types
