from pydantic import BaseModel, Field

from pm_agent_system.models.brd_output import CodeSample

VALID_TARGET_TOOLS = ("kiro", "claude_code", "cursor", "lovable")


class UserFlow(BaseModel):
    name: str
    steps: list[str] = Field(
        description='Sequence like "User does X" → "System does Y" → "User sees Z"'
    )
    related_requirements: list[str] = Field(
        description="FR-### IDs from the BRD"
    )


class FeatureSpec(BaseModel):
    name: str
    description: str
    acceptance_criteria: list[str] = Field(
        description="EXACT copy from the BRD. Do not paraphrase, summarize, or reword."
    )
    priority: str = Field(description="P0, P1, or P2")
    code_samples: list[CodeSample] = Field(
        default_factory=list, description="Carried forward from the BRD"
    )


class CodingPromptOutput(BaseModel):
    build_summary: str = Field(
        description="2-3 sentences: what to build, for whom, done condition"
    )
    user_flows: list[UserFlow] = Field(default_factory=list, min_length=1)
    feature_specs: list[FeatureSpec] = Field(default_factory=list, min_length=1)
    technical_constraints: list[str] = Field(
        default_factory=list,
        description="AWS-specific constraints carried from BRD"
    )
    architecture_reference: str = Field(
        default="",
        description="Mermaid diagram + description of target architecture"
    )
    current_state_context: str = Field(default="")
    out_of_scope: list[str] = Field(
        default_factory=list,
        description="P2 items and constraint-driven exclusions. The coding tool must not build these."
    )
    target_tool: str = Field(description="kiro, claude_code, cursor, or lovable")
    formatted_spec: str = Field(
        default="",
        description="The complete tool-specific output ready to paste or load into the chosen tool"
    )
