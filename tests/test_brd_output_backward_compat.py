"""Backward-compatibility tests for BRDOutput after the compliance-aware extension.

A pre-feature BRDOutput payload (no compliance fields) must still validate
against the extended schema, and every new field must fall back to its
documented default.
"""

import json
from pathlib import Path

from pm_agent_system.models.brd_intermediate import (
    BRDComplianceOutput,
    BRDCostRiskOutput,
    BRDStructureOutput,
)
from pm_agent_system.models.brd_output import BRDOutput, DataHandlingSection
from pm_agent_system.models.compliance_primitives import (
    ComplianceGate,
    DataClassification,
    DataElement,
    GateOwner,
    LaunchReadinessItem,
    PrivacyConsiderations,
)

FIXTURES = Path(__file__).parent / "fixtures"
LEGACY_FIXTURE = FIXTURES / "brd_legacy.json"


def _load_legacy_payload() -> dict:
    return json.loads(LEGACY_FIXTURE.read_text())


def _assemble_brd_output_from_intermediates(
    structure: BRDStructureOutput,
    cost_risk: BRDCostRiskOutput,
    compliance: BRDComplianceOutput,
) -> BRDOutput:
    """Test-local synchronous oracle for the three-way BRD assembly merge.

    Production assembly runs through ``brd_assembly_task`` as an LLM task.
    This helper performs the same mechanical field copy that the task is
    instructed to perform, so unit tests can assert post-conditions on
    the merge without invoking an LLM. It is intentionally kept inside
    the test module and is not production code.
    """
    return BRDOutput(
        executive_summary=structure.executive_summary,
        problem_statement=structure.problem_statement,
        proposed_solution_overview=structure.proposed_solution_overview,
        user_stories=structure.user_stories,
        functional_requirements=structure.functional_requirements,
        non_functional_requirements=structure.non_functional_requirements,
        technical_context_and_dependencies=structure.technical_context_and_dependencies,
        cost_flags=cost_risk.cost_flags,
        risks=cost_risk.risks,
        success_metrics=cost_risk.success_metrics,
        timeline_and_milestones=cost_risk.timeline_and_milestones,
        version_history=cost_risk.version_history,
        data_handling_section=DataHandlingSection(
            elements=compliance.data_elements,
            dataset_classification=compliance.dataset_classification,
            gap_flag=compliance.data_handling_gap_flag,
            gap_notes=compliance.data_handling_gaps,
        ),
        vendor_considerations=compliance.vendor_considerations,
        vendor_scenarios_applied=compliance.vendor_scenarios_applied,
        privacy_considerations=compliance.privacy_considerations,
        compliance_gates=compliance.compliance_gates,
        launch_readiness_checklist=compliance.launch_readiness_checklist,
        post_launch_maintenance=compliance.post_launch_maintenance,
    )


def _make_structure_intermediate() -> BRDStructureOutput:
    """Build a populated ``BRDStructureOutput`` from the legacy fixture shape."""
    payload = _load_legacy_payload()
    return BRDStructureOutput(
        executive_summary=payload["executive_summary"],
        problem_statement=payload["problem_statement"],
        proposed_solution_overview=payload["proposed_solution_overview"],
        user_stories=payload["user_stories"],
        functional_requirements=payload["functional_requirements"],
        non_functional_requirements=payload["non_functional_requirements"],
        technical_context_and_dependencies=payload[
            "technical_context_and_dependencies"
        ],
    )


def _make_cost_risk_intermediate() -> BRDCostRiskOutput:
    """Build a populated ``BRDCostRiskOutput`` from the legacy fixture shape."""
    payload = _load_legacy_payload()
    return BRDCostRiskOutput(
        cost_flags=[
            {
                "decision": "Use DynamoDB on-demand capacity",
                "why_it_matters": "Traffic is bursty and low-volume, so on-demand avoids over-provisioning.",
                "tradeoff": "Per-request pricing costs more per unit than provisioned throughput at steady high load.",
                "reference_url": "https://aws.amazon.com/dynamodb/pricing/on-demand/",
                "pricing_data": "On-demand: $1.25 per million write request units in us-east-1.",
            }
        ],
        risks=payload["risks"],
        success_metrics=payload["success_metrics"],
        timeline_and_milestones=payload["timeline_and_milestones"],
        version_history=payload["version_history"],
    )


def _make_compliance_intermediate() -> BRDComplianceOutput:
    """Build a populated ``BRDComplianceOutput`` covering every field."""
    elements = [
        DataElement(
            name="User preferences payload",
            classification=DataClassification.CONFIDENTIAL,
            purpose="Persist per-user UI settings across internal tools.",
        ),
        DataElement(
            name="Cognito user identifier",
            classification=DataClassification.HIGHLY_CONFIDENTIAL,
            purpose="Scope preference records to the calling user.",
        ),
    ]
    return BRDComplianceOutput(
        data_elements=elements,
        dataset_classification=DataClassification.HIGHLY_CONFIDENTIAL,
        vendor_considerations=(
            "No third party stores preference records. "
            "All storage runs on AWS accounts owned by the platform team."
        ),
        vendor_scenarios_applied=["SaaS usage"],
        privacy_considerations=PrivacyConsiderations(
            risks=["Unauthorized read of another user's preferences."],
            mitigations=[
                "Encryption in transit via TLS 1.2 or higher.",
                "Encryption at rest via KMS-managed DynamoDB keys.",
                "Per-user access scoping through Cognito identity tokens.",
            ],
            design_review_flag=True,
        ),
        compliance_gates=[
            ComplianceGate(name="security review", owner=GateOwner.SECURITY),
            ComplianceGate(name="privacy review", owner=GateOwner.PRIVACY),
        ],
        launch_readiness_checklist=[
            LaunchReadinessItem(
                item="Data classification sign-off",
                applies_to="All data elements",
                gate_owner=GateOwner.PM,
                evidence_reference="BRD data handling section",
            ),
            LaunchReadinessItem(
                item="Monitoring or alarm setup",
                applies_to="Production workload",
                gate_owner=GateOwner.ENGINEER,
                evidence_reference="BRD non-functional requirements",
            ),
        ],
        post_launch_maintenance=(
            "Recertify vendor access and data classifications every six months. "
            "Triggers include new data elements, changed data sources, and changed vendor scope."
        ),
        data_handling_gap_flag=False,
        data_handling_gaps=[],
    )


