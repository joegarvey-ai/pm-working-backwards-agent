"""Tests for the checkpoint module and --resume / --fresh behavior."""

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from pm_agent_system.checkpoint import (
    completed_stages,
    compute_input_hash,
    delete_checkpoint,
    load_checkpoint,
    new_checkpoint,
    record_artifact,
    save_checkpoint,
)
from pm_agent_system.models import (
    BRDOutput,
    CodingPromptOutput,
    PRFAQOutput,
    ResearchOutput,
)
from pm_agent_system.models.brd_output import (
    FunctionalRequirement,
    NonFunctionalRequirement,
    Risk,
    SuccessMetric,
    UserStory,
)
from pm_agent_system.models.coding_prompt_output import FeatureSpec, UserFlow
from pm_agent_system.models.prfaq_output import FAQ, VersionEntry
from pm_agent_system.models.research_output import MarketSizing


# ---------- Fixtures ----------


def _minimal_research():
    return ResearchOutput(
        context="Test context.",
        executive_summary="Test summary.",
        market_sizing=MarketSizing(summary="$1B", data_points=["p"], sources=["s"]),
        strategic_implications="Test implications.",
    )


def _minimal_prfaq():
    return PRFAQOutput(
        press_release="Test press release.",
        external_faqs=[FAQ(question=f"Q{i}?", answer=f"A{i}", audience="external") for i in range(3)],
        internal_faqs=[FAQ(question=f"IQ{i}?", answer=f"IA{i}", audience="internal") for i in range(5)],
        customer_experience_narrative="Test narrative.",
        version_history=[VersionEntry(version="1.0", date="2026-04-15", author="Agent 2", changes="Init")],
    )


def _minimal_brd():
    return BRDOutput(
        executive_summary="Exec.",
        problem_statement="Problem.",
        proposed_solution_overview="Solution.",
        user_stories=[
            UserStory(id=f"US-00{i}", persona="PM", action="X", outcome="Y", priority="P0")
            for i in range(1, 4)
        ],
        functional_requirements=[
            FunctionalRequirement(
                id=f"FR-00{i}", description="Shall.", rationale="Because.",
                acceptance_criteria=["AC"], related_user_stories=[f"US-00{i}"],
            )
            for i in range(1, 4)
        ],
        non_functional_requirements=[
            NonFunctionalRequirement(id="NFR-001", category="perf", description="<200ms", acceptance_criteria=["<200ms"]),
            NonFunctionalRequirement(id="NFR-002", category="sec", description="TLS", acceptance_criteria=["TLS"]),
        ],
        risks=[
            Risk(description="R1", likelihood="med", impact="high", mitigation="M"),
            Risk(description="R2", likelihood="low", impact="med", mitigation="M"),
        ],
        success_metrics=[SuccessMetric(metric="M", target_value="V", measurement_method="CM", timeline="Q3")],
        version_history=[VersionEntry(version="1.0", date="2026-04-15", author="Agent 4", changes="Init")],
    )


def _minimal_spec():
    return CodingPromptOutput(
        build_summary="Build X.", target_tool="kiro", formatted_spec="# Spec",
        user_flows=[UserFlow(name="Flow", steps=["S1"], related_requirements=["FR-001"])],
        feature_specs=[FeatureSpec(name="F1", description="D", acceptance_criteria=["AC"], priority="P0")],
    )


def _mock_crew_result(models):
    """Build a mock CrewOutput from a list of Pydantic models."""
    tasks = []
    for m in models:
        t = MagicMock()
        t.pydantic = m
        tasks.append(t)
    result = MagicMock()
    result.tasks_output = tasks
    result.pydantic = models[-1] if models else None
    return result


