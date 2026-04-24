"""Classifier output schema for the feedback loop.

The feedback_classify_task returns one of these per feedback item.
The caller copies the fields onto the source FeedbackItem and writes
the updated item back to disk.

See 2026-04-24_wave2_design_classifier_and_apply.md for the full design.
"""

from pydantic import BaseModel, Field

from pm_agent_system.models.feedback_item import (
    ArtifactImpact,
    ContradictionFlag,
    ResearchGap,
)


class FeedbackClassification(BaseModel):
    """Routing decisions for a single feedback item, produced by the classifier agent."""

    affects: list[ArtifactImpact] = Field(
        default_factory=list,
        description="Artifacts (and sections within each) that this feedback affects",
    )
    research_gaps: list[ResearchGap] = Field(
        default_factory=list,
        description="Research gaps that Tavily, CompetitiveIntel, or Dovetail could fill",
    )
    contradictions: list[ContradictionFlag] = Field(
        default_factory=list,
        description="Conflicts with other feedback items or existing artifact content",
    )
    classifier_notes: str = Field(
        default="",
        description="Optional free-form notes from the classifier (debug aid)",
    )