def _make_populated_intermediates() -> (
    tuple[BRDStructureOutput, BRDCostRiskOutput, BRDComplianceOutput]
):
    """Return a triple of populated intermediates for assembly tests."""
    return (
        _make_structure_intermediate(),
        _make_cost_risk_intermediate(),
        _make_compliance_intermediate(),
    )


def test_brd_legacy_fixture_loads_successfully():
    payload = _load_legacy_payload()

    result = BRDOutput.model_validate(payload)

    assert isinstance(result, BRDOutput)


def test_brd_legacy_fixture_defaults_new_compliance_fields():
    payload = _load_legacy_payload()

    result = BRDOutput.model_validate(payload)

    assert isinstance(result.data_handling_section, DataHandlingSection)
    assert result.data_handling_section.elements == []
    assert result.data_handling_section.dataset_classification is None
    assert result.data_handling_section.gap_flag is False
    assert result.data_handling_section.gap_notes == []

    assert result.vendor_considerations == ""
    assert result.vendor_scenarios_applied == []

    assert isinstance(result.privacy_considerations, PrivacyConsiderations)
    assert result.privacy_considerations.risks == []
    assert result.privacy_considerations.mitigations == []
    assert result.privacy_considerations.design_review_flag is False

    assert result.compliance_gates == []
    assert result.launch_readiness_checklist == []
    assert result.post_launch_maintenance == ""


def test_brd_legacy_fixture_preserves_existing_fields():
    payload = _load_legacy_payload()

    result = BRDOutput.model_validate(payload)

    assert result.executive_summary == payload["executive_summary"]
    assert result.user_stories[0].id == "US-001"
    assert len(result.version_history) == 1
    assert result.version_history[0].version == "1.0"


def test_assembly_preserves_structure_fields():
    """Every ``BRDStructureOutput`` field appears on the assembled ``BRDOutput`` byte-identically."""
    structure, cost_risk, compliance = _make_populated_intermediates()

    result = _assemble_brd_output_from_intermediates(structure, cost_risk, compliance)

    assert result.executive_summary == structure.executive_summary
    assert result.problem_statement == structure.problem_statement
    assert result.proposed_solution_overview == structure.proposed_solution_overview
    assert result.user_stories == structure.user_stories
    assert result.functional_requirements == structure.functional_requirements
    assert result.non_functional_requirements == structure.non_functional_requirements
    assert (
        result.technical_context_and_dependencies
        == structure.technical_context_and_dependencies
    )


def test_assembly_preserves_cost_risk_fields():
    """Every ``BRDCostRiskOutput`` field appears on the assembled ``BRDOutput`` byte-identically."""
    structure, cost_risk, compliance = _make_populated_intermediates()

    result = _assemble_brd_output_from_intermediates(structure, cost_risk, compliance)

    assert result.cost_flags == cost_risk.cost_flags
    assert result.risks == cost_risk.risks
    assert result.success_metrics == cost_risk.success_metrics
    assert result.timeline_and_milestones == cost_risk.timeline_and_milestones
    assert result.version_history == cost_risk.version_history


def test_assembly_preserves_compliance_fields():
    """Every ``BRDComplianceOutput`` field lands on the assembled ``BRDOutput`` byte-identically.

    Data-handling content maps into ``data_handling_section`` on the final
    model; the remaining compliance fields map one to one.
    """
    structure, cost_risk, compliance = _make_populated_intermediates()

    result = _assemble_brd_output_from_intermediates(structure, cost_risk, compliance)

    assert result.data_handling_section.elements == compliance.data_elements
    assert (
        result.data_handling_section.dataset_classification
        == compliance.dataset_classification
    )
    assert result.data_handling_section.gap_flag == compliance.data_handling_gap_flag
    assert result.data_handling_section.gap_notes == compliance.data_handling_gaps

    assert result.vendor_considerations == compliance.vendor_considerations
    assert result.vendor_scenarios_applied == compliance.vendor_scenarios_applied
    assert result.privacy_considerations == compliance.privacy_considerations
    assert result.compliance_gates == compliance.compliance_gates
    assert result.launch_readiness_checklist == compliance.launch_readiness_checklist
    assert result.post_launch_maintenance == compliance.post_launch_maintenance


def test_assembly_passes_through_dataset_classification_unchanged():
    """Dataset classification on the assembled BRDOutput is the exact same enum value."""
    structure, cost_risk, compliance = _make_populated_intermediates()

    result = _assemble_brd_output_from_intermediates(structure, cost_risk, compliance)

    assert (
        result.data_handling_section.dataset_classification
        is compliance.dataset_classification
    )
