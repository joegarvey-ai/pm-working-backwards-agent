"""Unit tests for the DesignBriefOutput model, renderer, and pipeline wiring."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from pm_agent_system.models import (
    BRDOutput,
    CodingPromptOutput,
    DesignBriefOutput,
    DesignFlowStep,
    DesignUserFlow,
    PRFAQOutput,
    ResearchOutput,
    ScreenEntry,
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
from pm_agent_system.utils import render_design_brief_to_markdown


# ---------- Helpers ----------


def _minimal_design_brief(**overrides) -> DesignBriefOutput:
    """Construct a DesignBriefOutput with every required field filled in."""
    data = dict(
        product_overview="A task manager for small teams.",
        screen_inventory=[
            ScreenEntry(
                name="Dashboard",
                purpose="Overview of open tasks and team activity.",
                primary_flow="Core",
                source_section="PRFAQ CX narrative, paragraph 2",
            ),
            ScreenEntry(
                name="Task Detail",
                purpose="View and edit a single task.",
                primary_flow="Core",
                source_section="PRFAQ CX narrative, paragraph 3",
            ),
        ],
        user_flows=[
            DesignUserFlow(
                name="Core — create and track a task",
                priority="core",
                steps=[
                    DesignFlowStep(
                        step_number=1,
                        user_action="Click New Task",
                        system_response="Task detail form opens",
                        screen="Dashboard",
                    ),
                ],
                related_screens=["Dashboard", "Task Detail"],
            ),
        ],
        design_principles=[
            "Make status changes one click.",
            "Show blockers before they ship.",
            "Treat async updates as first-class.",
        ],
        competitive_ui_patterns="Jira uses kanban; Linear emphasizes keyboard shortcuts.",
        brand_style_context="Neutral palette, Inter typeface.",
    )
    data.update(overrides)
    return DesignBriefOutput(**data)


# ---------- Model validation ----------


def test_design_brief_output_model_valid():
    brief = _minimal_design_brief()
    assert brief.screen_inventory[0].name == "Dashboard"
    assert brief.user_flows[0].steps[0].step_number == 1
    assert len(brief.design_principles) == 3


def test_design_brief_output_model_missing_screens():
    with pytest.raises(ValidationError):
        _minimal_design_brief(screen_inventory=[
            ScreenEntry(
                name="Dashboard",
                purpose="Only screen.",
                primary_flow="Core",
                source_section="CX narrative",
            ),
        ])


def test_design_brief_output_model_missing_flows():
    with pytest.raises(ValidationError):
        _minimal_design_brief(user_flows=[])


def test_design_brief_output_model_too_few_principles():
    with pytest.raises(ValidationError):
        _minimal_design_brief(design_principles=["Only two.", "Not enough."])


def test_design_brief_output_model_too_many_principles():
    with pytest.raises(ValidationError):
        _minimal_design_brief(design_principles=[
            "One.", "Two.", "Three.", "Four.", "Five.", "Six.",
        ])


def test_design_brief_output_model_defaults():
    brief = _minimal_design_brief()
    assert brief.accessibility_considerations == ""
    assert brief.platform_targets == []
    assert brief.style_guide_used is False


# ---------- Renderer ----------


def test_design_brief_renderer_all_fields():
    brief = _minimal_design_brief(
        accessibility_considerations="WCAG AA.",
        platform_targets=["web", "mobile"],
        style_guide_used=True,
    )
    md = render_design_brief_to_markdown(brief, slug="taskflow")

    # Frontmatter
    assert "type: design_brief" in md
    assert 'slug: "taskflow"' in md

    # Sections
    assert "## Product Overview" in md
    assert "## Screen Inventory" in md
    assert "| Dashboard |" in md
    assert "| Task Detail |" in md
    assert "## User Flows" in md
    assert "### Core — create and track a task (core)" in md
    assert "**Click New Task** → Task detail form opens (on Dashboard)" in md
    assert "## Design Principles" in md
    assert "1. Make status changes one click." in md
    assert "## Competitive UI Patterns" in md
    assert "Jira uses kanban" in md
    assert "## Brand / Style Context" in md
    assert "## Accessibility" in md
    assert "WCAG AA." in md
    assert "## Platform Targets" in md
    assert "web, mobile" in md


def test_design_brief_renderer_incomplete_output_warning():
    brief = _minimal_design_brief()  # accessibility/platform_targets default empty
    md = render_design_brief_to_markdown(brief, slug="taskflow")
    assert "Incomplete output detected" in md
    assert "Accessibility" in md
    assert "Platform Targets" in md


def test_design_brief_renderer_no_style_guide():
    brief = _minimal_design_brief(style_guide_used=False, brand_style_context="")
    md = render_design_brief_to_markdown(brief, slug="taskflow")
    assert "No visual style guide was provided." in md


# ---------- Pipeline integration ----------


def _minimal_research() -> ResearchOutput:
    return ResearchOutput(
        context="Test context.",
        executive_summary="Test summary.",
        market_sizing=MarketSizing(summary="$1B", data_points=["point"], sources=["src"]),
        strategic_implications="Test implications.",
    )


def _minimal_prfaq() -> PRFAQOutput:
    return PRFAQOutput(
        press_release="Test press release.",
        external_faqs=[FAQ(question=f"Q{i}?", answer=f"A{i}", audience="external") for i in range(3)],
        internal_faqs=[FAQ(question=f"IQ{i}?", answer=f"IA{i}", audience="internal") for i in range(5)],
        customer_experience_narrative="Test narrative.",
        version_history=[VersionEntry(version="1.0", date="2026-04-15", author="Agent 2", changes="Initial")],
    )


def _minimal_brd() -> BRDOutput:
    return BRDOutput(
        executive_summary="Exec.",
        problem_statement="Problem.",
        proposed_solution_overview="Solution.",
        user_stories=[
            UserStory(id=f"US-00{i}", persona="PM", action="does", outcome="gets", priority="P0")
            for i in range(1, 4)
        ],
        functional_requirements=[
            FunctionalRequirement(
                id=f"FR-00{i}", description="The system shall do X.",
                rationale="R", acceptance_criteria=["AC"], related_user_stories=[f"US-00{i}"],
            )
            for i in range(1, 4)
        ],
        non_functional_requirements=[
            NonFunctionalRequirement(id="NFR-001", category="performance", description="fast", acceptance_criteria=["AC"]),
            NonFunctionalRequirement(id="NFR-002", category="security", description="TLS", acceptance_criteria=["AC"]),
        ],
        risks=[
            Risk(description="R1", likelihood="low", impact="low", mitigation="M"),
            Risk(description="R2", likelihood="low", impact="low", mitigation="M"),
        ],
        success_metrics=[SuccessMetric(metric="M", target_value="T", measurement_method="How", timeline="Q3")],
        version_history=[VersionEntry(version="1.0", date="2026-04-15", author="Agent 4", changes="Initial")],
    )


def _minimal_spec() -> CodingPromptOutput:
    return CodingPromptOutput(
        build_summary="Build X.",
        user_flows=[UserFlow(name="Flow", steps=["Do thing"], related_requirements=["FR-001"])],
        feature_specs=[FeatureSpec(name="F", description="D", acceptance_criteria=["AC"], priority="P0")],
        target_tool="kiro",
        formatted_spec="# Spec",
    )


def _mock_crew_result(task_outputs):
    """Build a CrewAI-like mock CrewOutput."""
    wrapped = []
    for obj in task_outputs:
        t = MagicMock()
        t.pydantic = obj
        wrapped.append(t)
    result = MagicMock()
    result.tasks_output = wrapped
    result.pydantic = task_outputs[-1]
    return result


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    out = tmp_path / "output"
    out.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(out))
    monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
    yield out


@pytest.fixture
def input_file(tmp_path):
    import yaml
    data = {
        "feature_summary": "TaskFlow",
        "product_name": "TaskFlow",
        "goals": "Test goals",
        "timing": "Q3 2026",
        "user_summary": "Test users",
    }
    path = tmp_path / "input.yaml"
    path.write_text(yaml.dump(data))
    return str(path)


def _args(input_file: str, **overrides) -> argparse.Namespace:
    base = dict(
        input_file=input_file,
        target_tool="kiro",
        requirements_path=None,
        skip_validation=False,
        resume=False,
        fresh=False,
        skip_design=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_full_pipeline_with_design_brief(output_dir, input_file):
    """Run with skip_design=False; expect five artifacts and design brief path passed to BRD."""
    mock_result = _mock_crew_result([
        _minimal_research(), _minimal_prfaq(), _minimal_design_brief(), _minimal_brd(), _minimal_spec(),
    ])

    captured_inputs = {}

    with patch("pm_agent_system.main.PmAgentSystem") as MockCrew:
        instance = MockCrew.return_value
        crew_mock = MagicMock()

        def _kickoff(**kwargs):
            captured_inputs.update(kwargs.get("inputs", {}))
            if crew_mock.task_callback:
                for t in mock_result.tasks_output:
                    crew_mock.task_callback(t)
            return mock_result

        crew_mock.kickoff.side_effect = _kickoff
        instance.full_pipeline_crew.return_value = crew_mock

        from pm_agent_system.main import cmd_full_pipeline
        cmd_full_pipeline(_args(input_file))

    # full_pipeline_crew was called with skip_design=False
    _, kwargs = instance.full_pipeline_crew.call_args
    assert kwargs.get("skip_design") is False

    # BRD task received a non-empty design_brief_path
    assert captured_inputs["design_brief_path"]
    assert "design_brief" in captured_inputs["design_brief_path"]

    # Five artifacts written to output/
    names = [p.name for p in output_dir.iterdir() if p.suffix == ".md"]
    assert any("research_brief" in n for n in names), names
    assert any(n.startswith("prfaq_") for n in names), names
    assert any(n.startswith("design_brief_") for n in names), names
    assert any(n.startswith("brd_") for n in names), names
    assert any(n.startswith("build_spec_") for n in names), names


def test_full_pipeline_skip_design(output_dir, input_file):
    """Run with --skip-design; expect four artifacts and an empty design_brief_path."""
    mock_result = _mock_crew_result([
        _minimal_research(), _minimal_prfaq(), _minimal_brd(), _minimal_spec(),
    ])

    captured_inputs = {}

    with patch("pm_agent_system.main.PmAgentSystem") as MockCrew:
        instance = MockCrew.return_value
        crew_mock = MagicMock()

        def _kickoff(**kwargs):
            captured_inputs.update(kwargs.get("inputs", {}))
            if crew_mock.task_callback:
                for t in mock_result.tasks_output:
                    crew_mock.task_callback(t)
            return mock_result

        crew_mock.kickoff.side_effect = _kickoff
        instance.full_pipeline_crew.return_value = crew_mock

        from pm_agent_system.main import cmd_full_pipeline
        cmd_full_pipeline(_args(input_file, skip_design=True))

    # full_pipeline_crew was called with skip_design=True
    _, kwargs = instance.full_pipeline_crew.call_args
    assert kwargs.get("skip_design") is True

    # No design brief file; design_brief_path stays empty
    assert captured_inputs.get("design_brief_path", "") == ""

    names = [p.name for p in output_dir.iterdir() if p.suffix == ".md"]
    assert not any(n.startswith("design_brief_") for n in names), names
    assert any(n.startswith("research_brief") for n in names), names
    assert any(n.startswith("prfaq_") for n in names), names
    assert any(n.startswith("brd_") for n in names), names
    assert any(n.startswith("build_spec_") for n in names), names


def test_wireframes_standalone(output_dir, input_file, tmp_path):
    """cmd_wireframes saves a design brief from an approved PRFAQ."""
    mock_result = _mock_crew_result([_minimal_design_brief()])

    prfaq_path = tmp_path / "prfaq.md"
    prfaq_path.write_text("# PRFAQ\nContent.")

    with patch("pm_agent_system.main.PmAgentSystem") as MockCrew:
        instance = MockCrew.return_value
        crew_mock = MagicMock()
        crew_mock.kickoff.return_value = mock_result
        instance.design_brief_crew.return_value = crew_mock

        from pm_agent_system.main import cmd_wireframes
        args = argparse.Namespace(
            input_file=input_file,
            prfaq_path=str(prfaq_path),
            research_path=None,
        )
        cmd_wireframes(args)

    names = [p.name for p in output_dir.iterdir() if p.suffix == ".md"]
    assert any(n.startswith("design_brief_") for n in names), names


def test_revise_wireframes(output_dir, tmp_path, monkeypatch):
    """cmd_revise_wireframes bumps or preserves the design brief filename."""
    # Seed an existing design brief
    design_path = tmp_path / "design_brief_taskflow_v1.0.md"
    design_path.write_text(
        "---\n"
        "type: design_brief\n"
        'slug: "taskflow"\n'
        'product_slug: "taskflow"\n'
        'version: "1.0"\n'
        "---\n\n"
        "# Design Brief\n"
    )

    mock_result = _mock_crew_result([_minimal_design_brief()])

    with patch("pm_agent_system.main.PmAgentSystem") as MockCrew:
        instance = MockCrew.return_value
        crew_mock = MagicMock()
        crew_mock.kickoff.return_value = mock_result
        instance.revise_design_brief_crew.return_value = crew_mock

        from pm_agent_system.main import cmd_revise_wireframes
        args = argparse.Namespace(
            design_brief_path=str(design_path),
            context_path=None,
            context_text="Add a settings screen.",
        )
        cmd_revise_wireframes(args)

    names = [p.name for p in output_dir.iterdir() if p.suffix == ".md"]
    assert any(n.startswith("design_brief_") for n in names), names


# ---------- Registry ----------


def test_design_brief_registered_in_provider():
    """Build the full-pipeline registry and confirm DesignBriefOutput dispatches."""
    from pm_agent_system.vault_checkpoint import ArtifactHandler, build_registry

    handler = ArtifactHandler(
        artifact_type="design_brief",
        pydantic_class=DesignBriefOutput,
        render_fn=lambda obj: render_design_brief_to_markdown(obj),
        save_output_fn=lambda md, _obj: Path("/tmp/design_brief.md"),
        version="1.0",
        upstream="prfaq",
        downstream="brd",
    )
    registry = build_registry([handler])
    assert DesignBriefOutput in registry
    assert registry[DesignBriefOutput].artifact_type == "design_brief"
    assert registry[DesignBriefOutput].upstream == "prfaq"
    assert registry[DesignBriefOutput].downstream == "brd"
