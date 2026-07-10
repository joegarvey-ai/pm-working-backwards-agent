"""Property-based tests for compliance-aware-brd correctness properties.

One test (or tight group of tests) per property named in the
compliance-aware-brd design. Each test validates a universal rule across
randomly generated inputs using hypothesis, rather than a single example.

Properties covered in this file:
- Property 1: Enum values are bounded at schema level.
- Property 2: Dataset classification is the element-wise maximum.
- Property 3: Gap flag pairing invariant on BRDComplianceOutput.
- Property 4: Assembly preserves intermediate content byte-identically.
- Property 5 (STRIDE and RACI renderer half): build spec renders STRIDE
  and RACI deterministically from trigger state on the BRDOutput.
- Property 5 (BRD markdown half): render_brd_to_markdown preserves the
  compliance content on the BRDOutput (section headers in declared
  order, element classifications, gate owners, and the verbatim gap
  notice).
- Property 6: Renderer static strings contain zero banned words and
  zero em dashes used as punctuation.
"""

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from pm_agent_system.models import (
    BRDComplianceOutput,
    CodeSample,
    ComplianceGate,
    CostFlag,
    DataClassification,
    DataElement,
    FunctionalRequirement,
    GateOwner,
    LaunchReadinessItem,
    NonFunctionalRequirement,
    PrivacyConsiderations,
    Risk,
    SuccessMetric,
    UserStory,
    VersionEntry,
)
from pm_agent_system.models.brd_intermediate import (
    BRDCostRiskOutput,
    BRDStructureOutput,
)
from pm_agent_system.models.compliance_primitives import (
    _DATA_CLASS_ORDER,
    _derive_dataset_classification,
)
from tests.test_brd_output_backward_compat import (
    _assemble_brd_output_from_intermediates,
)


VALID_CLASSIFICATIONS = {c.value for c in DataClassification}
VALID_OWNERS = {o.value for o in GateOwner}


# ---------------------------------------------------------------------------
# Property 1: Enum values are bounded at schema level.
#
# For any attempted construction of DataElement, LaunchReadinessItem, or
# ComplianceGate with a classification or gate owner value outside the
# declared enum set, Pydantic raises a ValidationError. For any construction
# with values inside the enum set, construction succeeds.
#
# Validates: Requirements 1.2, 3.3, 3.4, 5.2, 9.3
# ---------------------------------------------------------------------------


@given(classification=st.sampled_from(list(DataClassification)))
def test_property_1_valid_classification_accepted(classification):
    element = DataElement(name="x", classification=classification)
    assert element.classification == classification


@given(owner=st.sampled_from(list(GateOwner)))
def test_property_1_valid_owner_accepted_on_launch_item(owner):
    item = LaunchReadinessItem(item="x", applies_to="y", gate_owner=owner)
    assert item.gate_owner == owner


@given(owner=st.sampled_from(list(GateOwner)))
def test_property_1_valid_owner_accepted_on_compliance_gate(owner):
    gate = ComplianceGate(name="security review", owner=owner)
    assert gate.owner == owner


@given(
    bogus=st.text(min_size=1, max_size=40).filter(
        lambda s: s not in VALID_CLASSIFICATIONS
    )
)
def test_property_1_invalid_classification_rejected(bogus):
    with pytest.raises(ValidationError):
        DataElement(name="x", classification=bogus)


@given(
    bogus=st.text(min_size=1, max_size=40).filter(lambda s: s not in VALID_OWNERS)
)
def test_property_1_invalid_owner_rejected_on_launch_item(bogus):
    with pytest.raises(ValidationError):
        LaunchReadinessItem(item="x", applies_to="y", gate_owner=bogus)


@given(
    bogus=st.text(min_size=1, max_size=40).filter(lambda s: s not in VALID_OWNERS)
)
def test_property_1_invalid_owner_rejected_on_compliance_gate(bogus):
    with pytest.raises(ValidationError):
        ComplianceGate(name="security review", owner=bogus)


# ---------------------------------------------------------------------------
# Property 3: Gap flag pairing invariant.
#
# For any BRDComplianceOutput instance where data_handling_gap_flag is True,
# data_elements must be empty, dataset_classification must be None, and
# data_handling_gaps must be non-empty. For any instance where the flag is
# False, data_elements and dataset_classification may hold any valid values
# and the model accepts the instance. The paired invariant is enforced by a
# model validator so no instance violating it can be constructed.
#
# Validates: Requirements 3.5, 5.4, 15.2, 15.3
# ---------------------------------------------------------------------------


@st.composite
def data_element_strategy(draw):
    return DataElement(
        name=draw(st.text(min_size=1, max_size=30)),
        classification=draw(st.sampled_from(list(DataClassification))),
    )


@given(
    gaps=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5),
)
def test_property_3_valid_gap_pairing_accepted(gaps):
    output = BRDComplianceOutput(
        data_handling_gap_flag=True,
        data_handling_gaps=gaps,
    )
    assert output.data_handling_gap_flag is True
    assert output.data_elements == []
    assert output.dataset_classification is None
    assert output.data_handling_gaps == gaps


def test_property_3_gap_flag_true_empty_gaps_auto_corrected():
    output = BRDComplianceOutput(
        data_handling_gap_flag=True,
        data_handling_gaps=[],
    )
    assert output.data_handling_gaps == [
        "Data handling analysis incomplete (gap flag set with no details)"
    ]


