"""Tests for the gated write-back CLI commands.

The single most important property this suite proves: **nothing writes to an
external system without an explicit per-invocation confirmation.** For each
write command, a "n" (or empty / EOF) confirmation must produce ZERO write
calls, and a "y" must produce exactly the expected writes.

Handlers are invoked directly with an argparse.Namespace (matching the
existing command tests), with the underlying write helpers patched so no MCP
binary or live service is touched.
"""

from __future__ import annotations

import argparse
from unittest.mock import patch

import pytest

from pm_agent_system.models.brd_output import (
    BRDOutput,
    FunctionalRequirement,
    NonFunctionalRequirement,
    Risk,
    SuccessMetric,
    UserStory,
)
from pm_agent_system.models.prfaq_output import VersionEntry
from pm_agent_system.utils import render_brd_to_markdown


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def artifact_file(tmp_path):
    p = tmp_path / "prfaq_widget_v1.0.md"
    p.write_text("# Widget PRFAQ\n\nPress release body.\n\n## FAQ\n\nQ1...\n", encoding="utf-8")
    return p


def _brd_markdown() -> str:
    frs = [
        FunctionalRequirement(
            id=f"FR-00{i}",
            description=f"The system shall do thing {i}",
            rationale="because",
            acceptance_criteria=["Given X when Y then Z"],
            related_user_stories=["US-001"],
        )
        for i in (1, 2, 3)
    ]
    brd = BRDOutput(
        executive_summary="Exec.",
        problem_statement="Problem.",
        proposed_solution_overview="Solution.",
        user_stories=[
            UserStory(id="US-001", persona="PM", action="do", outcome="win", priority="P0"),
            UserStory(id="US-002", persona="dev", action="build", outcome="ship", priority="P1"),
            UserStory(id="US-003", persona="ops", action="run", outcome="up", priority="P2"),
        ],
        functional_requirements=frs,
        non_functional_requirements=[
            NonFunctionalRequirement(id="NFR-001", category="performance", description="fast", acceptance_criteria=["p99<100ms"]),
            NonFunctionalRequirement(id="NFR-002", category="security", description="safe", acceptance_criteria=["encrypted"]),
        ],
        risks=[
            Risk(description="r1", likelihood="low", impact="minor", mitigation="watch"),
            Risk(description="r2", likelihood="high", impact="major", mitigation="plan"),
        ],
        success_metrics=[SuccessMetric(metric="adoption", target_value="50%", measurement_method="CW", timeline="Q3")],
        version_history=[VersionEntry(version="1.0", date="2026-07-13", author="agent", changes="init")],
    )
    return render_brd_to_markdown(brd)