@pytest.fixture
def output_dir(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    with patch.dict("os.environ", {"OUTPUT_DIR": str(out)}):
        yield out


@pytest.fixture
def example_input(tmp_path):
    data = {
        "feature_summary": "Test Feature",
        "goals": "Test goals",
        "timing": "Q3 2026",
        "user_summary": "Test users",
    }
    path = tmp_path / "input.yaml"
    path.write_text(yaml.dump(data))
    return str(path)


# ---------- Unit tests: checkpoint module ----------


def test_checkpoint_write_and_load(tmp_path):
    ckpt = new_checkpoint("abc123", "claude-sonnet-4-20250514")
    save_checkpoint(tmp_path, ckpt)
    loaded = load_checkpoint(tmp_path)
    assert loaded is not None
    assert loaded["input_hash"] == "abc123"
    assert loaded["model"] == "claude-sonnet-4-20250514"


def test_record_artifact(tmp_path):
    ckpt = new_checkpoint("hash", "model")
    record_artifact(ckpt, "research_brief", "/tmp/rb.md", tokens_in=100, tokens_out=200)
    save_checkpoint(tmp_path, ckpt)
    loaded = load_checkpoint(tmp_path)
    assert "research_brief" in loaded["artifacts"]
    assert loaded["artifacts"]["research_brief"]["tokens_in"] == 100


def test_delete_checkpoint(tmp_path):
    ckpt = new_checkpoint("hash", "model")
    save_checkpoint(tmp_path, ckpt)
    assert load_checkpoint(tmp_path) is not None
    delete_checkpoint(tmp_path)
    assert load_checkpoint(tmp_path) is None


def test_completed_stages_checks_file_existence(tmp_path):
    # Create a real file
    artifact_file = tmp_path / "research.md"
    artifact_file.write_text("content")

    ckpt = new_checkpoint("hash", "model")
    record_artifact(ckpt, "research_brief", str(artifact_file))
    record_artifact(ckpt, "prfaq", "/nonexistent/prfaq.md")

    done = completed_stages(ckpt)
    assert "research_brief" in done
    assert "prfaq" not in done  # file doesn't exist


def test_input_hash_stable(tmp_path):
    data = {"b": "2", "a": "1"}
    p = tmp_path / "input.yaml"
    p.write_text(yaml.dump(data))
    h1 = compute_input_hash(str(p))

    # Same data, different key order in source
    p2 = tmp_path / "input2.yaml"
    p2.write_text(yaml.dump({"a": "1", "b": "2"}))
    h2 = compute_input_hash(str(p2))

    assert h1 == h2  # normalization sorts keys


def test_input_hash_changes_on_content_change(tmp_path):
    p = tmp_path / "input.yaml"
    p.write_text(yaml.dump({"a": "1"}))
    h1 = compute_input_hash(str(p))

    p.write_text(yaml.dump({"a": "2"}))
    h2 = compute_input_hash(str(p))

    assert h1 != h2


# ---------- Integration tests: --resume behavior ----------


def test_resume_skips_completed_agents(output_dir, example_input):
    """--resume with research+PRFAQ done should only run Agent 4."""
    # Create fake artifact files and a checkpoint
    rb_path = output_dir / "research_brief_20260415.md"
    rb_path.write_text("# Research")
    prfaq_path = output_dir / "prfaq_test_v1.0.md"
    prfaq_path.write_text("# PRFAQ")

    input_hash = compute_input_hash(example_input)
    ckpt = new_checkpoint(input_hash, "claude-sonnet-4-20250514")
    record_artifact(ckpt, "research_brief", str(rb_path))
    record_artifact(ckpt, "prfaq", str(prfaq_path))
    save_checkpoint(output_dir, ckpt)

    # Mock only brd_from_prfaq_crew (the Agent 4 path)
    mock_result = _mock_crew_result([_minimal_brd(), _minimal_spec()])

    with patch("pm_agent_system.main.PmAgentSystem") as MockCrew:
        instance = MockCrew.return_value
        instance.brd_from_prfaq_crew.return_value.kickoff.return_value = mock_result
        # full_pipeline_crew should NOT be called
        instance.full_pipeline_crew.return_value.kickoff.side_effect = AssertionError(
            "full_pipeline_crew should not be called on resume"
        )

        from pm_agent_system.main import cmd_full_pipeline
        args = argparse.Namespace(
            input_file=example_input, target_tool="kiro",
            requirements_path=None, skip_validation=False,
            resume=True, fresh=False,
            skip_design=True,  # no design brief in the checkpoint
        )
        cmd_full_pipeline(args)

    # Agent 4 crew was called
    instance.brd_from_prfaq_crew.assert_called_once()


def test_resume_full_run_on_hash_mismatch(output_dir, example_input):
    """--resume with mismatched input hash should do a full run."""
    rb_path = output_dir / "research_brief_old.md"
    rb_path.write_text("# Old Research")

    ckpt = new_checkpoint("old-hash-that-wont-match", "claude-sonnet-4-20250514")
    record_artifact(ckpt, "research_brief", str(rb_path))
    save_checkpoint(output_dir, ckpt)

    mock_result = _mock_crew_result([
        _minimal_research(), _minimal_prfaq(), _minimal_brd(), _minimal_spec()
    ])

    with patch("pm_agent_system.main.PmAgentSystem") as MockCrew:
        instance = MockCrew.return_value
        crew_mock = MagicMock()
        crew_mock.kickoff.return_value = mock_result
        instance.full_pipeline_crew.return_value = crew_mock

        from pm_agent_system.main import cmd_full_pipeline
        args = argparse.Namespace(
            input_file=example_input, target_tool="kiro",
            requirements_path=None, skip_validation=False,
            resume=True, fresh=False,
        )
        cmd_full_pipeline(args)

    # Full pipeline was called (not the resume path)
    instance.full_pipeline_crew.assert_called_once()


def test_fresh_deletes_checkpoint(output_dir, example_input):
    """--fresh should delete checkpoint and do a full run."""
    ckpt = new_checkpoint("some-hash", "model")
    save_checkpoint(output_dir, ckpt)

    mock_result = _mock_crew_result([
        _minimal_research(), _minimal_prfaq(), _minimal_brd(), _minimal_spec()
    ])

    with patch("pm_agent_system.main.PmAgentSystem") as MockCrew:
        instance = MockCrew.return_value
        crew_mock = MagicMock()
        crew_mock.kickoff.return_value = mock_result
        instance.full_pipeline_crew.return_value = crew_mock

        from pm_agent_system.main import cmd_full_pipeline
        args = argparse.Namespace(
            input_file=example_input, target_tool="kiro",
            requirements_path=None, skip_validation=False,
            resume=False, fresh=True,
        )
        cmd_full_pipeline(args)

    instance.full_pipeline_crew.assert_called_once()


def test_checkpoint_deleted_on_success(output_dir, example_input):
    """Successful full run should delete the checkpoint."""
    mock_result = _mock_crew_result([
        _minimal_research(), _minimal_prfaq(), _minimal_brd(), _minimal_spec()
    ])

    with patch("pm_agent_system.main.PmAgentSystem") as MockCrew:
        instance = MockCrew.return_value
        crew_mock = MagicMock()
        crew_mock.kickoff.return_value = mock_result
        instance.full_pipeline_crew.return_value = crew_mock

        from pm_agent_system.main import cmd_full_pipeline
        args = argparse.Namespace(
            input_file=example_input, target_tool="kiro",
            requirements_path=None, skip_validation=False,
            resume=False, fresh=False,
        )
        cmd_full_pipeline(args)

    assert load_checkpoint(output_dir) is None