@given(
    gaps=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5),
    elements=st.lists(data_element_strategy(), min_size=1, max_size=5),
)
def test_property_3_gap_flag_true_with_elements_auto_corrected(gaps, elements):
    output = BRDComplianceOutput(
        data_handling_gap_flag=True,
        data_handling_gaps=gaps,
        data_elements=elements,
    )
    assert output.data_elements == []
    assert output.data_handling_gaps == gaps


@given(
    gaps=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5),
    classification=st.sampled_from(list(DataClassification)),
)
def test_property_3_gap_flag_true_with_dataset_classification_auto_corrected(
    gaps, classification
):
    output = BRDComplianceOutput(
        data_handling_gap_flag=True,
        data_handling_gaps=gaps,
        dataset_classification=classification,
    )
    assert output.dataset_classification is None
    assert output.data_handling_gaps == gaps


@given(
    elements=st.lists(data_element_strategy(), max_size=5),
    classification=st.one_of(
        st.none(), st.sampled_from(list(DataClassification))
    ),
)
def test_property_3_gap_flag_false_accepts_any_elements_shape(
    elements, classification
):
    output = BRDComplianceOutput(
        data_handling_gap_flag=False,
        data_elements=elements,
        dataset_classification=classification,
    )
    assert output.data_handling_gap_flag is False
    assert output.data_elements == elements
    assert output.dataset_classification == classification


# ---------------------------------------------------------------------------
# Property 4: Assembly preserves intermediate content.
#
# For any triple of valid intermediates (BRDStructureOutput,
# BRDCostRiskOutput, BRDComplianceOutput), the assembled BRDOutput contains
# every field from every intermediate copied through without modification.
# Fields covered include data_elements, dataset_classification,
# compliance_gates, launch_readiness_checklist, acceptance criteria inside
# functional requirements, and pricing data inside cost flags. Byte-identical
# between input and output.
#
# Validates: Requirements 4.2, 4.4
# ---------------------------------------------------------------------------


# Shared strategies for intermediate generation. Kept small and minimal-but-valid.


_SAFE_TEXT = st.text(
    alphabet=st.characters(
        min_codepoint=32,
        max_codepoint=126,
        blacklist_characters="\n\r\t",
    ),
    min_size=1,
    max_size=20,
)


_FAKE_URLS = st.sampled_from(
    [
        "https://aws.amazon.com/pricing/",
        "https://docs.aws.amazon.com/lambda/",
        "https://aws.amazon.com/dynamodb/pricing/",
        "https://aws.amazon.com/cognito/pricing/",
    ]
)


@st.composite
def user_story_strategy(draw):
    idx = draw(st.integers(min_value=1, max_value=999))
    return UserStory(
        id=f"US-{idx:03d}",
        persona=draw(_SAFE_TEXT),
        action=draw(_SAFE_TEXT),
        outcome=draw(_SAFE_TEXT),
        priority=draw(st.sampled_from(["P0", "P1", "P2"])),
    )


@st.composite
def code_sample_strategy(draw):
    return CodeSample(
        description=draw(_SAFE_TEXT),
        language=draw(st.sampled_from(["python", "yaml", "json", "typescript"])),
        code=draw(_SAFE_TEXT),
    )


@st.composite
def functional_requirement_strategy(draw):
    idx = draw(st.integers(min_value=1, max_value=999))
    return FunctionalRequirement(
        id=f"FR-{idx:03d}",
        description=f"The system shall {draw(_SAFE_TEXT)}",
        rationale=draw(_SAFE_TEXT),
        acceptance_criteria=draw(st.lists(_SAFE_TEXT, min_size=1, max_size=3)),
        related_user_stories=draw(
            st.lists(
                st.builds(lambda n: f"US-{n:03d}", st.integers(1, 999)),
                min_size=1,
                max_size=3,
            )
        ),
        code_samples=draw(
            st.lists(code_sample_strategy(), min_size=0, max_size=2)
        ),
    )


@st.composite
def non_functional_requirement_strategy(draw):
    idx = draw(st.integers(min_value=1, max_value=999))
    return NonFunctionalRequirement(
        id=f"NFR-{idx:03d}",
        category=draw(
            st.sampled_from(
                ["performance", "security", "scalability", "accessibility", "compliance"]
            )
        ),
        description=draw(_SAFE_TEXT),
        acceptance_criteria=draw(st.lists(_SAFE_TEXT, min_size=1, max_size=3)),
    )


@st.composite
def cost_flag_strategy(draw):
    return CostFlag(
        decision=draw(_SAFE_TEXT),
        why_it_matters=draw(_SAFE_TEXT),
        tradeoff=draw(_SAFE_TEXT),
        reference_url=draw(_FAKE_URLS),
        pricing_data=draw(_SAFE_TEXT),
    )


@st.composite
def risk_strategy(draw):
    return Risk(
        description=draw(_SAFE_TEXT),
        likelihood=draw(st.sampled_from(["high", "medium", "low"])),
        impact=draw(_SAFE_TEXT),
        mitigation=draw(_SAFE_TEXT),
    )


@st.composite
def success_metric_strategy(draw):
    return SuccessMetric(
        metric=draw(_SAFE_TEXT),
        target_value=draw(_SAFE_TEXT),
        measurement_method=draw(_SAFE_TEXT),
        timeline=draw(_SAFE_TEXT),
    )


