"""Shared enums and nested compliance models reused across BRD and PRFAQ outputs."""

from enum import Enum

from pydantic import BaseModel, Field


class DataClassification(str, Enum):
    """Data sensitivity levels used across compliance models."""

    PUBLIC = "Public"
    CONFIDENTIAL = "Confidential"
    HIGHLY_CONFIDENTIAL = "Highly Confidential"
    RESTRICTED = "Restricted"
    CRITICAL = "Critical"


_DATA_CLASS_ORDER = {
    DataClassification.PUBLIC: 0,
    DataClassification.CONFIDENTIAL: 1,
    DataClassification.HIGHLY_CONFIDENTIAL: 2,
    DataClassification.RESTRICTED: 3,
    DataClassification.CRITICAL: 4,
}


class GateOwner(str, Enum):
    """Owner roles for compliance gates and the RACI matrix."""

    PM = "PM"
    TECH_LEAD = "Tech Lead"
    ENGINEER = "Engineer"
    LEGAL = "Legal"
    SECURITY = "Security"
    PRIVACY = "Privacy"


class DataElement(BaseModel):
    """A single data element the product collects, processes, stores, or transmits."""

    name: str
    classification: DataClassification
    purpose: str = ""


class ComplianceGate(BaseModel):
    """An applicable compliance gate with its owner and start-early guidance."""

    name: str = Field(
        description='One of "security review", "privacy review", '
        '"legal or contract review", "procurement review"'
    )
    note: str = Field(
        default="start early, run in parallel, do not launch with open "
        "Critical or High findings"
    )
    owner: GateOwner


class LaunchReadinessItem(BaseModel):
    """A single row in the launch readiness checklist."""

    item: str
    applies_to: str
    gate_owner: GateOwner
    evidence_reference: str = ""


class PrivacyConsiderations(BaseModel):
    """Privacy risks, mitigations, and the design review flag."""

    risks: list[str] = Field(default_factory=list)
    mitigations: list[str] = Field(default_factory=list)
    design_review_flag: bool = False


def _derive_dataset_classification(
    elements: list[DataElement],
) -> DataClassification | None:
    """Return the highest classification across elements, or None for empty list."""
    if not elements:
        return None
    return max(
        elements, key=lambda e: _DATA_CLASS_ORDER[e.classification]
    ).classification
