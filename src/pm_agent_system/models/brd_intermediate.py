"""Intermediate models for the split BRD pipeline.

Task 1 produces BRDStructureOutput (requirements, user stories, prose).
Task 2 produces BRDCostRiskOutput (cost flags, risks, metrics, timeline).
Task 3 merges both into the final BRDOutput.
"""

from pydantic import BaseModel, Field, model_validator

from pm_agent_system.models.brd_output import (
    CostFlag,
    FunctionalRequirement,
    NonFunctionalRequirement,
    Risk,
    SuccessMetric,
    UserStory,
)
from pm_agent_system.models.compliance_primitives import (
    ComplianceGate,
    DataClassification,
    DataElement,
    GateOwner,
    LaunchReadinessItem,
    PrivacyConsiderations,
    _DATA_CLASS_ORDER,
    _derive_dataset_classification,
)
from pm_agent_system.models.prfaq_output import VersionEntry

__all__ = [
    "BRDComplianceOutput",
    "BRDCostRiskOutput",
    "BRDStructureOutput",
    "ComplianceGate",
    "DataClassification",
    "DataElement",
    "GateOwner",
    "LaunchReadinessItem",
    "PrivacyConsiderations",
    "_DATA_CLASS_ORDER",
    "_derive_dataset_classification",
]


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


class BRDComplianceOutput(BaseModel):
    """Compliance intermediate: data elements, gates, privacy, and gap flags."""

    data_elements: list[DataElement] = Field(default_factory=list)
    dataset_classification: DataClassification | None = None
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
    data_handling_gap_flag: bool = False
    data_handling_gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_gap_pairing(self):
        if self.data_handling_gap_flag:
            if self.data_elements:
                raise ValueError(
                    "data_handling_gap_flag is True but data_elements is non-empty"
                )
            if self.dataset_classification is not None:
                raise ValueError(
                    "data_handling_gap_flag is True but dataset_classification is set"
                )
            if not self.data_handling_gaps:
                raise ValueError(
                    "data_handling_gap_flag is True but data_handling_gaps is empty"
                )
        return self