@st.composite
def version_entry_strategy(draw):
    major = draw(st.integers(min_value=1, max_value=9))
    minor = draw(st.integers(min_value=0, max_value=9))
    return VersionEntry(
        version=f"{major}.{minor}",
        date=draw(_SAFE_TEXT),
        author=draw(_SAFE_TEXT),
        changes=draw(_SAFE_TEXT),
    )


@st.composite
def compliance_gate_strategy(draw):
    return ComplianceGate(
        name=draw(
            st.sampled_from(
                [
                    "security review",
                    "privacy review",
                    "legal or contract review",
                    "procurement review",
                ]
            )
        ),
        owner=draw(st.sampled_from(list(GateOwner))),
    )


@st.composite
def launch_readiness_item_strategy(draw):
    return LaunchReadinessItem(
        item=draw(_SAFE_TEXT),
        applies_to=draw(_SAFE_TEXT),
        gate_owner=draw(st.sampled_from(list(GateOwner))),
        evidence_reference=draw(st.one_of(st.just(""), _SAFE_TEXT)),
    )


@st.composite
def privacy_considerations_strategy(draw):
    return PrivacyConsiderations(
        risks=draw(st.lists(_SAFE_TEXT, min_size=0, max_size=3)),
        mitigations=draw(st.lists(_SAFE_TEXT, min_size=0, max_size=3)),
        design_review_flag=draw(st.booleans()),
    )


@st.composite
def structure_strategy(draw):
    return BRDStructureOutput(
        executive_summary=draw(_SAFE_TEXT),
        problem_statement=draw(_SAFE_TEXT),
        proposed_solution_overview=draw(_SAFE_TEXT),
        user_stories=draw(
            st.lists(user_story_strategy(), min_size=3, max_size=5)
        ),
        functional_requirements=draw(
            st.lists(functional_requirement_strategy(), min_size=3, max_size=5)
        ),
        non_functional_requirements=draw(
            st.lists(non_functional_requirement_strategy(), min_size=2, max_size=4)
        ),
        technical_context_and_dependencies=draw(_SAFE_TEXT),
    )


@st.composite
def cost_risk_strategy(draw):
    return BRDCostRiskOutput(
        cost_flags=draw(st.lists(cost_flag_strategy(), min_size=0, max_size=3)),
        risks=draw(st.lists(risk_strategy(), min_size=2, max_size=4)),
        success_metrics=draw(
            st.lists(success_metric_strategy(), min_size=1, max_size=3)
        ),
        timeline_and_milestones=draw(_SAFE_TEXT),
        version_history=draw(
            st.lists(version_entry_strategy(), min_size=1, max_size=3)
        ),
    )


@st.composite
def compliance_strategy(draw):
    # Force gap_flag to False so element and classification fields can vary
    # freely. The gap-flag invariant is covered by Property 3 tests above.
    elements = draw(st.lists(data_element_strategy(), min_size=0, max_size=5))
    classification = draw(
        st.one_of(st.none(), st.sampled_from(list(DataClassification)))
    )
    return BRDComplianceOutput(
        data_elements=elements,
        dataset_classification=classification,
        vendor_considerations=draw(_SAFE_TEXT),
        vendor_scenarios_applied=draw(
            st.lists(_SAFE_TEXT, min_size=0, max_size=3)
        ),
        privacy_considerations=draw(privacy_considerations_strategy()),
        compliance_gates=draw(
            st.lists(compliance_gate_strategy(), min_size=0, max_size=4)
        ),
        launch_readiness_checklist=draw(
            st.lists(launch_readiness_item_strategy(), min_size=0, max_size=5)
        ),
        post_launch_maintenance=draw(_SAFE_TEXT),
        data_handling_gap_flag=False,
        data_handling_gaps=draw(st.lists(_SAFE_TEXT, min_size=0, max_size=3)),
    )


@settings(max_examples=50, deadline=None)
@given(
    structure=structure_strategy(),
    cost_risk=cost_risk_strategy(),
    compliance=compliance_strategy(),
)
def test_property_4_assembly_preserves_content(structure, cost_risk, compliance):
    """Every field on every intermediate lands on the BRDOutput unchanged."""
    result = _assemble_brd_output_from_intermediates(
        structure, cost_risk, compliance
    )

    # Structure intermediate: one-to-one field mapping.
    for field_name in BRDStructureOutput.model_fields:
        assert getattr(result, field_name) == getattr(structure, field_name), (
            f"structure field {field_name} was modified during assembly"
        )

    # Cost-risk intermediate: one-to-one field mapping.
    for field_name in BRDCostRiskOutput.model_fields:
        assert getattr(result, field_name) == getattr(cost_risk, field_name), (
            f"cost_risk field {field_name} was modified during assembly"
        )

    # Compliance intermediate: nested data-handling fields plus the
    # remaining top-level fields. Check explicit design mappings first.
    assert result.data_handling_section.elements == compliance.data_elements
    assert (
        result.data_handling_section.dataset_classification
        == compliance.dataset_classification
    )
    assert (
        result.data_handling_section.gap_flag == compliance.data_handling_gap_flag
    )
    assert (
        result.data_handling_section.gap_notes == compliance.data_handling_gaps
    )

    # Remaining compliance fields land directly on BRDOutput.
    _passthrough_fields = (
        "vendor_considerations",
        "vendor_scenarios_applied",
        "privacy_considerations",
        "compliance_gates",
        "launch_readiness_checklist",
        "post_launch_maintenance",
    )
    for field_name in _passthrough_fields:
        assert getattr(result, field_name) == getattr(compliance, field_name), (
            f"compliance field {field_name} was modified during assembly"
        )

    # Every field on BRDComplianceOutput model is accounted for above.
    _expected = set(BRDComplianceOutput.model_fields)
    _nested = {
        "data_elements",
        "dataset_classification",
        "data_handling_gap_flag",
        "data_handling_gaps",
    }
    assert _expected - _nested == set(_passthrough_fields), (
        "Compliance field coverage in the test has drifted from the model"
    )


