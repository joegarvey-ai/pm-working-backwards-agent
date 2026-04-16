"""Tests for the output inspector and renderer warning blocks."""

from pydantic import BaseModel, Field

from pm_agent_system.output_inspector import find_defaulted_empty_fields, format_warning_block
from pm_agent_system.models import BRDOutput
from pm_agent_system.models.brd_output import (
    FunctionalRequirement,
    NonFunctionalRequirement,
    Risk,
    SuccessMetric,
    UserStory,
)
from pm_agent_system.models.prfaq_output import VersionEntry
from pm_agent_system.utils.render_brd import render_brd_to_markdown


# ---------- Unit tests: find_defaulted_empty_fields ----------


class FixtureModel(BaseModel):
    required_field: str
    optional_str: str = ""
    optional_list: list[str] = Field(default_factory=list)
    optional_with_value: str = "default"


def test_detects_empty_defaults():
    instance = FixtureModel(required_field="present")
    empty = find_defaulted_empty_fields(instance)
    assert "optional_str" in empty
    assert "optional_list" in empty


def test_ignores_populated_defaults():
    instance = FixtureModel(
        required_field="present",
        optional_str="filled",
        optional_list=["item"],
    )
    empty = find_defaulted_empty_fields(instance)
    assert "optional_str" not in empty
    assert "optional_list" not in empty


def test_ignores_required_fields():
    instance = FixtureModel(required_field="present")
    empty = find_defaulted_empty_fields(instance)
    assert "required_field" not in empty


def test_detects_non_empty_default_string():
    """A field with default='default' that still has its default should not be flagged."""
    instance = FixtureModel(required_field="present")
    empty = find_defaulted_empty_fields(instance)
    # optional_with_value has default="default" which is non-empty
    assert "optional_with_value" not in empty


# ---------- Unit tests: format_warning_block ----------


def test_warning_block_empty_when_no_fields():
    assert format_warning_block([]) == ""


def test_warning_block_includes_field_names():
    block = format_warning_block(["risks", "non_functional_requirements"])
    assert "Risks" in block
    assert "Non-Functional Requirements (NFRs)" in block
    assert "Incomplete output detected" in block


# ---------- Renderer integration: BRD warning block ----------


def _brd_with_empty_risks() -> BRDOutput:
    """Simulate a truncated LLM response where some defaulted fields are empty.

    Uses model_construct to skip validation (which has min_length constraints)
    just as Pydantic does when deserializing a truncated JSON response with
    default_factory filling in the missing fields.
    """
    return BRDOutput.model_construct(
        executive_summary="Exec.",
        problem_statement="Problem.",
        proposed_solution_overview="Solution.",
        user_stories=[
            UserStory(id="US-001", persona="PM", action="X", outcome="Y", priority="P0"),
            UserStory(id="US-002", persona="Dev", action="A", outcome="B", priority="P1"),
            UserStory(id="US-003", persona="User", action="C", outcome="D", priority="P1"),
        ],
        functional_requirements=[
            FunctionalRequirement(
                id=f"FR-00{i}", description="Shall.", rationale="Because.",
                acceptance_criteria=["AC"], related_user_stories=[f"US-00{i}"],
            )
            for i in range(1, 4)
        ],
        # These are left empty (as default_factory would produce):
        non_functional_requirements=[],
        risks=[],
        cost_flags=[],
        success_metrics=[
            SuccessMetric(metric="M", target_value="V", measurement_method="CM", timeline="Q3"),
        ],
        timeline_and_milestones="",
        technical_context_and_dependencies="",
        version_history=[
            VersionEntry(version="1.0", date="2026-04-15", author="Agent 3", changes="Init"),
        ],
    )


def _brd_fully_populated() -> BRDOutput:
    from pm_agent_system.models.brd_output import CostFlag
    return BRDOutput(
        executive_summary="Exec.",
        problem_statement="Problem.",
        proposed_solution_overview="Solution.",
        user_stories=[
            UserStory(id="US-001", persona="PM", action="X", outcome="Y", priority="P0"),
            UserStory(id="US-002", persona="Dev", action="A", outcome="B", priority="P1"),
            UserStory(id="US-003", persona="User", action="C", outcome="D", priority="P1"),
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
        technical_context_and_dependencies="Uses Lambda + DynamoDB.",
        cost_flags=[
            CostFlag(decision="DynamoDB on-demand", why_it_matters="Cost", tradeoff="Simpler", reference_url="https://example.com"),
        ],
        risks=[
            Risk(description="R1", likelihood="med", impact="high", mitigation="M"),
            Risk(description="R2", likelihood="low", impact="med", mitigation="M"),
        ],
        success_metrics=[
            SuccessMetric(metric="M", target_value="V", measurement_method="CM", timeline="Q3"),
        ],
        timeline_and_milestones="Phase 1: Q3",
        version_history=[
            VersionEntry(version="1.0", date="2026-04-15", author="Agent 3", changes="Init"),
        ],
    )


def test_brd_renderer_warning_on_empty_fields():
    brd = _brd_with_empty_risks()
    md = render_brd_to_markdown(brd, slug="test")
    assert "Incomplete output detected" in md
    assert "Risks" in md
    assert "_Not generated in this run._" in md


def test_brd_renderer_no_warning_when_populated():
    brd = _brd_fully_populated()
    md = render_brd_to_markdown(brd, slug="test")
    assert "Incomplete output detected" not in md
    assert "_Not generated in this run._" not in md
