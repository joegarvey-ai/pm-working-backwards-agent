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


class RACIRow(BaseModel):
    """One role's RACI assignment for a compliance decision."""

    role: str = Field(
        description="Role label such as PM, Tech Lead, Engineer, Legal, Security, or Privacy"
    )
    responsible: bool = False
    accountable: bool = False
    consulted: bool = False
    informed: bool = False


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
    stride_stub: str = Field(
        default="",
        description="Rendered STRIDE markdown block. Populated deterministically by render_build_spec.py, not by the LLM."
    )
    raci_matrix: list[RACIRow] = Field(
        default_factory=list,
        description="Rendered RACI rows for compliance decisions. Populated deterministically by render_build_spec.py, not by the LLM."
    )
