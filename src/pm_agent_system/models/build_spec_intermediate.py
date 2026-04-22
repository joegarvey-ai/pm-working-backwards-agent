"""Intermediate model for the split build spec pipeline.

Task 1 produces BuildSpecStructureOutput (everything except formatted_spec).
Task 2 reads that and produces only the FormattedSpecOutput.
The CLI merges them into the final CodingPromptOutput for rendering.
"""

from pydantic import BaseModel, Field

from pm_agent_system.models.brd_output import CodeSample


class UserFlowIntermediate(BaseModel):
    name: str
    steps: list[str] = Field(
        description='Sequence like "User does X" then "System does Y"'
    )
    related_requirements: list[str] = Field(
        description="FR-### IDs from the BRD"
    )


class FeatureSpecIntermediate(BaseModel):
    name: str
    description: str
    acceptance_criteria: list[str] = Field(
        description="EXACT copy from the BRD. Do not paraphrase."
    )
    priority: str = Field(description="P0, P1, or P2")
    code_samples: list[CodeSample] = Field(default_factory=list)


class BuildSpecStructureOutput(BaseModel):
    """All build spec fields except formatted_spec."""

    build_summary: str = Field(
        description="2-3 sentences: what to build, for whom, done condition"
    )
    user_flows: list[UserFlowIntermediate] = Field(
        default_factory=list, min_length=1
    )
    feature_specs: list[FeatureSpecIntermediate] = Field(
        default_factory=list, min_length=1
    )
    technical_constraints: list[str] = Field(default_factory=list)
    architecture_reference: str = Field(default="")
    current_state_context: str = Field(default="")
    out_of_scope: list[str] = Field(default_factory=list)
    target_tool: str = Field(description="kiro, claude_code, cursor, or lovable")


class FormattedSpecOutput(BaseModel):
    """Just the formatted_spec string, produced by a second task."""

    formatted_spec: str = Field(
        description="The complete tool-specific output ready to paste into the chosen tool"
    )
    target_tool: str = Field(description="The tool this spec is formatted for")