@pytest.fixture
def brd_file(tmp_path):
    p = tmp_path / "brd_widget_v1.0.md"
    p.write_text(_brd_markdown(), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# publish-doc gate
# ---------------------------------------------------------------------------
class TestPublishDocGate:
    def _ns(self, artifact_file, **over):
        base = dict(
            command="publish-doc",
            artifact_path=str(artifact_file),
            target="quip",
            folder="",
            pippin_project="",
        )
        base.update(over)
        return argparse.Namespace(**base)

    def test_no_confirmation_writes_nothing(self, artifact_file, capsys):
        from pm_agent_system.main import cmd_publish_doc

        with patch("pm_agent_system.tools.write_back.publish_document") as mock_pub, \
             patch("builtins.input", return_value="n"):
            cmd_publish_doc(self._ns(artifact_file))

        mock_pub.assert_not_called()
        assert "Aborted" in capsys.readouterr().out

    def test_empty_confirmation_defaults_to_no(self, artifact_file):
        from pm_agent_system.main import cmd_publish_doc

        with patch("pm_agent_system.tools.write_back.publish_document") as mock_pub, \
             patch("builtins.input", return_value=""):
            cmd_publish_doc(self._ns(artifact_file))

        mock_pub.assert_not_called()

    def test_eof_defaults_to_no(self, artifact_file):
        from pm_agent_system.main import cmd_publish_doc

        with patch("pm_agent_system.tools.write_back.publish_document") as mock_pub, \
             patch("builtins.input", side_effect=EOFError):
            cmd_publish_doc(self._ns(artifact_file))

        mock_pub.assert_not_called()

    def test_yes_writes_exactly_once(self, artifact_file, capsys):
        from pm_agent_system.main import cmd_publish_doc

        with patch(
            "pm_agent_system.tools.write_back.publish_document",
            return_value="https://quip-amazon.com/AAA/Widget",
        ) as mock_pub, patch("builtins.input", return_value="y"):
            cmd_publish_doc(self._ns(artifact_file))

        assert mock_pub.call_count == 1
        _, kwargs = mock_pub.call_args
        assert kwargs["target"] == "quip"
        # Title derived from the H1.
        assert kwargs["title"] == "Widget PRFAQ"
        out = capsys.readouterr().out
        assert "https://quip-amazon.com/AAA/Widget" in out

    def test_soft_failure_is_reported_not_raised(self, artifact_file, capsys):
        from pm_agent_system.main import cmd_publish_doc

        with patch(
            "pm_agent_system.tools.write_back.publish_document",
            return_value="Error: builder-mcp binary not found on PATH; cannot publish.",
        ), patch("builtins.input", return_value="y"):
            cmd_publish_doc(self._ns(artifact_file))

        assert "Error" in capsys.readouterr().out

    def test_unknown_target_exits(self, artifact_file):
        from pm_agent_system.main import cmd_publish_doc

        ns = self._ns(artifact_file, target="notarealstore")
        with patch("pm_agent_system.tools.write_back.publish_document") as mock_pub, \
             pytest.raises(SystemExit):
            cmd_publish_doc(ns)
        mock_pub.assert_not_called()


# ---------------------------------------------------------------------------
# publish-doc gate — SharePoint target (the new provider's safety property)
# ---------------------------------------------------------------------------
class TestPublishDocSharePointGate:
    """The confirmation gate must hold for --target sharepoint exactly as it
    does for quip: "n"/""/EOF write nothing, "y" writes exactly once."""

    def _ns(self, artifact_file):
        return argparse.Namespace(
            command="publish-doc",
            artifact_path=str(artifact_file),
            target="sharepoint",
            folder="sites/pm/Shared Documents",
            pippin_project="",
        )

    def test_no_confirmation_writes_nothing(self, artifact_file, capsys):
        from pm_agent_system.main import cmd_publish_doc

        with patch("pm_agent_system.tools.write_back.publish_document") as mock_pub, \
             patch("builtins.input", return_value="n"):
            cmd_publish_doc(self._ns(artifact_file))

        mock_pub.assert_not_called()
        assert "Aborted" in capsys.readouterr().out

    def test_empty_confirmation_defaults_to_no(self, artifact_file):
        from pm_agent_system.main import cmd_publish_doc

        with patch("pm_agent_system.tools.write_back.publish_document") as mock_pub, \
             patch("builtins.input", return_value=""):
            cmd_publish_doc(self._ns(artifact_file))

        mock_pub.assert_not_called()

    def test_eof_defaults_to_no(self, artifact_file):
        from pm_agent_system.main import cmd_publish_doc

        with patch("pm_agent_system.tools.write_back.publish_document") as mock_pub, \
             patch("builtins.input", side_effect=EOFError):
            cmd_publish_doc(self._ns(artifact_file))

        mock_pub.assert_not_called()

    def test_yes_writes_exactly_once_to_sharepoint(self, artifact_file, capsys):
        from pm_agent_system.main import cmd_publish_doc

        with patch(
            "pm_agent_system.tools.write_back.publish_document",
            return_value="https://amazon.sharepoint.com/sites/pm/Widget.docx",
        ) as mock_pub, patch("builtins.input", return_value="y"):
            cmd_publish_doc(self._ns(artifact_file))

        assert mock_pub.call_count == 1
        _, kwargs = mock_pub.call_args
        assert kwargs["target"] == "sharepoint"
        # --folder threads through as the destination.
        assert kwargs["folder"] == "sites/pm/Shared Documents"
        assert "https://amazon.sharepoint.com/sites/pm/Widget.docx" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# publish-doc gate — Pippin target (requires a project id; gate still holds)
# ---------------------------------------------------------------------------
class TestPublishDocPippinGate:
    def _ns(self, artifact_file, **over):
        base = dict(
            command="publish-doc",
            artifact_path=str(artifact_file),
            target="pippin",
            folder="",
            pippin_project="proj-42",
        )
        base.update(over)
        return argparse.Namespace(**base)

    def test_missing_project_exits_without_prompting(self, artifact_file):
        from pm_agent_system.main import cmd_publish_doc

        ns = self._ns(artifact_file, pippin_project="")
        with patch("pm_agent_system.tools.write_back.publish_document") as mock_pub, \
             patch("builtins.input") as mock_input, \
             patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("PIPPIN_PROJECT_ID", None)
            with pytest.raises(SystemExit):
                cmd_publish_doc(ns)
        mock_pub.assert_not_called()
        mock_input.assert_not_called()

    def test_no_confirmation_writes_nothing(self, artifact_file, capsys):
        from pm_agent_system.main import cmd_publish_doc

        with patch("pm_agent_system.tools.write_back.publish_document") as mock_pub, \
             patch("builtins.input", return_value="n"):
            cmd_publish_doc(self._ns(artifact_file))

        mock_pub.assert_not_called()
        assert "Aborted" in capsys.readouterr().out

    def test_yes_writes_once_with_project_threaded(self, artifact_file, capsys):
        from pm_agent_system.main import cmd_publish_doc

        with patch(
            "pm_agent_system.tools.write_back.publish_document",
            return_value="https://pippin.sara.amazon.dev/architect/proj-42?artifact=art-1",
        ) as mock_pub, patch("builtins.input", return_value="y"):
            cmd_publish_doc(self._ns(artifact_file))

        assert mock_pub.call_count == 1
        _, kwargs = mock_pub.call_args
        assert kwargs["target"] == "pippin"
        # The project id is threaded through the folder slot.
        assert kwargs["folder"] == "proj-42"

    def test_project_from_env_when_flag_absent(self, artifact_file, monkeypatch):
        from pm_agent_system.main import cmd_publish_doc

        monkeypatch.setenv("PIPPIN_PROJECT_ID", "env-proj-99")
        with patch(
            "pm_agent_system.tools.write_back.publish_document",
            return_value="https://pippin.sara.amazon.dev/architect/env-proj-99?artifact=a",
        ) as mock_pub, patch("builtins.input", return_value="y"):
            cmd_publish_doc(self._ns(artifact_file, pippin_project=""))

        assert mock_pub.call_count == 1
        _, kwargs = mock_pub.call_args
        assert kwargs["folder"] == "env-proj-99"


# ---------------------------------------------------------------------------
# seed-taskei gate + dry-run
# ---------------------------------------------------------------------------
class TestSeedTaskei:
    def _ns(self, brd_file, **over):
        base = dict(
            command="seed-taskei",
            brd_path=str(brd_file),
            taskei_room="room-uuid-1",
            parent_task="",
            dry_run=False,
        )
        base.update(over)
        return argparse.Namespace(**base)

    def test_dry_run_writes_nothing(self, brd_file, capsys):
        from pm_agent_system.main import cmd_seed_taskei

        with patch("pm_agent_system.tools.write_back.create_taskei_task") as mock_task, \
             patch("pm_agent_system.tools.write_back.create_taskei_epic") as mock_epic:
            cmd_seed_taskei(self._ns(brd_file, dry_run=True))

        mock_task.assert_not_called()
        mock_epic.assert_not_called()
        out = capsys.readouterr().out
        assert "dry-run" in out.lower()
        assert "FR-001" in out and "FR-002" in out and "FR-003" in out

    def test_no_confirmation_writes_nothing(self, brd_file, capsys):
        from pm_agent_system.main import cmd_seed_taskei

        with patch("pm_agent_system.tools.write_back.create_taskei_task") as mock_task, \
             patch("pm_agent_system.tools.write_back.create_taskei_epic") as mock_epic, \
             patch("builtins.input", return_value="n"):
            cmd_seed_taskei(self._ns(brd_file))

        mock_task.assert_not_called()
        mock_epic.assert_not_called()
        assert "Aborted" in capsys.readouterr().out

    def test_yes_creates_epic_then_one_task_per_fr(self, brd_file, capsys):
        from pm_agent_system.main import cmd_seed_taskei

        with patch(
            "pm_agent_system.tools.write_back.create_taskei_epic",
            return_value="https://taskei.amazon.dev/tasks/EPIC-1",
        ) as mock_epic, patch(
            "pm_agent_system.tools.write_back.create_taskei_task",
            side_effect=[f"https://taskei.amazon.dev/tasks/T-{i}" for i in range(1, 4)],
        ) as mock_task, patch("builtins.input", return_value="y"):
            cmd_seed_taskei(self._ns(brd_file))

        assert mock_epic.call_count == 1
        assert mock_task.call_count == 3
        # Every child nests under the EPIC's *identifier* (extracted from the
        # returned URL), not the full display URL.
        for call in mock_task.call_args_list:
            assert call.kwargs["parent_task"] == "EPIC-1"
        out = capsys.readouterr().out
        assert "Created 3/3" in out
        # The full EPIC URL is still shown to the user.
        assert "https://taskei.amazon.dev/tasks/EPIC-1" in out

    def test_provided_parent_skips_epic(self, brd_file):
        from pm_agent_system.main import cmd_seed_taskei

        with patch("pm_agent_system.tools.write_back.create_taskei_epic") as mock_epic, \
             patch(
                 "pm_agent_system.tools.write_back.create_taskei_task",
                 side_effect=[f"url-{i}" for i in range(3)],
             ) as mock_task, patch("builtins.input", return_value="y"):
            cmd_seed_taskei(self._ns(brd_file, parent_task="EXISTING-1"))

        mock_epic.assert_not_called()
        assert mock_task.call_count == 3
        for call in mock_task.call_args_list:
            assert call.kwargs["parent_task"] == "EXISTING-1"

    def test_epic_failure_aborts_before_children(self, brd_file, capsys):
        from pm_agent_system.main import cmd_seed_taskei

        with patch(
            "pm_agent_system.tools.write_back.create_taskei_epic",
            return_value="Error: could not create Taskei task: boom",
        ), patch("pm_agent_system.tools.write_back.create_taskei_task") as mock_task, \
           patch("builtins.input", return_value="y"):
            cmd_seed_taskei(self._ns(brd_file))

        mock_task.assert_not_called()
        assert "Aborting" in capsys.readouterr().out

    def test_partial_failure_reported(self, brd_file, capsys):
        from pm_agent_system.main import cmd_seed_taskei

        with patch(
            "pm_agent_system.tools.write_back.create_taskei_epic",
            return_value="EPIC-1",
        ), patch(
            "pm_agent_system.tools.write_back.create_taskei_task",
            side_effect=["url-1", "Error: timeout", "url-3"],
        ), patch("builtins.input", return_value="y"):
            cmd_seed_taskei(self._ns(brd_file))

        out = capsys.readouterr().out
        assert "Created 2/3" in out
        assert "1 task(s) failed" in out

    def test_missing_room_exits_without_reading(self, brd_file):
        from pm_agent_system.main import cmd_seed_taskei

        ns = self._ns(brd_file, taskei_room="")
        with patch.dict("os.environ", {}, clear=False) as _env:
            import os
            os.environ.pop("TASKEI_ROOM_ID", None)
            with patch("pm_agent_system.tools.write_back.create_taskei_task") as mock_task, \
                 pytest.raises(SystemExit):
                cmd_seed_taskei(ns)
            mock_task.assert_not_called()

    def test_room_from_env_when_flag_absent(self, brd_file, monkeypatch):
        from pm_agent_system.main import cmd_seed_taskei

        monkeypatch.setenv("TASKEI_ROOM_ID", "env-room-42")
        captured = {}

        def fake_epic(room, name, body, **kw):
            captured["room"] = room
            return "EPIC-1"

        with patch("pm_agent_system.tools.write_back.create_taskei_epic", side_effect=fake_epic), \
             patch("pm_agent_system.tools.write_back.create_taskei_task", return_value="url"), \
             patch("builtins.input", return_value="y"):
            cmd_seed_taskei(self._ns(brd_file, taskei_room=""))

        assert captured["room"] == "env-room-42"