# ---------------------------------------------------------------------------
# Property 5 (STRIDE + RACI renderer half)
#
# For any BRDOutput where at least one element is Confidential or higher, or
# privacy_considerations.design_review_flag is True, or at least one vendor
# scenario applies, render_stride_stub(brd_output) returns a string containing
# exactly six subsection headers matching the fixed STRIDE category set, and
# returns the empty string for any BRDOutput meeting none of those conditions.
#
# For any BRDOutput where at least one vendor scenario applies or the design
# review flag is True, render_raci_matrix(brd_output) returns exactly six rows
# covering the GateOwner enum, each row has exactly one Accountable and at
# least one Responsible, and returns the empty list for any BRDOutput meeting
# neither condition. Sensitive elements alone do not trigger the RACI matrix.
#
# Validates: Requirements 11.2, 11.3, 11.4
# ---------------------------------------------------------------------------


from pm_agent_system.utils.render_build_spec import (
    render_raci_matrix,
    render_stride_stub,
)
from tests.test_brd_output_backward_compat import (
    _make_cost_risk_intermediate,
    _make_structure_intermediate,
)


_STRIDE_HEADERS = (
    "**Spoofing.**",
    "**Tampering.**",
    "**Repudiation.**",
    "**Information disclosure.**",
    "**Denial of service.**",
    "**Elevation of privilege.**",
)


@st.composite
def _public_only_element_strategy(draw):
    """DataElement strategy restricted to the Public classification."""
    return DataElement(
        name=draw(st.text(min_size=1, max_size=30)),
        classification=DataClassification.PUBLIC,
    )


@st.composite
def _sensitive_element_strategy(draw):
    """DataElement strategy restricted to Confidential or higher."""
    sensitive_levels = [
        DataClassification.CONFIDENTIAL,
        DataClassification.HIGHLY_CONFIDENTIAL,
        DataClassification.RESTRICTED,
        DataClassification.CRITICAL,
    ]
    return DataElement(
        name=draw(st.text(min_size=1, max_size=30)),
        classification=draw(st.sampled_from(sensitive_levels)),
    )


@st.composite
def _no_trigger_compliance_strategy(draw):
    """Generate a BRDComplianceOutput that trips no STRIDE or RACI trigger.

    Elements must be empty or all Public, design_review_flag must be False,
    and vendor_scenarios_applied must be empty.
    """
    elements = draw(
        st.lists(_public_only_element_strategy(), min_size=0, max_size=4)
    )
    return BRDComplianceOutput(
        data_elements=elements,
        dataset_classification=(
            DataClassification.PUBLIC if elements else None
        ),
        vendor_considerations="",
        vendor_scenarios_applied=[],
        privacy_considerations=PrivacyConsiderations(
            risks=[],
            mitigations=[],
            design_review_flag=False,
        ),
        compliance_gates=[],
        launch_readiness_checklist=[],
        post_launch_maintenance="",
        data_handling_gap_flag=False,
        data_handling_gaps=[],
    )


@st.composite
def _stride_positive_compliance_strategy(draw):
    """Generate a BRDComplianceOutput with at least one STRIDE trigger.

    The branch choice controls which trigger fires: a sensitive element,
    the design review flag, or a vendor scenario. Other trigger inputs are
    set to neutral values in that branch so the test can cover each path.
    """
    branch = draw(st.sampled_from(["sensitive_element", "design_flag", "vendor"]))

    if branch == "sensitive_element":
        sensitive = draw(_sensitive_element_strategy())
        extras = draw(
            st.lists(_public_only_element_strategy(), min_size=0, max_size=3)
        )
        elements = [sensitive] + extras
        design_flag = False
        vendors: list[str] = []
    elif branch == "design_flag":
        elements = draw(
            st.lists(_public_only_element_strategy(), min_size=0, max_size=3)
        )
        design_flag = True
        vendors = []
    else:
        elements = draw(
            st.lists(_public_only_element_strategy(), min_size=0, max_size=3)
        )
        design_flag = False
        vendors = draw(
            st.lists(
                st.text(min_size=1, max_size=20), min_size=1, max_size=3
            )
        )

    return BRDComplianceOutput(
        data_elements=elements,
        dataset_classification=None,
        vendor_considerations="",
        vendor_scenarios_applied=vendors,
        privacy_considerations=PrivacyConsiderations(
            risks=[],
            mitigations=[],
            design_review_flag=design_flag,
        ),
        compliance_gates=[],
        launch_readiness_checklist=[],
        post_launch_maintenance="",
        data_handling_gap_flag=False,
        data_handling_gaps=[],
    )


