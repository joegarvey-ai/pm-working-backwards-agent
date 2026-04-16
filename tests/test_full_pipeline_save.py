"""Integration test: cmd_full_pipeline saves all three artifact files."""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


def _minimal_research() -> ResearchOutput:
    return ResearchOutput(
        context="Test context.",
        executive_summary="Test summary.",
        market_sizing=MarketSizing(summary="$1B", data_points=["point"], sources=["src"]),
        strategic_implications="Test implications.",
    )


def _minimal_prfaq() -> PRFAQOutput:
    return PRFAQOutput(
        press_release="Test press release content for the product launch.",
        external_faqs=[
            FAQ(question="Q1?", answer="A1", audience="external"),
            FAQ(question="Q2?", answer="A2", audience="external"),
            FAQ(question="Q3?", answer="A3", audience="external"),
        ],
        internal_faqs=[
            FAQ(question=f"IQ{i}?", answer=f"IA{i}", audience="internal")
            for i in range(5)
        ],
        customer_experience_narrative="Test narrative.",
        version_history=[
            VersionEntry(version="1.0", date="2026-04-15", author="Agent 2", changes="Initial")
        ],
    )


def _minimal_brd() -> BRDOutput:
    return BRDOutput(
        executive_summary="Test exec summary.",
        problem_statement="Test problem.",
        proposed_solution_overview="Test solution.",
        user_stories=[
            UserStory(id="US-001", persona="PM", action="does X", outcome="gets Y", priority="P0"),
            UserStory(id="US-002", persona="Dev", action="does A", outcome="gets B", priority="P1"),
            UserStory(id="US-003", persona="User", action="does C", outcome="gets D", priority="P1"),
        ],
        functional_requirements=[
            FunctionalRequirement(
                id="FR-001", description="The system shall do X.",
                rationale="Because.", acceptance_criteria=["Given X when Y then Z"],
                related_user_stories=["US-001"],
            ),
            FunctionalRequirement(
                id="FR-002", description="The system shall do Y.",
                rationale="Because.", acceptance_criteria=["Given A when B then C"],
                related_user_stories=["US-002"],
            ),
            FunctionalRequirement(
                id="FR-003", description="The system shall do Z.",
                rationale="Because.", acceptance_criteria=["Given D when E then F"],
                related_user_stories=["US-003"],
            ),
        ],
        non_functional_requirements=[
            NonFunctionalRequirement(id="NFR-001", category="performance", description="p95 < 200ms", acceptance_criteria=["< 200ms"]),
            NonFunctionalRequirement(id="NFR-002", category="security", description="TLS", acceptance_criteria=["TLS 1.3"]),
        ],
        risks=[
            Risk(description="Risk 1", likelihood="medium", impact="high", mitigation="Mitigate"),
            Risk(description="Risk 2", likelihood="low", impact="medium", mitigation="Mitigate"),
        ],
        success_metrics=[
            SuccessMetric(metric="Adoption", target_value="1000 users", measurement_method="Analytics", timeline="Q3"),
        ],
        version_history=[
            VersionEntry(version="1.0", date="2026-04-15", author="Agent 3", changes="Initial")
        ],
    )


def _minimal_spec() -> CodingPromptOutput:
    return CodingPromptOutput(
        build_summary="Build X for Y. Done when Z.",
        user_flows=[UserFlow(name="Main flow", steps=["Step 1"], related_requirements=["FR-001"])],
        feature_specs=[FeatureSpec(name="Feature 1", description="Desc", acceptance_criteria=["AC"], priority="P0")],
        target_tool="kiro",
        formatted_spec="# Spec content",
    )


def _build_mock_result():
    """Build a mock CrewOutput with tasks_output containing all four models."""
    research = _minimal_research()
    prfaq = _minimal_prfaq()
    brd = _minimal_brd()
    spec = _minimal_spec()

    task_research = MagicMock()
    task_research.pydantic = research

    task_prfaq = MagicMock()
    task_prfaq.pydantic = prfaq

    task_brd = MagicMock()
    task_brd.pydantic = brd

    task_spec = MagicMock()
    task_spec.pydantic = spec

    result = MagicMock()
    result.tasks_output = [task_research, task_prfaq, task_brd, task_spec]
    result.pydantic = spec
    return result


@pytest.fixture
def output_dir(tmp_path):
    """Patch OUTPUT_DIR to a temporary directory."""
    out = tmp_path / "output"
    out.mkdir()
    with patch.dict("os.environ", {"OUTPUT_DIR": str(out)}):
        yield out


@pytest.fixture
def example_input(tmp_path):
    """Write a minimal input YAML file."""
    import yaml
    data = {
        "feature_summary": "Test Feature",
        "goals": "Test goals",
        "timing": "Q3 2026",
        "user_summary": "Test users",
    }
    path = tmp_path / "input.yaml"
    path.write_text(yaml.dump(data))
    return str(path)


def test_full_pipeline_saves_all_artifacts(output_dir, example_input):
    """cmd_full_pipeline should produce research_brief, prfaq, and brd files."""
    mock_result = _build_mock_result()

    with patch("pm_agent_system.main.PmAgentSystem") as MockCrew:
        instance = MockCrew.return_value
        crew_mock = MagicMock()

        # When kickoff is called, trigger the task_callback for each task output
        # to simulate what CrewAI does during a real run.
        def _kickoff_with_callbacks(**kwargs):
            if crew_mock.task_callback:
                for task_output in mock_result.tasks_output:
                    crew_mock.task_callback(task_output)
            return mock_result

        crew_mock.kickoff.side_effect = _kickoff_with_callbacks
        instance.full_pipeline_crew.return_value = crew_mock

        from pm_agent_system.main import cmd_full_pipeline

        args = argparse.Namespace(
            input_file=example_input,
            target_tool="kiro",
            requirements_path=None,
            skip_validation=False,
            resume=False,
            fresh=False,
        )
        cmd_full_pipeline(args)

    files = list(output_dir.iterdir())
    filenames = [f.name for f in files]

    # Check that research brief, prfaq, and brd files exist
    assert any("research_brief" in name and name.endswith(".md") for name in filenames), (
        f"research_brief_*.md not found in {filenames}"
    )
    assert any("prfaq" in name and name.endswith(".md") for name in filenames), (
        f"prfaq_*.md not found in {filenames}"
    )
    assert any("brd" in name and name.endswith(".md") for name in filenames), (
        f"brd_*.md not found in {filenames}"
    )

    # Verify files are non-empty
    for f in files:
        if f.suffix == ".md":
            assert f.stat().st_size > 0, f"{f.name} is empty"
