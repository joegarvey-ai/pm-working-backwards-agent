"""Unit tests for BRD markdown renderer coverage of compliance sections 13-18.

Covers section ordering, the gap notice blockquote when ``gap_flag`` is True,
the verbatim start-early note for compliance gates, launch readiness table
headers, and static-string hygiene in the renderer output produced by
``render_brd_to_markdown``. The word list below is test data used to detect
prohibited prose in renderer-owned static strings; it is not prose itself.
"""

import json
import re
from pathlib import Path

from pm_agent_system.models import (
    ComplianceGate,
    DataClassification,
    DataElement,
    GateOwner,
    LaunchReadinessItem,
)
from pm_agent_system.models.brd_output import BRDOutput
from pm_agent_system.utils.render_brd import (
    _GAP_NOTICE_BLOCKQUOTE,
    render_brd_to_markdown,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "brd_legacy.json"

# Detection list used by the hygiene tests below. Kept as data, not prose.
BANNED = [
    "robust", "comprehensive", "powerful", "cutting-edge", "transformative",
    "game-changing", "revolutionary", "best-in-class", "seamless",
    "incredibly", "significantly", "essentially", "very", "really",
    "quite", "extremely", "strong", "leverage", "synergies",
    "drive alignment", "holistic", "unlock", "supercharge",
]


def _load_legacy_brd() -> BRDOutput:
    """Load a fresh legacy BRDOutput from the fixture on each call."""
    payload = json.loads(FIXTURE_PATH.read_text())
    return BRDOutput.model_validate(payload)


# --- Section order ---


def test_sections_13_through_18_appear_in_order():
    brd = _load_legacy_brd()

    output = render_brd_to_markdown(brd)

    headers = [
        "## 13.",
        "## 14.",
        "## 15.",
        "## 16.",
        "## 17.",
        "## 18.",
    ]
    indexes = [output.index(h) for h in headers]
    assert indexes == sorted(indexes)
    assert all(idx >= 0 for idx in indexes)


def test_sections_13_through_18_appear_after_version_history():
    brd = _load_legacy_brd()

    output = render_brd_to_markdown(brd)

    assert output.index("## 12. Version History") < output.index("## 13. Data Handling")


# --- Section 13: Data Handling ---


def test_section_13_renders_gap_notice_when_flag_true():
    brd = _load_legacy_brd()
    brd.data_handling_section.gap_flag = True
    brd.data_handling_section.gap_notes = ["reason"]

    output = render_brd_to_markdown(brd)

    assert _GAP_NOTICE_BLOCKQUOTE in output
    assert "| Element | Classification | Purpose |" not in output
    assert "**Dataset Classification:**" not in output


def test_section_13_renders_elements_and_classification_when_populated():
    brd = _load_legacy_brd()
    brd.data_handling_section.elements = [
        DataElement(
            name="public_element",
            classification=DataClassification.PUBLIC,
            purpose="marketing copy",
        ),
        DataElement(
            name="sensitive_element",
            classification=DataClassification.HIGHLY_CONFIDENTIAL,
            purpose="user identifier",
        ),
    ]
    brd.data_handling_section.dataset_classification = (
        DataClassification.HIGHLY_CONFIDENTIAL
    )

    output = render_brd_to_markdown(brd)

    assert "**Dataset Classification:** Highly Confidential" in output
    assert "| Element | Classification | Purpose |" in output
    assert "public_element" in output
    assert "sensitive_element" in output
    assert _GAP_NOTICE_BLOCKQUOTE not in output


def test_section_13_renders_not_specified_when_no_classification():
    brd = _load_legacy_brd()

    output = render_brd_to_markdown(brd)

    assert "**Dataset Classification:** Not specified" in output


# --- Section 14: Vendor Considerations ---


def test_section_14_renders_no_third_party_fallback_when_no_scenarios():
    brd = _load_legacy_brd()

    output = render_brd_to_markdown(brd)

    assert (
        "No third party is involved in this product. Vendor review, "
        "contract review, and procurement review are not required."
    ) in output


def test_section_14_renders_scenarios_and_prose_when_populated():
    brd = _load_legacy_brd()
    brd.vendor_scenarios_applied = ["data handling", "SaaS usage"]
    brd.vendor_considerations = "Generic vendor context text."

    output = render_brd_to_markdown(brd)

    assert "Scenarios applied: data handling, SaaS usage." in output
    assert "Generic vendor context text." in output
    assert (
        "No third party is involved in this product. Vendor review, "
        "contract review, and procurement review are not required."
    ) not in output


# --- Section 15: Privacy Considerations ---


def test_section_15_renders_design_review_flag_false_by_default():
    brd = _load_legacy_brd()

    output = render_brd_to_markdown(brd)

    assert "**Design review flag:** false" in output


def test_section_15_renders_design_review_flag_true_when_set():
    brd = _load_legacy_brd()
    brd.privacy_considerations.design_review_flag = True

    output = render_brd_to_markdown(brd)

    assert "**Design review flag:** true" in output


def test_section_15_renders_none_recorded_fallback_when_risks_and_mitigations_empty():
    brd = _load_legacy_brd()

    output = render_brd_to_markdown(brd)

    assert output.count("- None recorded.") == 2


# --- Section 16: Compliance Gates ---


def test_section_16_renders_no_gates_fallback_when_empty():
    brd = _load_legacy_brd()

    output = render_brd_to_markdown(brd)

    assert "No compliance gates recorded." in output


def test_section_16_renders_start_early_note_verbatim():
    brd = _load_legacy_brd()
    brd.compliance_gates = [
        ComplianceGate(name="security review", owner=GateOwner.SECURITY)
    ]

    output = render_brd_to_markdown(brd)

    assert (
        "start early, run in parallel, do not launch with open "
        "Critical or High findings"
    ) in output


# --- Section 17: Launch Readiness Checklist ---


def test_section_17_renders_no_items_fallback_when_empty():
    brd = _load_legacy_brd()

    output = render_brd_to_markdown(brd)

    assert "No launch readiness items recorded." in output


def test_section_17_renders_markdown_table_headers_when_items_present():
    brd = _load_legacy_brd()
    brd.launch_readiness_checklist = [
        LaunchReadinessItem(
            item="Threat model review",
            applies_to="All services handling user data",
            gate_owner=GateOwner.SECURITY,
            evidence_reference="",
        )
    ]

    output = render_brd_to_markdown(brd)

    assert "| Item | Applies To | Gate Owner | Evidence Reference |" in output


# --- Section 18: Post-Launch Maintenance ---


def test_section_18_renders_fallback_when_text_empty():
    brd = _load_legacy_brd()

    output = render_brd_to_markdown(brd)

    assert "No post-launch maintenance guidance recorded." in output


def test_section_18_renders_text_verbatim_when_set():
    brd = _load_legacy_brd()
    brd.post_launch_maintenance = (
        "Recertify annually. Update data classifications when sources change."
    )

    output = render_brd_to_markdown(brd)

    assert (
        "Recertify annually. Update data classifications when sources change."
        in output
    )


# --- Static-string hygiene (applies to renderer-owned text only) ---


def test_new_section_static_strings_have_no_em_dash_punctuation():
    brd = _load_legacy_brd()

    output = render_brd_to_markdown(brd)
    slice_start = output.index("## 13. Data Handling")
    new_sections = output[slice_start:]

    assert "\u2014" not in new_sections


def test_new_section_static_strings_contain_no_banned_words():
    brd = _load_legacy_brd()

    output = render_brd_to_markdown(brd)
    slice_start = output.index("## 13.")
    lowered = output[slice_start:].lower()

    for word in BANNED:
        assert not re.search(rf"\b{re.escape(word)}\b", lowered), (
            f"Disallowed word found in renderer static strings: {word!r}"
        )