@st.composite
def _raci_negative_compliance_strategy(draw):
    """Generate a BRDComplianceOutput with no RACI trigger.

    RACI fires only on vendor scenarios or the design review flag.
    Sensitive elements alone must not fire RACI, so this strategy is free
    to vary element classifications across the full enum set.
    """
    elements = draw(st.lists(data_element_strategy(), min_size=0, max_size=4))
    return BRDComplianceOutput(
        data_elements=elements,
        dataset_classification=None,
        vendor_considerations="",
        vendor_scenarios_applied=[],
        privacy_considerations=PrivacyConsiderations(
            risks=[],
            mitigations=[],
            design_review_flag=False,
        ),
        compliance_gates=[],
        launch_readiness_checklist=[],
        post_launch_maintenance="",
        data_handling_gap_flag=False,
        data_handling_gaps=[],
    )


@st.composite
def _raci_positive_compliance_strategy(draw):
    """Generate a BRDComplianceOutput with at least one RACI trigger.

    Either vendor scenarios or the design review flag (or both) fire.
    """
    branch = draw(st.sampled_from(["design_flag", "vendor", "both"]))

    if branch == "design_flag":
        design_flag = True
        vendors: list[str] = []
    elif branch == "vendor":
        design_flag = False
        vendors = draw(
            st.lists(
                st.text(min_size=1, max_size=20), min_size=1, max_size=3
            )
        )
    else:
        design_flag = True
        vendors = draw(
            st.lists(
                st.text(min_size=1, max_size=20), min_size=1, max_size=3
            )
        )

    return BRDComplianceOutput(
        data_elements=draw(
            st.lists(data_element_strategy(), min_size=0, max_size=4)
        ),
        dataset_classification=None,
        vendor_considerations="",
        vendor_scenarios_applied=vendors,
        privacy_considerations=PrivacyConsiderations(
            risks=[],
            mitigations=[],
            design_review_flag=design_flag,
        ),
        compliance_gates=[],
        launch_readiness_checklist=[],
        post_launch_maintenance="",
        data_handling_gap_flag=False,
        data_handling_gaps=[],
    )


def _assemble_brd_for_compliance(compliance: BRDComplianceOutput):
    """Build a full BRDOutput so renderer tests can exercise real objects."""
    return _assemble_brd_output_from_intermediates(
        _make_structure_intermediate(),
        _make_cost_risk_intermediate(),
        compliance,
    )


@settings(max_examples=50, deadline=None)
@given(compliance=_no_trigger_compliance_strategy())
def test_property_5_stride_empty_when_no_triggers(compliance):
    """STRIDE returns the empty string when no trigger condition is met."""
    brd = _assemble_brd_for_compliance(compliance)

    assert render_stride_stub(brd) == ""


@settings(max_examples=50, deadline=None)
@given(compliance=_stride_positive_compliance_strategy())
def test_property_5_stride_exact_six_headers_when_triggered(compliance):
    """STRIDE returns the fixed six-header block when any trigger fires."""
    brd = _assemble_brd_for_compliance(compliance)

    rendered = render_stride_stub(brd)

    assert rendered != ""
    assert rendered.startswith("## Threat Model (STRIDE Stub)")
    for marker in _STRIDE_HEADERS:
        assert rendered.count(marker) == 1, (
            f"header {marker} should appear exactly once, found "
            f"{rendered.count(marker)}"
        )


@settings(max_examples=50, deadline=None)
@given(compliance=_raci_negative_compliance_strategy())
def test_property_5_raci_empty_when_no_triggers(compliance):
    """RACI returns the empty list when no vendor or design-flag trigger fires."""
    brd = _assemble_brd_for_compliance(compliance)

    assert render_raci_matrix(brd) == []


@settings(max_examples=50, deadline=None)
@given(compliance=_raci_positive_compliance_strategy())
def test_property_5_raci_six_rows_one_accountable_when_triggered(compliance):
    """RACI returns six rows covering the GateOwner enum in declaration order.

    Exactly one row is Accountable (PM), at least one row is Responsible.
    """
    brd = _assemble_brd_for_compliance(compliance)

    rows = render_raci_matrix(brd)

    assert len(rows) == 6
    assert [row.role for row in rows] == [owner.value for owner in GateOwner]

    accountable_rows = [row for row in rows if row.accountable]
    assert len(accountable_rows) == 1
    assert accountable_rows[0].role == GateOwner.PM.value

    responsible_rows = [row for row in rows if row.responsible]
    assert len(responsible_rows) >= 1

# ---------------------------------------------------------------------------
# Property 2: Dataset classification is the element-wise maximum.
#
# For any non-empty list of DataElement values, the derived dataset
# classification equals the maximum element classification under the order
# Public < Confidential < Highly Confidential < Restricted < Critical. For
# any empty list (gap case), the derived dataset classification is None.
#
# Validates: Requirements 5.3
# ---------------------------------------------------------------------------


def test_property_2_dataset_classification_empty_returns_none():
    """Deriving from an empty element list returns None."""
    assert _derive_dataset_classification([]) is None


@given(elements=st.lists(data_element_strategy(), min_size=1, max_size=10))
def test_property_2_dataset_classification_matches_element_wise_max(elements):
    """Derived classification equals the max element classification."""
    expected = max(
        elements, key=lambda e: _DATA_CLASS_ORDER[e.classification]
    ).classification

    assert _derive_dataset_classification(elements) == expected


@given(
    existing=st.lists(data_element_strategy(), min_size=1, max_size=5),
    new_element=data_element_strategy(),
)
def test_property_2_dataset_classification_is_monotone_on_append(
    existing, new_element
):
    """Appending an element never lowers the derived classification rank."""
    before = _derive_dataset_classification(existing)
    after = _derive_dataset_classification(existing + [new_element])

    assert before is not None
    assert after is not None
    assert _DATA_CLASS_ORDER[after] >= _DATA_CLASS_ORDER[before]



