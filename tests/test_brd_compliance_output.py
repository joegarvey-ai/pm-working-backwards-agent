"""Validation tests for BRDComplianceOutput and its nested models.

Covers default and populated construction, enum constraints on data
classification and gate owner fields, and the gap-flag pairing invariant
enforced by the model validator on BRDComplianceOutput.
"""

import pytest
from pydantic import ValidationError

from pm_agent_system.models import (
    BRDComplianceOutput,
    ComplianceGate,
    DataClassification,
    DataElement,
    GateOwner,
    LaunchReadinessItem,
    PrivacyConsiderations,
)


def test_brd_compliance_output_default_construction():
    output = BRDComplianceOutput()

    assert output.data_elements == []
    assert output.dataset_classification is None
    assert output.vendor_considerations == ""
    assert output.vendor_scenarios_applied == []
    assert output.privacy_considerations == PrivacyConsiderations()
    assert output.compliance_gates == []
    assert output.launch_readiness_checklist == []
    assert output.post_launch_maintenance == ""
    assert output.data_handling_gap_flag is False
    assert output.data_handling_gaps == []


def test_brd_compliance_output_full_construction():
    element = DataElement(
        name="customer_email",
        classification=DataClassification.HIGHLY_CONFIDENTIAL,
        purpose="account recovery",
    )
    gate = ComplianceGate(name="privacy review", owner=GateOwner.PRIVACY)
    checklist_item = LaunchReadinessItem(
        item="privacy mitigation sign-off",
        applies_to="elements at Confidential and above",
        gate_owner=GateOwner.PRIVACY,
        evidence_reference="BRD privacy considerations",
    )
    privacy = PrivacyConsiderations(
        risks=["unauthorized disclosure of customer email"],
        mitigations=["encryption at rest with KMS", "access controls via Cognito"],
        design_review_flag=True,
    )

    output = BRDComplianceOutput(
        data_elements=[element],
        dataset_classification=DataClassification.HIGHLY_CONFIDENTIAL,
        vendor_considerations="no third party is involved",
        vendor_scenarios_applied=[],
        privacy_considerations=privacy,
        compliance_gates=[gate],
        launch_readiness_checklist=[checklist_item],
        post_launch_maintenance="recertify data classifications annually",
    )

    dumped = output.model_dump()
    assert dumped["data_elements"][0]["name"] == "customer_email"
    assert dumped["data_elements"][0]["classification"] == "Highly Confidential"
    assert dumped["dataset_classification"] == "Highly Confidential"
    assert dumped["vendor_considerations"] == "no third party is involved"
    assert dumped["vendor_scenarios_applied"] == []
    assert dumped["privacy_considerations"]["design_review_flag"] is True
    assert dumped["privacy_considerations"]["risks"] == [
        "unauthorized disclosure of customer email"
    ]
    assert dumped["compliance_gates"][0]["name"] == "privacy review"
    assert dumped["compliance_gates"][0]["owner"] == "Privacy"
    assert dumped["launch_readiness_checklist"][0]["gate_owner"] == "Privacy"
    assert dumped["post_launch_maintenance"] == (
        "recertify data classifications annually"
    )
    assert dumped["data_handling_gap_flag"] is False
    assert dumped["data_handling_gaps"] == []


def test_invalid_classification_rejected():
    with pytest.raises(ValidationError):
        DataElement(name="some_field", classification="Top Secret")


def test_invalid_gate_owner_rejected_on_launch_item():
    with pytest.raises(ValidationError):
        LaunchReadinessItem(
            item="data classification sign-off",
            applies_to="all data elements",
            gate_owner="Intern",
        )


def test_invalid_gate_owner_rejected_on_compliance_gate():
    with pytest.raises(ValidationError):
        ComplianceGate(name="security review", owner="Intern")


def test_gap_flag_true_with_empty_gaps_auto_corrected():
    output = BRDComplianceOutput(data_handling_gap_flag=True)
    assert output.data_handling_gaps == [
        "Data handling analysis incomplete (gap flag set with no details)"
    ]


def test_gap_flag_true_with_non_empty_elements_auto_corrected():
    output = BRDComplianceOutput(
        data_handling_gap_flag=True,
        data_handling_gaps=["upstream PRFAQ did not list data elements"],
        data_elements=[
            DataElement(name="x", classification=DataClassification.PUBLIC)
        ],
    )
    assert output.data_elements == []
    assert output.data_handling_gaps == ["upstream PRFAQ did not list data elements"]


def test_gap_flag_true_with_dataset_classification_auto_corrected():
    output = BRDComplianceOutput(
        data_handling_gap_flag=True,
        data_handling_gaps=["upstream PRFAQ did not list data elements"],
        dataset_classification=DataClassification.PUBLIC,
    )
    assert output.dataset_classification is None
    assert output.data_handling_gaps == ["upstream PRFAQ did not list data elements"]


def test_gap_flag_true_with_valid_pairing_accepted():
    output = BRDComplianceOutput(
        data_handling_gap_flag=True,
        data_handling_gaps=["upstream PRFAQ did not list data elements"],
    )

    assert output.data_handling_gap_flag is True
    assert output.data_elements == []
    assert output.dataset_classification is None
    assert output.data_handling_gaps == [
        "upstream PRFAQ did not list data elements"
    ]


def test_gap_flag_false_allows_any_elements_shape():
    empty = BRDComplianceOutput(data_handling_gap_flag=False)
    assert empty.data_elements == []
    assert empty.dataset_classification is None

    populated = BRDComplianceOutput(
        data_handling_gap_flag=False,
        data_elements=[
            DataElement(
                name="public_profile",
                classification=DataClassification.PUBLIC,
            ),
            DataElement(
                name="session_token",
                classification=DataClassification.RESTRICTED,
            ),
        ],
        dataset_classification=DataClassification.RESTRICTED,
    )
    assert [e.name for e in populated.data_elements] == [
        "public_profile",
        "session_token",
    ]
    assert populated.dataset_classification == DataClassification.RESTRICTED
