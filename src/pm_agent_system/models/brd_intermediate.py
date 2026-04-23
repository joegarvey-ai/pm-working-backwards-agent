"""Intermediate models for the split BRD pipeline.

Task 1 produces BRDStructureOutput (requirements, user stories, prose).
Task 2 produces BRDCostRiskOutput (cost flags, risks, metrics, timeline).
Task 3 merges both into the final BRDOutput.
"""

from pydantic import BaseModel, Field

from pm_agent_system.models.brd_output import (
    CostFlag,
    FunctionalRequirement,
    NonFunctionalRequirement,
    Risk,
    SuccessMetric,
    UserStory,
)
from pm_agent_system.models.prfaq_output import VersionEntry


class BRDStructureOutput(BaseModel):
    """Core BRD content: prose sections, user stories, requirements."""

    executive_summary: str
    problem_statement: str
    proposed_solution_overview: str = Field(
        default="",
        description="Includes a Mermaid architecture diagram inline",
    )
    user_stories: list[UserStory] = Field(default_factory=list, min_length=3)
    functional_requirements: list[FunctionalRequirement] = Field(
        default_factory=list, min_length=3
    )
    non_functional_requirements: list[NonFunctionalRequirement] = Field(
        default_factory=list, min_length=2
    )
    technical_context_and_dependencies: str = Field(default="")


class BRDCostRiskOutput(BaseModel):
    """Cost flags, risks, success metrics, and timeline from pricing research."""

    cost_flags: list[CostFlag] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list, min_length=2)
    success_metrics: list[SuccessMetric] = Field(default_factory=list, min_length=1)
    timeline_and_milestones: str = Field(default="")
    version_history: list[VersionEntry] = Field(default_factory=list, min_length=1)