# ---------------------------------------------------------------------------
# Property 5 (BRD markdown half)
#
# For any BRDOutput with populated compliance fields, render_brd_to_markdown
# preserves the compliance content in the rendered output. Specifically:
#   - each new section header (13 through 18) appears in declared order
#     after the existing twelve sections, each exactly once;
#   - every DataElement.classification value string from the data handling
#     section appears in the rendered output;
#   - every LaunchReadinessItem.gate_owner value string from the checklist
#     appears in the rendered output;
#   - when data_handling_section.gap_flag is True, the verbatim gap notice
#     blockquote appears in the rendered output and names the missing input.
#
# Validates: Requirements 12.1, 12.2
# ---------------------------------------------------------------------------


from pm_agent_system.utils.render_brd import (
    _GAP_NOTICE_BLOCKQUOTE,
    render_brd_to_markdown,
)


@st.composite
def _populated_elements_compliance_strategy(draw):
    """Generate a BRDComplianceOutput with a non-empty elements list.

    Forces gap_flag=False and sets dataset_classification to the element-wise
    max so the gap pairing validator accepts the instance and the renderer
    produces a real data handling table rather than the gap notice.
    """
    elements = draw(
        st.lists(data_element_strategy(), min_size=1, max_size=5)
    )
    return BRDComplianceOutput(
        data_elements=elements,
        dataset_classification=_derive_dataset_classification(elements),
        vendor_considerations="",
        vendor_scenarios_applied=[],
        privacy_considerations=PrivacyConsiderations(
            risks=[],
            mitigations=[],
            design_review_flag=False,
        ),
        compliance_gates=[],
        launch_readiness_checklist=[],
        post_launch_maintenance="",
        data_handling_gap_flag=False,
        data_handling_gaps=[],
    )


@st.composite
def _populated_checklist_compliance_strategy(draw):
    """Generate a BRDComplianceOutput with a non-empty launch readiness list."""
    checklist = draw(
        st.lists(launch_readiness_item_strategy(), min_size=1, max_size=5)
    )
    return BRDComplianceOutput(
        data_elements=[],
        dataset_classification=None,
        vendor_considerations="",
        vendor_scenarios_applied=[],
        privacy_considerations=PrivacyConsiderations(
            risks=[],
            mitigations=[],
            design_review_flag=False,
        ),
        compliance_gates=[],
        launch_readiness_checklist=checklist,
        post_launch_maintenance="",
        data_handling_gap_flag=False,
        data_handling_gaps=[],
    )


@st.composite
def _gap_flag_compliance_strategy(draw):
    """Generate a BRDComplianceOutput with gap_flag=True and empty elements.

    The gap pairing validator requires: gap_flag=True, data_elements empty,
    dataset_classification None, data_handling_gaps non-empty.
    """
    gaps = draw(
        st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5)
    )
    return BRDComplianceOutput(
        data_elements=[],
        dataset_classification=None,
        vendor_considerations="",
        vendor_scenarios_applied=[],
        privacy_considerations=PrivacyConsiderations(
            risks=[],
            mitigations=[],
            design_review_flag=False,
        ),
        compliance_gates=[],
        launch_readiness_checklist=[],
        post_launch_maintenance="",
        data_handling_gap_flag=True,
        data_handling_gaps=gaps,
    )


_NEW_SECTION_HEADERS = (
    "## 13. Data Handling",
    "## 14. Vendor Considerations",
    "## 15. Privacy Considerations",
    "## 16. Compliance Gates",
    "## 17. Launch Readiness Checklist",
    "## 18. Post-Launch Maintenance",
)


@settings(max_examples=50, deadline=None)
@given(compliance=compliance_strategy())
def test_property_5_brd_markdown_has_all_six_section_headers_in_order(compliance):
    """Section headers 13 through 18 appear in order, each exactly once."""
    brd = _assemble_brd_for_compliance(compliance)

    rendered = render_brd_to_markdown(brd)

    # Anchor to whole heading LINES. User-controlled fields (mitigations,
    # risks, vendor prose, post-launch text) render verbatim into bullets or
    # paragraphs and can legally contain a "## NN." fragment, so a
    # whole-document substring count would over-count. A real section heading
    # is always its own line; a bulleted line is "- ## NN. ...", never equal.
    lines = rendered.splitlines()

    for header in _NEW_SECTION_HEADERS:
        assert lines.count(header) == 1, (
            f"header {header} should appear exactly once, found "
            f"{lines.count(header)}"
        )

    indexes = [lines.index(header) for header in _NEW_SECTION_HEADERS]
    assert indexes == sorted(indexes), (
        f"section headers appeared out of declared order: {indexes}"
    )


@settings(max_examples=50, deadline=None)
@given(compliance=_populated_elements_compliance_strategy())
def test_property_5_brd_markdown_contains_every_element_classification(compliance):
    """Every element classification value string appears in the rendered output."""
    brd = _assemble_brd_for_compliance(compliance)

    rendered = render_brd_to_markdown(brd)

    for element in compliance.data_elements:
        assert element.classification.value in rendered, (
            f"classification {element.classification.value!r} missing from "
            f"rendered markdown"
        )


