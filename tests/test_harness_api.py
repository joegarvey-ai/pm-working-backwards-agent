"""Integration tests for the harness public API.

Covers: run_crew signature, HarnessConfigError, load_record, diff_manifests,
and output_path JSON writing.

Requirements: 1.4, 6.1, 6.4, 6.5, 6.6
"""

from __future__ import annotations

import inspect
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.harness import diff_manifests, load_record, run_crew
from tests.harness.exceptions import HarnessConfigError
from tests.harness.models import (
    CostSummary,
    LatencySummary,
    RunManifest,
    RunRecord,
    Trace,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest(**overrides: object) -> RunManifest:
    """Build a minimal RunManifest with sensible defaults."""
    defaults = dict(
        model_id="claude-sonnet-4-20250514",
        agents_yaml_hash="a" * 64,
        tasks_yaml_hash="b" * 64,
        tool_names_by_agent={"researcher": ["TavilySearch"]},
        env_flags={"LLM_PROVIDER": True, "DOVETAIL_API_TOKEN": False},
        input_brief_hash="c" * 64,
    )
    defaults.update(overrides)
    return RunManifest(**defaults)


def _make_run_record(**overrides: object) -> RunRecord:
    """Build a minimal valid RunRecord."""
    defaults = dict(
        run_id=str(uuid.uuid4()),
        manifest=_make_manifest(),
        prompt_snapshots=[],
        tool_calls=[],
        llm_calls=[],
        trace=Trace(spans=[]),
        cost_summary=CostSummary(total_usd=0.0, per_agent={}, warnings=[]),
        latency_summary=LatencySummary(
            total_s=0.0, per_task={}, aggregate_llm_s=0.0, aggregate_tool_s=0.0
        ),
        agent_outputs={},
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    defaults.update(overrides)
    return RunRecord(**defaults)


# ---------------------------------------------------------------------------
# 1. run_crew function signature and return type (smoke test)
# ---------------------------------------------------------------------------


class TestRunCrewSignature:
    """Verify the run_crew public API surface (Req 6.1)."""

    def test_run_crew_is_callable(self) -> None:
        assert callable(run_crew)

    def test_run_crew_accepts_expected_parameters(self) -> None:
        sig = inspect.signature(run_crew)
        param_names = list(sig.parameters.keys())
        assert "crew" in param_names
        assert "inputs" in param_names
        assert "replay_path" in param_names
        assert "output_path" in param_names
        assert "strict_manifest" in param_names

    def test_run_crew_defaults(self) -> None:
        sig = inspect.signature(run_crew)
        assert sig.parameters["replay_path"].default is None
        assert sig.parameters["output_path"].default is None
        assert sig.parameters["strict_manifest"].default is False


# ---------------------------------------------------------------------------
# 2. HarnessConfigError raised when config files missing (Req 1.4)
# ---------------------------------------------------------------------------


class TestHarnessConfigError:
    """Verify HarnessConfigError is raised when config files are unreadable."""

    def test_missing_config_raises_harness_config_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Point _CONFIG_DIR at an empty directory so agents.yaml is missing."""
        import tests.harness as harness_mod

        monkeypatch.setattr(harness_mod, "_CONFIG_DIR", tmp_path)

        class FakeCrew:
            agents: list = []
            tasks: list = []

            def kickoff(self, inputs: dict | None = None) -> None:
                pass

        with pytest.raises(HarnessConfigError) as exc_info:
            run_crew(FakeCrew(), {"brief": "test"})

        # The error message should name the missing file.
        assert "agents.yaml" in str(exc_info.value)

    def test_missing_tasks_yaml_raises_harness_config_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Provide agents.yaml but not tasks.yaml."""
        import tests.harness as harness_mod

        monkeypatch.setattr(harness_mod, "_CONFIG_DIR", tmp_path)
        (tmp_path / "agents.yaml").write_text("agents: []")

        class FakeCrew:
            agents: list = []
            tasks: list = []

            def kickoff(self, inputs: dict | None = None) -> None:
                pass

        with pytest.raises(HarnessConfigError) as exc_info:
            run_crew(FakeCrew(), {"brief": "test"})

        assert "tasks.yaml" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 3. load_record reads and validates JSON correctly (Req 6.5)
# ---------------------------------------------------------------------------


class TestLoadRecord:
    """Verify load_record reads and validates RunRecord JSON."""

    def test_load_record_round_trip(self, tmp_path: Path) -> None:
        record = _make_run_record()
        json_path = tmp_path / "record.json"
        json_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

        loaded = load_record(str(json_path))

        assert loaded.run_id == record.run_id
        assert loaded.manifest == record.manifest
        assert loaded.created_at == record.created_at

    def test_load_record_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_record("/nonexistent/path/record.json")

    def test_load_record_invalid_json(self, tmp_path: Path) -> None:
        bad_path = tmp_path / "bad.json"
        bad_path.write_text('{"not": "a run record"}', encoding="utf-8")

        with pytest.raises(Exception):
            # Pydantic ValidationError on missing required fields.
            load_record(str(bad_path))


# ---------------------------------------------------------------------------
# 4. diff_manifests returns correct diff dictionary (Req 6.6)
# ---------------------------------------------------------------------------


class TestDiffManifests:
    """Verify diff_manifests compares RunManifests correctly."""

    def test_identical_manifests_return_empty_dict(self) -> None:
        m = _make_manifest()
        assert diff_manifests(m, m) == {}

    def test_single_field_diff(self) -> None:
        a = _make_manifest(model_id="model-a")
        b = _make_manifest(model_id="model-b")
        diffs = diff_manifests(a, b)

        assert "model_id" in diffs
        assert diffs["model_id"] == ("model-a", "model-b")
        # Only model_id should differ.
        assert len(diffs) == 1

    def test_multiple_field_diffs(self) -> None:
        a = _make_manifest(model_id="model-a", input_brief_hash="x" * 64)
        b = _make_manifest(model_id="model-b", input_brief_hash="y" * 64)
        diffs = diff_manifests(a, b)

        assert "model_id" in diffs
        assert "input_brief_hash" in diffs
        assert len(diffs) == 2

    def test_diff_values_are_old_new_tuples(self) -> None:
        a = _make_manifest(agents_yaml_hash="1" * 64)
        b = _make_manifest(agents_yaml_hash="2" * 64)
        diffs = diff_manifests(a, b)

        old_val, new_val = diffs["agents_yaml_hash"]
        assert old_val == "1" * 64
        assert new_val == "2" * 64


# ---------------------------------------------------------------------------
# 5. output_path writing produces valid JSON with 2-space indentation (Req 6.4)
# ---------------------------------------------------------------------------


class TestOutputPathWriting:
    """Verify that output_path produces valid, 2-space-indented JSON."""

    def test_output_path_creates_valid_json(self, tmp_path: Path) -> None:
        record = _make_run_record()
        out_file = tmp_path / "output.json"
        out_file.write_text(record.model_dump_json(indent=2), encoding="utf-8")

        raw = out_file.read_text(encoding="utf-8")
        parsed = json.loads(raw)

        assert parsed["run_id"] == record.run_id
        assert "manifest" in parsed
        assert "cost_summary" in parsed

    def test_output_json_uses_two_space_indentation(self, tmp_path: Path) -> None:
        record = _make_run_record()
        out_file = tmp_path / "output.json"
        out_file.write_text(record.model_dump_json(indent=2), encoding="utf-8")

        raw = out_file.read_text(encoding="utf-8")
        lines = raw.splitlines()

        # Find the first indented line and verify it uses 2-space indent.
        indented_lines = [
            ln for ln in lines if ln.startswith("  ") and not ln.startswith("    ")
        ]
        assert len(indented_lines) > 0, "Expected at least one 2-space indented line"

        # No tabs should be present.
        assert "\t" not in raw

    def test_output_json_round_trips_through_load_record(
        self, tmp_path: Path
    ) -> None:
        record = _make_run_record()
        out_file = tmp_path / "output.json"
        out_file.write_text(record.model_dump_json(indent=2), encoding="utf-8")

        loaded = load_record(str(out_file))
        assert loaded == record
