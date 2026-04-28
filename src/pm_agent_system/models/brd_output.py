from pydantic import BaseModel, Field

from pm_agent_system.models.compliance_primitives import (
    ComplianceGate,
    DataClassification,
    DataElement,
    LaunchReadinessItem,
    PrivacyConsiderations,
)
from pm_agent_system.models.prfaq_output import VersionEntry


class UserStory(BaseModel):
    id: str = Field(description="Format: US-001")
    persona: str
    action: str
    outcome: str
    priority: str = Field(description="P0, P1, or P2")
    origin: str = Field(
        default="agent-generated",
        description=(
            "One of: 'customer_input' (from PM's requirements file), "
            "'agent-generated' (derived from PRFAQ/research), or 'reconciled' "
            "(PM requirement modified to align with PRFAQ)"
        ),
    )
    traceability: str = Field(
        default="",
        description=(
            "Reference to a PRFAQ section, research finding, or PM constraint "
            "that justifies this user story. E.g. 'PRFAQ FAQ #3', 'Research: competitor analysis'"
        ),
    )


class CodeSample(BaseModel):
    description: str = Field(description="What this snippet demonstrates")
    language: str = Field(description="python, json, yaml, typescript, mermaid, etc.")
    code: str


class FunctionalRequirement(BaseModel):
    id: str = Field(description="Format: FR-001")
    description: str = Field(description='Written as "The system shall..."')
    rationale: str
    acceptance_criteria: list[str] = Field(
        description="Given/when/then format. These are carried verbatim into the build spec."
    )
    related_user_stories: list[str] = Field(
        min_length=1, description="At least one US-### reference required for traceability"
    )
    code_samples: list[CodeSample] = Field(
        default_factory=list,
        description="API contracts, data model schemas, integration snippets",
    )
    origin: str = Field(
        default="agent-generated",
        description=(
            "One of: 'customer_input' (from PM's requirements file), "
            "'agent-generated' (derived from PRFAQ/research), or 'reconciled' "
            "(PM requirement modified to align with PRFAQ)"
        ),
    )
    traceability: str = Field(
        default="",
        description=(
            "Reference to a PRFAQ section, research finding, or PM constraint "
            "that justifies this requirement. E.g. 'PRFAQ FAQ #3', 'CR-005 (PM input)'"
        ),
    )


class NonFunctionalRequirement(BaseModel):
    id: str = Field(description="Format: NFR-001")
    category: str = Field(
        description="performance, security, scalability, accessibility, compliance"
    )
    description: str
    acceptance_criteria: list[str]


class CostFlag(BaseModel):
    decision: str
    why_it_matters: str
    tradeoff: str
    reference_url: str = Field(
        description="A real URL from Tavily search the PM can investigate."
    )
    pricing_data: str = Field(
        default="",
        description="Raw pricing summary from aws_pricing_lookup, for traceability.",
    )


class Risk(BaseModel):
    description: str
    likelihood: str = Field(description="high, medium, or low")
    impact: str
    mitigation: str


class SuccessMetric(BaseModel):
    metric: str
    target_value: str
    measurement_method: str = Field(
        description='How it will be measured, e.g. "CloudWatch custom metric"'
    )
    timeline: str


class DataHandlingSection(BaseModel):
    """Data elements, dataset classification, and any gap flag for the BRD."""

    elements: list[DataElement] = Field(default_factory=list)
    dataset_classification: DataClassification | None = None
    gap_flag: bool = False
    gap_notes: list[str] = Field(default_factory=list)


class BRDOutput(BaseModel):
    executive_summary: str
    problem_statement: str
    proposed_solution_overview: str = Field(
        description="Includes a Mermaid architecture diagram inline as a fenced code block"
    )
    user_stories: list[UserStory] = Field(default_factory=list, min_length=3)
    functional_requirements: list[FunctionalRequirement] = Field(default_factory=list, min_length=3)
    non_functional_requirements: list[NonFunctionalRequirement] = Field(default_factory=list, min_length=2)
    technical_context_and_dependencies: str = Field(
        default="",
        description="Includes a Mermaid diagram of the current state inline"
    )
    cost_flags: list[CostFlag] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list, min_length=2)
    success_metrics: list[SuccessMetric] = Field(default_factory=list, min_length=1)
    timeline_and_milestones: str = Field(default="")
    version_history: list[VersionEntry] = Field(default_factory=list, min_length=1)
    data_handling_section: DataHandlingSection = Field(
        default_factory=DataHandlingSection
    )
    vendor_considerations: str = ""
    vendor_scenarios_applied: list[str] = Field(default_factory=list)
    privacy_considerations: PrivacyConsiderations = Field(
        default_factory=PrivacyConsiderations
    )
    compliance_gates: list[ComplianceGate] = Field(default_factory=list)
    launch_readiness_checklist: list[LaunchReadinessItem] = Field(
        default_factory=list
    )
    post_launch_maintenance: str = ""