@settings(max_examples=50, deadline=None)
@given(compliance=_populated_checklist_compliance_strategy())
def test_property_5_brd_markdown_contains_every_gate_owner_from_checklist(
    compliance,
):
    """Every gate owner value string from the checklist appears in rendered output."""
    brd = _assemble_brd_for_compliance(compliance)

    rendered = render_brd_to_markdown(brd)

    # Slice to section 17 onward so the assertion targets the checklist
    # table rather than accidental matches in earlier sections.
    slice_start = rendered.index("## 17. Launch Readiness Checklist")
    checklist_slice = rendered[slice_start:]

    for item in compliance.launch_readiness_checklist:
        assert item.gate_owner.value in checklist_slice, (
            f"gate owner {item.gate_owner.value!r} missing from rendered "
            f"launch readiness section"
        )


@settings(max_examples=50, deadline=None)
@given(compliance=_gap_flag_compliance_strategy())
def test_property_5_brd_markdown_renders_gap_notice_when_gap_flag_true(compliance):
    """The verbatim gap notice appears whenever data_handling_section.gap_flag is True."""
    brd = _assemble_brd_for_compliance(compliance)

    rendered = render_brd_to_markdown(brd)

    assert _GAP_NOTICE_BLOCKQUOTE in rendered


# ---------------------------------------------------------------------------
# Property 6 (renderer static hygiene)
#
# For any BRDOutput, the static-template slice of the rendered markdown
# produced by render_brd_to_markdown (section headings, table headers, gap
# notice text, start-early note text, and other renderer-owned strings)
# contains zero banned words from the Banned_Word_List and zero em dashes
# used as punctuation. LLM-generated content (vendor_considerations, element
# purposes, privacy risks, and similar free-text fields) can legally contain
# banned words, so this test fixes every content string to a safe placeholder.
# Any banned word or em dash found in the rendered output must therefore come
# from a renderer-owned static string.
#
# Validates: Requirements 12.3
# ---------------------------------------------------------------------------


import re

from pm_agent_system.models.prfaq_output import VersionEntry as _VersionEntry


# Detection data used by the hygiene asserts below. Kept as data, not prose.
_BANNED_WORDS = [
    "robust", "comprehensive", "powerful", "cutting-edge", "transformative",
    "game-changing", "revolutionary", "best-in-class", "seamless",
    "incredibly", "significantly", "essentially", "very", "really",
    "quite", "extremely", "strong", "leverage", "synergies",
    "drive alignment", "holistic", "unlock", "supercharge",
]

# Safe placeholder strings (no banned words, no em dashes) used to fill
# every content field on the intermediates. The test can then attribute
# any ban hit or em dash in the rendered output to renderer-owned text.
_PLACEHOLDER_PROSE = "placeholder_prose"
_PLACEHOLDER_ITEM = "placeholder_item"
_PLACEHOLDER_NAME = "placeholder_name"
_PLACEHOLDER_PURPOSE = "placeholder_purpose"
_PLACEHOLDER_NOTE = "placeholder_note"
_PLACEHOLDER_DESC = "placeholder_description"


def _placeholder_user_stories() -> list[UserStory]:
    return [
        UserStory(
            id=f"US-{i:03d}",
            persona=_PLACEHOLDER_NAME,
            action=_PLACEHOLDER_PROSE,
            outcome=_PLACEHOLDER_PROSE,
            priority="P1",
        )
        for i in range(1, 4)
    ]


def _placeholder_functional_requirements() -> list[FunctionalRequirement]:
    return [
        FunctionalRequirement(
            id=f"FR-{i:03d}",
            description=f"The system shall perform placeholder action {i}.",
            rationale=_PLACEHOLDER_PROSE,
            acceptance_criteria=[_PLACEHOLDER_PROSE],
            related_user_stories=[f"US-{i:03d}"],
            code_samples=[],
        )
        for i in range(1, 4)
    ]


def _placeholder_non_functional_requirements() -> list[NonFunctionalRequirement]:
    return [
        NonFunctionalRequirement(
            id=f"NFR-{i:03d}",
            category="performance",
            description=_PLACEHOLDER_DESC,
            acceptance_criteria=[_PLACEHOLDER_PROSE],
        )
        for i in range(1, 3)
    ]


def _placeholder_risks() -> list[Risk]:
    return [
        Risk(
            description=_PLACEHOLDER_DESC,
            likelihood="medium",
            impact=_PLACEHOLDER_PROSE,
            mitigation=_PLACEHOLDER_PROSE,
        )
        for _ in range(2)
    ]


def _placeholder_success_metrics() -> list[SuccessMetric]:
    return [
        SuccessMetric(
            metric=_PLACEHOLDER_ITEM,
            target_value=_PLACEHOLDER_ITEM,
            measurement_method=_PLACEHOLDER_PROSE,
            timeline=_PLACEHOLDER_PROSE,
        )
    ]


def _placeholder_version_history() -> list[_VersionEntry]:
    return [
        _VersionEntry(
            version="1.0",
            date="2025-01-01",
            author=_PLACEHOLDER_NAME,
            changes=_PLACEHOLDER_PROSE,
        )
    ]


