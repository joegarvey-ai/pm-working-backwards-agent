"""Unit tests for PippinReadTool.

The tool speaks stdio to the python-pippin-mcp binary (same pattern as
builder_mcp), so these tests patch _mcp_stdio.call_stdio_mcp and
is_binary_available rather than a live service. This tool is READ-only —
create/update stay in the human-gated publish path.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from pm_agent_system.tools.pippin_mcp import PippinReadTool


def _patch_binary_present():
    return patch(
        "pm_agent_system.tools._mcp_stdio.is_binary_available",
        return_value=True,
    )


def _patch_call(side_effect):
    return patch(
        "pm_agent_system.tools.pippin_mcp._mcp_stdio.call_stdio_mcp",
        side_effect=side_effect,
    )


class TestActions:
    def test_list_projects_needs_no_ids(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=60.0):
            captured["binary"] = binary
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return '{"projects": []}'

        with _patch_binary_present(), _patch_call(fake_call):
            result = PippinReadTool()._run(action="list_projects", limit=25)

        assert captured["binary"] == "python-pippin-mcp"
        assert captured["tool_name"] == "list_projects"
        assert captured["arguments"] == {"max_results": 25}
        assert result == '{"projects": []}'

    def test_list_artifacts_forwards_project_id(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=60.0):
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return "artifacts"

        with _patch_binary_present(), _patch_call(fake_call):
            PippinReadTool()._run(action="list_artifacts", project_id="proj-1", limit=10)

        assert captured["tool_name"] == "list_artifacts"
        assert captured["arguments"] == {"project_id": "proj-1", "max_results": 10}

    def test_get_artifact_forwards_both_ids(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=60.0):
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return "artifact body"

        with _patch_binary_present(), _patch_call(fake_call):
            PippinReadTool()._run(action="get_artifact", project_id="proj-1", design_id="art-9")

        assert captured["tool_name"] == "get_artifact"
        assert captured["arguments"] == {"project_id": "proj-1", "design_id": "art-9"}

    def test_get_comments_forwards_both_ids(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=60.0):
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return "comments"

        with _patch_binary_present(), _patch_call(fake_call):
            PippinReadTool()._run(action="get_comments", project_id="proj-1", design_id="art-9")

        assert captured["tool_name"] == "get_comments"
        assert captured["arguments"] == {"project_id": "proj-1", "design_id": "art-9"}


class TestGuards:
    def test_unknown_action_returns_string(self):
        result = PippinReadTool()._run(action="create_artifact")
        assert isinstance(result, str)
        assert "unknown action" in result.lower()

    def test_list_artifacts_requires_project(self):
        result = PippinReadTool()._run(action="list_artifacts", project_id="")
        assert "project_id" in result.lower()

    def test_get_artifact_requires_design(self):
        result = PippinReadTool()._run(action="get_artifact", project_id="proj-1", design_id="")
        assert "design_id" in result.lower()

    def test_missing_binary_returns_descriptive_string(self):
        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ):
            result = PippinReadTool()._run(action="list_projects")
        assert isinstance(result, str)
        assert "not found" in result.lower()

    def test_transport_error_returns_string_not_raises(self):
        with _patch_binary_present(), _patch_call(RuntimeError("stdio boom")):
            result = PippinReadTool()._run(action="list_projects")
        assert isinstance(result, str)
        assert "error" in result.lower()

    def test_timeout_returns_error_string(self):
        with _patch_binary_present(), _patch_call(asyncio.TimeoutError()):
            result = PippinReadTool()._run(action="list_projects")
        assert isinstance(result, str)
        assert "timed out" in result.lower()


class TestReadOnly:
    """The tool exposes no create/update/delete action."""

    def test_action_map_is_read_only(self):
        from pm_agent_system.tools import pippin_mcp

        for action in pippin_mcp._ACTION_MAP:
            assert not any(
                w in action for w in ("create", "update", "delete", "publish", "write")
            ), f"Pippin read tool must not expose write action {action!r}"


class TestCallLogging:
    def test_logs_invocation_and_response(self, monkeypatch, tmp_path: Path):
        log_file = tmp_path / "pippin_mcp_calls.log"
        import pm_agent_system.tools.pippin_mcp as mod
        monkeypatch.setattr(mod, "_CALL_LOG_PATH", log_file)

        def fake_call(binary, tool_name, arguments, args=(), timeout=60.0):
            return "ok"

        with _patch_binary_present(), _patch_call(fake_call):
            PippinReadTool()._run(action="list_projects")

        assert log_file.exists()
        import json

        events = [json.loads(line) for line in log_file.read_text().strip().splitlines()]
        types = [e["event"] for e in events]
        assert types[0] == "invocation"
        assert "response" in types
