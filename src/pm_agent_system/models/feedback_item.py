"""Feedback item model for the stakeholder feedback loop.

A FeedbackItem is a piece of stakeholder input (from a VP, customer,
engineer, legal review, prototype demo, or any other source) that may
affect one or more artifacts in the PM agent pipeline. Feedback items
are stored as markdown files in output/feedback/ with YAML frontmatter
carrying the structured metadata.

See the planning doc 2026-04-24_stakeholder_feedback_loop_plan.md for
the full UX design.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------- Enums ----------

FeedbackStatus = Literal["open", "incorporated", "rejected", "deferred"]

ArtifactType = Literal[
    "research_brief",
    "prfaq",
    "design_brief",
    "brd",
    "build_spec",
]

ResearchTool = Literal["tavily", "competitive_intel", "dovetail"]


# ---------- Sub-models ----------


class ArtifactImpact(BaseModel):
    """Classifier output: which artifact and sections a feedback item affects."""

    artifact: ArtifactType
    sections: list[str] = Field(
        default_factory=list,
        description="Section names within the artifact (e.g., 'press_release', 'risks')",
    )
    confidence: float = Field(
        ge=0.0, le=1.0, default=1.0,
        description="Classifier confidence 0.0-1.0 that this impact is real",
    )
    rationale: str = Field(default="", description="One-line why this artifact is affected")


class ResearchGap(BaseModel):
    """Classifier output: this feedback needs new research from a specific tool."""

    tool: ResearchTool
    query: str = Field(description="Scoped research query to fill the gap")
    rationale: str = Field(default="", description="Why existing research does not cover this")


class ContradictionFlag(BaseModel):
    """Classifier output: this feedback conflicts with existing content or other feedback."""

    conflicts_with: str = Field(
        description="What it conflicts with (e.g., 'fb-2026-04-24-002' or 'research_brief v1.0 customer_quote #3')"
    )
    summary: str = Field(description="One-line description of the contradiction")


class VersionRef(BaseModel):
    """Record that a feedback item was incorporated into a specific artifact version."""

    artifact: ArtifactType
    version: str = Field(description="Artifact version string, e.g. '1.2'")
    incorporated_at: datetime


# ---------- Main model ----------


class FeedbackItem(BaseModel):
    """A single piece of stakeholder feedback with routing metadata."""

    # Identity
    id: str = Field(description="Feedback ID, e.g. 'fb-2026-04-24-001'")
    source: str = Field(description="Human-readable source, e.g. 'VP Engineering (Sam Chen)'")
    received: datetime = Field(description="When the feedback was received")

    # Lifecycle
    status: FeedbackStatus = "open"

    # Summary (first line of the markdown body, auto-populated if blank)
    summary: str = Field(default="", description="One-line summary of the feedback")

    # Routing (populated by the classifier)
    affects: list[ArtifactImpact] = Field(default_factory=list)
    research_gaps: list[ResearchGap] = Field(default_factory=list)
    contradictions: list[ContradictionFlag] = Field(default_factory=list)

    # Applied
    incorporated_in: list[VersionRef] = Field(default_factory=list)

    # Metadata
    rejection_reason: str = Field(default="", description="Populated when status=rejected")
    defer_until: str = Field(default="", description="Populated when status=deferred")

    # Full body (raw markdown, not serialized to frontmatter)
    raw_text: str = Field(
        default="",
        description="Free-form markdown body, read from the file content after frontmatter",
    )

    def frontmatter_dict(self) -> dict:
        """Return the subset of fields that serialize to YAML frontmatter.

        raw_text is excluded because it is stored as the markdown body below
        the frontmatter block.
        """
        return self.model_dump(mode="json", exclude={"raw_text"})