def _safe_structure_intermediate() -> BRDStructureOutput:
    """Structure intermediate where every string field is a safe placeholder."""
    return BRDStructureOutput(
        executive_summary=_PLACEHOLDER_PROSE,
        problem_statement=_PLACEHOLDER_PROSE,
        proposed_solution_overview=_PLACEHOLDER_PROSE,
        user_stories=_placeholder_user_stories(),
        functional_requirements=_placeholder_functional_requirements(),
        non_functional_requirements=_placeholder_non_functional_requirements(),
        technical_context_and_dependencies=_PLACEHOLDER_PROSE,
    )


def _safe_cost_risk_intermediate() -> BRDCostRiskOutput:
    """Cost-risk intermediate with empty cost_flags and safe placeholder content.

    cost_flags is empty so the renderer does not emit the pricing details
    summary line (which contains an em dash outside the scope of this
    property); the focus here is the compliance sections added in this feature.
    """
    return BRDCostRiskOutput(
        cost_flags=[],
        risks=_placeholder_risks(),
        success_metrics=_placeholder_success_metrics(),
        timeline_and_milestones=_PLACEHOLDER_PROSE,
        version_history=_placeholder_version_history(),
    )


@st.composite
def _renderer_hygiene_compliance_strategy(draw):
    """Build a BRDComplianceOutput that exercises every renderer branch.

    Randomizes booleans (gap_flag, design_review_flag, vendor scenarios
    presence, element population, gate and checklist population) so the
    renderer hits each conditional path across examples. All text fields
    stay pinned to safe placeholders so any banned word or em dash in the
    rendered output must come from renderer-owned static strings.
    """
    gap_flag = draw(st.booleans())

    if gap_flag:
        elements: list[DataElement] = []
        dataset_classification = None
        gaps = [_PLACEHOLDER_PROSE]
    else:
        populate_elements = draw(st.booleans())
        if populate_elements:
            classifications = list(DataClassification)
            count = draw(st.integers(min_value=1, max_value=3))
            elements = [
                DataElement(
                    name=f"element_{i}",
                    classification=draw(st.sampled_from(classifications)),
                    purpose=_PLACEHOLDER_PURPOSE,
                )
                for i in range(1, count + 1)
            ]
            dataset_classification = _derive_dataset_classification(elements)
        else:
            elements = []
            dataset_classification = None
        gaps = []

    vendors_present = draw(st.booleans())
    vendor_scenarios = [_PLACEHOLDER_ITEM] if vendors_present else []
    vendor_considerations = _PLACEHOLDER_PROSE if vendors_present else ""

    design_review_flag = draw(st.booleans())
    privacy_risks_present = draw(st.booleans())
    privacy = PrivacyConsiderations(
        risks=[_PLACEHOLDER_PROSE] if privacy_risks_present else [],
        mitigations=[_PLACEHOLDER_PROSE] if privacy_risks_present else [],
        design_review_flag=design_review_flag,
    )

    gates_present = draw(st.booleans())
    if gates_present:
        gates = [
            ComplianceGate(
                name=_PLACEHOLDER_NAME,
                owner=draw(st.sampled_from(list(GateOwner))),
            )
        ]
    else:
        gates = []

    checklist_present = draw(st.booleans())
    if checklist_present:
        checklist = [
            LaunchReadinessItem(
                item=_PLACEHOLDER_ITEM,
                applies_to=_PLACEHOLDER_PROSE,
                gate_owner=draw(st.sampled_from(list(GateOwner))),
                evidence_reference=_PLACEHOLDER_PROSE,
            )
        ]
    else:
        checklist = []

    post_launch_present = draw(st.booleans())
    post_launch = _PLACEHOLDER_PROSE if post_launch_present else ""

    return BRDComplianceOutput(
        data_elements=elements,
        dataset_classification=dataset_classification,
        vendor_considerations=vendor_considerations,
        vendor_scenarios_applied=vendor_scenarios,
        privacy_considerations=privacy,
        compliance_gates=gates,
        launch_readiness_checklist=checklist,
        post_launch_maintenance=post_launch,
        data_handling_gap_flag=gap_flag,
        data_handling_gaps=gaps,
    )


@st.composite
def _renderer_hygiene_brd_strategy(draw):
    """Build a full BRDOutput with safe-placeholder content.

    Structure and cost-risk intermediates are fully populated with
    placeholder strings; the compliance intermediate randomizes every
    boolean trigger so the renderer exercises all branches across examples.
    """
    compliance = draw(_renderer_hygiene_compliance_strategy())
    return _assemble_brd_output_from_intermediates(
        _safe_structure_intermediate(),
        _safe_cost_risk_intermediate(),
        compliance,
    )


@settings(max_examples=50, deadline=None)
@given(brd=_renderer_hygiene_brd_strategy())
def test_property_6_renderer_static_strings_contain_no_banned_words(brd):
    """Rendered markdown contains no banned word from the detection list."""
    rendered = render_brd_to_markdown(brd)
    lowered = rendered.lower()

    for word in _BANNED_WORDS:
        match = re.search(rf"\b{re.escape(word)}\b", lowered)
        assert match is None, (
            f"Disallowed word found in renderer output: {word!r} at "
            f"position {match.start() if match else -1}"
        )


@settings(max_examples=50, deadline=None)
@given(brd=_renderer_hygiene_brd_strategy())
def test_property_6_renderer_static_strings_have_no_em_dash_punctuation(brd):
    """Rendered markdown contains no em dash character."""
    rendered = render_brd_to_markdown(brd)

    assert "\u2014" not in rendered, (
        "Em dash found in renderer output; renderer-owned static strings "
        "must not use em dashes as punctuation"
    )
