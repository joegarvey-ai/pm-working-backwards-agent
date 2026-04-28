"""Unit tests for the build-spec STRIDE and RACI hookup.

Covers the narrow BRD markdown parser `extract_brd_trigger_state` and the
in-place augmentation helper `_augment_spec_with_stride_raci`. Both wire
deterministic STRIDE and RACI content into `CodingPromptOutput.formatted_spec`
in the fixed order (STRIDE before RACI, both after the main body).

Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5
"""

import json
from pathlib import Path

from pm_agent_system.models import (
    CodingPromptOutput,
    DataClassification,
    DataElement,
    GateOwner,
)
from pm_agent_system.models.brd_output import BRDOutput, DataHandlingSection
from pm_agent_system.models.compliance_primitives import PrivacyConsiderations
from pm_agent_system.utils.render_brd import render_brd_to_markdown
from pm_agent_system.utils.render_build_spec import (
    _augment_spec_with_stride_raci,
    extract_brd_trigger_state,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "brd_legacy.json"


def _load_legacy_brd() -> BRDOutput:
    payload = json.loads(FIXTURE_PATH.read_text())
    return BRDOutput.model_validate(payload)


def _minimal_spec(formatted_spec: str = "main spec body") -> CodingPromptOutput:
    from pm_agent_system.models import FeatureSpec, UserFlow

    return CodingPromptOutput(
        build_summary="s",
        user_flows=[UserFlow(name="flow", steps=["step"], related_requirements=[])],
        feature_specs=[
            FeatureSpec(
                name="feat",
                description="d",
                acceptance_criteria=["ac"],
                priority="P1",
                code_samples=[],
            )
        ],
        technical_constraints=[],
        architecture_reference="a",
        current_state_context="c",
        out_of_scope=[],
        target_tool="kiro",
        formatted_spec=formatted_spec,
    )


# --- extract_brd_trigger_state tests ---


def test_extract_trigger_state_from_legacy_brd_markdown_yields_empty_triggers():
    """Legacy BRDs have no sections 13 through 15; renderers should no-op."""
    legacy_brd = _load_legacy_brd()
    markdown = render_brd_to_markdown(legacy_brd, slug="legacy")

    state = extract_brd_trigger_state(markdown)

    assert state.data_handling_section.elements == []
    assert state.vendor_scenarios_applied == []
    assert state.privacy_considerations.design_review_flag is False


def test_extract_trigger_state_parses_triggered_markdown():
    """A markdown BRD with populated sections 13-15 round-trips the three trigger signals."""
    brd_md = (
        "# BRD\n"
        "\n"
        "## 12. Version History\n"
        "\n"
        "| Version | Date | Changes |\n"
        "| --- | --- | --- |\n"
        "| 1.0 | 2026-01-01 | initial |\n"
        "\n"
        "## 13. Data Handling\n"
        "\n"
        "**Dataset Classification:** Highly Confidential\n"
        "\n"
        "| Element | Classification | Purpose |\n"
        "| --- | --- | --- |\n"
        "| User email | Confidential | Account identity |\n"
        "| Session token | Highly Confidential | API authorization |\n"
        "\n"
        "## 14. Vendor Considerations\n"
        "\n"
        "Scenarios applied: data handling, SaaS usage.\n"
        "\n"
        "## 15. Privacy Considerations\n"
        "\n"
        "**Design review flag:** true\n"
    )

    state = extract_brd_trigger_state(brd_md)

    names = [e.name for e in state.data_handling_section.elements]
    assert names == ["User email", "Session token"]
    classifications = [e.classification for e in state.data_handling_section.elements]
    assert classifications == [
        DataClassification.CONFIDENTIAL,
        DataClassification.HIGHLY_CONFIDENTIAL,
    ]
    assert state.vendor_scenarios_applied == ["data handling", "SaaS usage"]
    assert state.privacy_considerations.design_review_flag is True


def test_extract_trigger_state_handles_design_review_false():
    """When the flag line reads false, it is parsed as false."""
    brd_md = (
        "## 15. Privacy Considerations\n"
        "\n"
        "**Design review flag:** false\n"
    )

    state = extract_brd_trigger_state(brd_md)

    assert state.privacy_considerations.design_review_flag is False


# --- _augment_spec_with_stride_raci tests ---


def test_augment_with_triggered_brd_appends_stride_then_raci():
    """Triggered BRDOutput populates both fields and appends STRIDE before RACI."""
    brd = BRDOutput.model_construct(
        data_handling_section=DataHandlingSection(
            elements=[
                DataElement(
                    name="token",
                    classification=DataClassification.HIGHLY_CONFIDENTIAL,
                )
            ]
        ),
        vendor_scenarios_applied=["SaaS usage"],
        privacy_considerations=PrivacyConsiderations(design_review_flag=True),
    )
    spec = _minimal_spec(formatted_spec="main body")

    _augment_spec_with_stride_raci(spec, brd)

    assert spec.stride_stub != ""
    assert spec.stride_stub.startswith("## Threat Model (STRIDE Stub)")
    assert len(spec.raci_matrix) == 6
    # Row ordering covers the GateOwner enum in declaration order.
    roles = [row.role for row in spec.raci_matrix]
    assert roles == [o.value for o in GateOwner]

    # formatted_spec must contain STRIDE then RACI, both after the main body.
    main_idx = spec.formatted_spec.find("main body")
    stride_idx = spec.formatted_spec.find("## Threat Model (STRIDE Stub)")
    raci_idx = spec.formatted_spec.find("## RACI Matrix")

    assert main_idx == 0
    assert 0 < stride_idx < raci_idx


def test_augment_without_triggers_leaves_spec_unchanged():
    """Untriggered BRDOutput keeps fields empty and preserves formatted_spec verbatim."""
    brd = BRDOutput.model_construct(
        data_handling_section=DataHandlingSection(
            elements=[
                DataElement(name="docs", classification=DataClassification.PUBLIC)
            ]
        ),
        vendor_scenarios_applied=[],
        privacy_considerations=PrivacyConsiderations(design_review_flag=False),
    )
    original_body = "main body stays put"
    spec = _minimal_spec(formatted_spec=original_body)

    _augment_spec_with_stride_raci(spec, brd)

    assert spec.stride_stub == ""
    assert spec.raci_matrix == []
    assert spec.formatted_spec == original_body


def test_augment_on_legacy_brd_is_a_no_op():
    """A legacy BRDOutput (no compliance fields populated) triggers nothing."""
    brd = _load_legacy_brd()
    original_body = "legacy body"
    spec = _minimal_spec(formatted_spec=original_body)

    _augment_spec_with_stride_raci(spec, brd)

    assert spec.stride_stub == ""
    assert spec.raci_matrix == []
    assert spec.formatted_spec == original_body
