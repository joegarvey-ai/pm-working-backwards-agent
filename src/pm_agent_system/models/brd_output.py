from pydantic import BaseModel, Field

from pm_agent_system.models.prfaq_output import VersionEntry


class UserStory(BaseModel):
    id: str = Field(description="Format: US-001")
    persona: str
    action: str
    outcome: str
    priority: str = Field(description="P0, P1, or P2")
    source: str = Field(
        description="Traceability — references a research finding or PRFAQ section"
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
        description="A real URL from Tavily search the PM can investigate. No dollar estimates."
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


class BRDOutput(BaseModel):
    executive_summary: str
    problem_statement: str
    proposed_solution_overview: str = Field(
        description="Includes a Mermaid architecture diagram inline as a fenced code block"
    )
    user_stories: list[UserStory] = Field(min_length=3)
    functional_requirements: list[FunctionalRequirement] = Field(min_length=3)
    non_functional_requirements: list[NonFunctionalRequirement] = Field(min_length=2)
    technical_context_and_dependencies: str = Field(
        description="Includes a Mermaid diagram of the current state inline"
    )
    cost_flags: list[CostFlag]
    risks: list[Risk] = Field(min_length=2)
    success_metrics: list[SuccessMetric] = Field(min_length=1)
    timeline_and_milestones: str
    version_history: list[VersionEntry] = Field(min_length=1)
