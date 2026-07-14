"""Unit tests for the gated write-back helpers.

These helpers WRITE to outward-facing systems (Quip, Taskei), so the bar is:
- the correct remote tool name + argument dict is sent, and
- every failure mode (missing binary, timeout, transport error) fails soft
  with an ``"Error: ..."`` string and NEVER raises.

Like the read-tool tests, these patch ``_mcp_stdio.call_stdio_mcp`` and
``is_binary_available`` rather than touching a live service. No confirmation
prompt is tested here — the ``input()`` gate lives in the command handlers
(see test_write_back_commands.py); this module tests the transport wrappers.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from pm_agent_system.tools import write_back


def _patch_binary_present():
    return patch(
        "pm_agent_system.tools._mcp_stdio.is_binary_available",
        return_value=True,
    )


def _patch_call(side_effect):
    return patch(
        "pm_agent_system.tools.write_back._mcp_stdio.call_stdio_mcp",
        side_effect=side_effect,
    )


# ---------------------------------------------------------------------------
# publish_document
# ---------------------------------------------------------------------------
class TestPublishDocument:
    def test_quip_sends_correct_tool_and_args(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            captured["binary"] = binary
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return "Created: https://quip-amazon.com/AbC123/PRFAQ-Draft"

        with _patch_binary_present(), _patch_call(fake_call):
            url = write_back.publish_document(
                title="PRFAQ Draft",
                markdown="# Press Release\n\nBody.",
                target="quip",
                folder="FOLDER123,USER456",
            )

        assert captured["tool_name"] == "QuipEditor"
        assert captured["arguments"]["title"] == "PRFAQ Draft"
        assert captured["arguments"]["content"] == "# Press Release\n\nBody."
        assert captured["arguments"]["format"] == "markdown"
        # No documentId -> create a new doc.
        assert "documentId" not in captured["arguments"]
        # --folder maps to memberIds.
        assert captured["arguments"]["memberIds"] == "FOLDER123,USER456"
        # The URL is extracted from the free-text response.
        assert url == "https://quip-amazon.com/AbC123/PRFAQ-Draft"

    def test_folder_omitted_when_blank(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            captured["arguments"] = arguments
            return "https://quip-amazon.com/x/y"

        with _patch_binary_present(), _patch_call(fake_call):
            write_back.publish_document(title="T", markdown="body", target="quip")

        assert "memberIds" not in captured["arguments"]

    def test_unknown_target_returns_error_without_calling(self):
        called = {"n": 0}

        def fake_call(*a, **k):
            called["n"] += 1
            return "should not happen"

        with _patch_binary_present(), _patch_call(fake_call):
            result = write_back.publish_document(
                title="T", markdown="body", target="notarealstore"
            )

        assert write_back.is_write_error(result)
        assert "unknown publish target" in result.lower()
        assert called["n"] == 0

    def test_empty_markdown_refused_without_calling(self):
        called = {"n": 0}

        def fake_call(*a, **k):
            called["n"] += 1
            return "x"

        with _patch_binary_present(), _patch_call(fake_call):
            result = write_back.publish_document(title="T", markdown="   ", target="quip")

        assert write_back.is_write_error(result)
        assert called["n"] == 0

    def test_missing_binary_returns_error_string(self):
        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ):
            result = write_back.publish_document(title="T", markdown="body", target="quip")
        assert write_back.is_write_error(result)
        assert "not found on path" in result.lower()

    def test_transport_error_returns_error_string_not_raises(self):
        with _patch_binary_present(), _patch_call(RuntimeError("stdio boom")):
            result = write_back.publish_document(title="T", markdown="body", target="quip")
        assert isinstance(result, str)
        assert write_back.is_write_error(result)

    def test_timeout_returns_error_string(self):
        with _patch_binary_present(), _patch_call(asyncio.TimeoutError()):
            result = write_back.publish_document(title="T", markdown="body", target="quip")
        assert write_back.is_write_error(result)
        assert "timed out" in result.lower()

    def test_response_without_url_returns_raw_text(self):
        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            return "Document created successfully (id ABC)"

        with _patch_binary_present(), _patch_call(fake_call):
            result = write_back.publish_document(title="T", markdown="body", target="quip")
        # No URL in the response -> the raw confirmation is surfaced (not an error).
        assert not write_back.is_write_error(result)
        assert "Document created successfully" in result


# ---------------------------------------------------------------------------
# publish_document — SharePoint provider (separate binary, FedAuth)
# ---------------------------------------------------------------------------
class TestPublishSharePoint:
    def test_sends_sharepoint_binary_tool_and_args(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            captured["binary"] = binary
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return "Created: https://amazon.sharepoint.com/sites/pm/Doc.docx"

        with _patch_binary_present(), _patch_call(fake_call):
            url = write_back.publish_document(
                title="PRFAQ Draft",
                markdown="# Press Release\n\nBody.",
                target="sharepoint",
                folder="sites/pm/Shared Documents/PRFAQs",
            )

        # The SharePoint provider routes to its OWN binary, not builder-mcp.
        assert captured["binary"] == write_back._SHAREPOINT_BINARY
        assert captured["binary"] != write_back._BINARY_NAME
        assert captured["tool_name"] == write_back._SHAREPOINT_TOOL
        assert captured["arguments"]["title"] == "PRFAQ Draft"
        assert captured["arguments"]["content"] == "# Press Release\n\nBody."
        assert captured["arguments"]["format"] == "markdown"
        # --folder maps to the SharePoint destination path.
        assert captured["arguments"]["destination"] == "sites/pm/Shared Documents/PRFAQs"
        assert url == "https://amazon.sharepoint.com/sites/pm/Doc.docx"

    def test_folder_omitted_when_blank(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            captured["arguments"] = arguments
            return "https://amazon.sharepoint.com/x/y"

        with _patch_binary_present(), _patch_call(fake_call):
            write_back.publish_document(title="T", markdown="body", target="sharepoint")

        assert "destination" not in captured["arguments"]

    def test_missing_binary_fails_soft(self):
        # is_binary_available(False) for every binary -> descriptive Error, no raise.
        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ):
            result = write_back.publish_document(title="T", markdown="body", target="sharepoint")
        assert write_back.is_write_error(result)
        assert write_back._SHAREPOINT_BINARY in result
        assert "not found on path" in result.lower()

    def test_transport_error_fails_soft(self):
        with _patch_binary_present(), _patch_call(RuntimeError("fedauth boom")):
            result = write_back.publish_document(title="T", markdown="body", target="sharepoint")
        assert isinstance(result, str)
        assert write_back.is_write_error(result)

    def test_env_override_tool_name(self, monkeypatch):
        # The assumed SharePoint tool name is env-overridable; reload picks it up.
        import importlib

        monkeypatch.setenv("WRITE_BACK_SHAREPOINT_TOOL", "UploadFileToLibrary")
        reloaded = importlib.reload(write_back)
        try:
            captured: dict = {}

            def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
                captured["tool_name"] = tool_name
                return "https://amazon.sharepoint.com/x/y"

            with patch(
                "pm_agent_system.tools._mcp_stdio.is_binary_available", return_value=True
            ), patch(
                "pm_agent_system.tools.write_back._mcp_stdio.call_stdio_mcp",
                side_effect=fake_call,
            ):
                reloaded.publish_document(title="T", markdown="body", target="sharepoint")
            assert captured["tool_name"] == "UploadFileToLibrary"
        finally:
            monkeypatch.delenv("WRITE_BACK_SHAREPOINT_TOOL", raising=False)
            importlib.reload(write_back)


# ---------------------------------------------------------------------------
# publish_document — Pippin provider (python-pippin-mcp, project_id required)
# ---------------------------------------------------------------------------
class TestPublishPippin:
    def test_sends_pippin_binary_tool_and_confirmed_args(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            captured["binary"] = binary
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return "Created artifact: https://pippin.sara.amazon.dev/architect/proj-1?artifact=art-9"

        with _patch_binary_present(), _patch_call(fake_call):
            url = write_back.publish_document(
                title="Widget PRFAQ",
                markdown="# Widget\n\nBody.",
                target="pippin",
                folder="proj-1",
            )

        assert captured["binary"] == write_back._PIPPIN_BINARY
        assert captured["tool_name"] == write_back._PIPPIN_TOOL
        args = captured["arguments"]
        # CONFIRMED contract: project_id + name + content, and NO `format` key.
        assert args["project_id"] == "proj-1"
        assert args["name"] == "Widget PRFAQ"
        assert args["content"] == "# Widget\n\nBody."
        assert "format" not in args
        assert url.startswith("https://pippin.sara.amazon.dev/")

    # -- Live-confirmed response shape (2026-07-14) ------------------------
    # create_artifact returns JSON with NO url field; the addressable URL is
    # built from projectId + designId. Placeholder ids only (never real ones).
    _LIVE_CREATE_RESPONSE = (
        '{"design": {"content": "# x", "createdAt": 1, "createdBy": "someone", '
        '"designId": "DESIGN123", "docId": "DOC456", "kind": "PROSE", '
        '"name": "Scratch", "projectId": "PROJ789", "version": 1}}'
    )

    def test_json_response_yields_canonical_artifact_url(self):
        """The live create_artifact JSON (no URL field) must resolve to the
        canonical {base}/architect/{projectId}?artifact={designId} URL, not a
        dump of the raw JSON blob."""
        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            return self._LIVE_CREATE_RESPONSE

        with _patch_binary_present(), _patch_call(fake_call):
            url = write_back.publish_document(
                title="Scratch", markdown="# x", target="pippin", folder="PROJ789"
            )

        assert url == "https://pippin.sara.amazon.dev/architect/PROJ789?artifact=DESIGN123"
        assert not write_back.is_write_error(url)
        # The raw JSON must NOT leak through as the "URL".
        assert "{" not in url

    def test_project_id_from_arg_when_absent_in_response(self):
        """If the response omits projectId, fall back to the --pippin-project
        arg that was threaded in as `folder`."""
        resp = '{"design": {"designId": "DESIGN123", "kind": "PROSE"}}'

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            return resp

        with _patch_binary_present(), _patch_call(fake_call):
            url = write_back.publish_document(
                title="Scratch", markdown="# x", target="pippin", folder="PROJ789"
            )
        assert url == "https://pippin.sara.amazon.dev/architect/PROJ789?artifact=DESIGN123"

    def test_url_bearing_response_still_works(self):
        """A future/alternate response that already carries a URL must pass
        through unchanged (no regression)."""
        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            return "Created: https://pippin.sara.amazon.dev/x/y"

        with _patch_binary_present(), _patch_call(fake_call):
            url = write_back.publish_document(
                title="S", markdown="# x", target="pippin", folder="PROJ789"
            )
        assert url == "https://pippin.sara.amazon.dev/x/y"

    def test_non_json_response_does_not_crash(self):
        """A non-JSON body degrades to the generic extractor, never raises."""
        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            return "some unexpected plain text"

        with _patch_binary_present(), _patch_call(fake_call):
            url = write_back.publish_document(
                title="S", markdown="# x", target="pippin", folder="PROJ789"
            )
        assert isinstance(url, str)
        assert "some unexpected plain text" in url

    def test_base_url_env_overridable(self, monkeypatch):
        import importlib

        monkeypatch.setenv("PIPPIN_BASE_URL", "https://pippin.example.internal/")
        reloaded = importlib.reload(write_back)
        try:
            def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
                return self._LIVE_CREATE_RESPONSE

            with patch(
                "pm_agent_system.tools._mcp_stdio.is_binary_available", return_value=True
            ), patch(
                "pm_agent_system.tools.write_back._mcp_stdio.call_stdio_mcp", side_effect=fake_call
            ):
                url = reloaded.publish_document(
                    title="S", markdown="# x", target="pippin", folder="PROJ789"
                )
            assert url == "https://pippin.example.internal/architect/PROJ789?artifact=DESIGN123"
        finally:
            monkeypatch.delenv("PIPPIN_BASE_URL", raising=False)
            importlib.reload(write_back)

    def test_missing_project_refused_without_calling(self):
        called = {"n": 0}

        def fake_call(*a, **k):
            called["n"] += 1
            return "should not happen"

        with _patch_binary_present(), _patch_call(fake_call):
            result = write_back.publish_document(
                title="T", markdown="body", target="pippin", folder=""
            )

        assert write_back.is_write_error(result)
        assert "project" in result.lower()
        assert called["n"] == 0

    def test_missing_binary_fails_soft(self):
        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ):
            result = write_back.publish_document(
                title="T", markdown="body", target="pippin", folder="proj-1"
            )
        assert write_back.is_write_error(result)
        assert write_back._PIPPIN_BINARY in result


# ---------------------------------------------------------------------------
# create_taskei_task / create_taskei_epic
# ---------------------------------------------------------------------------
class TestCreateTaskeiTask:
    def test_sends_correct_tool_and_required_args(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            captured["binary"] = binary
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return "Task created: https://taskei.amazon.dev/tasks/T-999"

        with _patch_binary_present(), _patch_call(fake_call):
            url = write_back.create_taskei_task(
                room="room-uuid-123",
                name="FR-001: The system shall foo",
                description="Rationale...\n\nAcceptance criteria:\n- given/when/then",
                priority="High",
                parent_task="EPIC-1",
            )

        # Regression: Taskei stays on the builder-mcp binary after the
        # per-provider-binary refactor (it does not pass an explicit binary).
        assert captured["binary"] == write_back._BINARY_NAME
        assert captured["tool_name"] == "TaskeiCreateTask"
        args = captured["arguments"]
        assert args["roomId"] == "room-uuid-123"
        assert args["name"] == "FR-001: The system shall foo"
        assert args["description"].startswith("Rationale")
        assert args["priority"] == "High"
        assert args["parentTask"] == "EPIC-1"
        assert args["type"] == "TASK"
        assert url == "https://taskei.amazon.dev/tasks/T-999"

    def test_missing_room_refused_without_calling(self):
        called = {"n": 0}

        def fake_call(*a, **k):
            called["n"] += 1
            return "x"

        with _patch_binary_present(), _patch_call(fake_call):
            result = write_back.create_taskei_task(room="", name="T", description="d")

        assert write_back.is_write_error(result)
        assert "room id is required" in result.lower()
        assert called["n"] == 0

    def test_bad_priority_omitted(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            captured["arguments"] = arguments
            return "https://taskei.amazon.dev/tasks/T-1"

        with _patch_binary_present(), _patch_call(fake_call):
            write_back.create_taskei_task(
                room="r", name="T", description="d", priority="Urgent"
            )

        assert "priority" not in captured["arguments"]

    def test_epic_uses_epic_type(self):
        captured: dict = {}

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            captured["arguments"] = arguments
            return "https://taskei.amazon.dev/tasks/E-1"

        with _patch_binary_present(), _patch_call(fake_call):
            write_back.create_taskei_epic(room="r", name="BRD Epic", description="d")

        assert captured["arguments"]["type"] == "EPIC"

    def test_missing_binary_returns_error(self):
        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ):
            result = write_back.create_taskei_task(room="r", name="T", description="d")
        assert write_back.is_write_error(result)

    def test_transport_error_fails_soft(self):
        with _patch_binary_present(), _patch_call(RuntimeError("boom")):
            result = write_back.create_taskei_task(room="r", name="T", description="d")
        assert isinstance(result, str)
        assert write_back.is_write_error(result)


# ---------------------------------------------------------------------------
# Call logging
# ---------------------------------------------------------------------------
class TestCallLogging:
    def test_logs_invocation_and_response(self, monkeypatch, tmp_path: Path):
        log_file = tmp_path / "write_back_calls.log"
        monkeypatch.setattr(write_back, "_CALL_LOG_PATH", log_file)

        def fake_call(binary, tool_name, arguments, args=(), timeout=120.0):
            return "https://taskei.amazon.dev/tasks/T-1"

        with _patch_binary_present(), _patch_call(fake_call):
            write_back.create_taskei_task(room="r", name="T", description="d")

        assert log_file.exists()
        events = [json.loads(line) for line in log_file.read_text().strip().splitlines()]
        types = [e["event"] for e in events]
        assert types[0] == "invocation"
        assert "response" in types

    def test_missing_binary_logged(self, monkeypatch, tmp_path: Path):
        log_file = tmp_path / "write_back_calls.log"
        monkeypatch.setattr(write_back, "_CALL_LOG_PATH", log_file)

        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ):
            write_back.publish_document(title="T", markdown="body", target="quip")

        events = [json.loads(line) for line in log_file.read_text().strip().splitlines()]
        types = [e["event"] for e in events]
        assert "binary_missing" in types


# ---------------------------------------------------------------------------
# Env-overridable remote tool names
# ---------------------------------------------------------------------------
class TestEnvOverride:
    def test_registry_exposes_quip_sharepoint_pippin(self):
        assert set(write_back.PUBLISH_TARGETS) == {"quip", "sharepoint", "pippin"}
        # Every provider entry is (binary, remote_tool, arg_builder).
        for target, entry in write_back.PUBLISH_PROVIDERS.items():
            assert len(entry) == 3, f"{target} entry should be a 3-tuple, got {entry!r}"
            binary, remote_tool, arg_builder = entry
            assert isinstance(binary, str) and binary
            assert isinstance(remote_tool, str) and remote_tool
            assert callable(arg_builder)

    def test_quip_provider_uses_builder_mcp_binary(self):
        # Regression: the Quip provider must keep the builder-mcp binary after
        # the per-provider-binary refactor (its behavior is unchanged).
        binary, remote_tool, _ = write_back.PUBLISH_PROVIDERS["quip"]
        assert binary == write_back._BINARY_NAME
        assert remote_tool == write_back._QUIP_TOOL

    def test_url_extraction_prefers_first_http_url(self):
        raw = "See https://quip-amazon.com/AAA/Doc and https://other.example/x"
        assert write_back._extract_url(raw) == "https://quip-amazon.com/AAA/Doc"


class TestExtractTaskRef:
    """extract_task_ref derives a parentTask *identifier*, not a display URL.

    A created EPIC returns a URL/confirmation for display; that value is not a
    valid parentTask id. extract_task_ref recovers the id so child tasks nest
    correctly.
    """

    def test_url_yields_last_path_segment(self):
        assert write_back.extract_task_ref("Created: https://taskei.amazon.dev/tasks/EPIC-1") == "EPIC-1"

    def test_url_with_query_and_fragment_stripped(self):
        assert write_back.extract_task_ref("https://taskei.amazon.dev/tasks/T-42?tab=x#c") == "T-42"

    def test_bare_id_token_recovered(self):
        assert write_back.extract_task_ref("Created task EPIC-123 successfully") == "EPIC-123"

    def test_uuid_recovered(self):
        u = "550e8400-e29b-41d4-a716-446655440000"
        assert write_back.extract_task_ref(f"new task {u} done") == u

    def test_no_id_falls_back_to_stripped_text(self):
        assert write_back.extract_task_ref("  done  ") == "done"

    def test_empty_stays_empty(self):
        assert write_back.extract_task_ref("") == ""
