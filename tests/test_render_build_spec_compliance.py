"""Unit tests for deterministic STRIDE and RACI renderers.

Covers trigger logic, empty returns when no trigger condition is met, exact
STRIDE section shape (six category markers), exact RACI shape (six rows, one
Accountable, at least one Responsible, owner enum coverage), and markdown
formatting details for the RACI table.
"""

import json
from pathlib import Path

from pm_agent_system.models import DataClassification, GateOwner, RACIRow
from pm_agent_system.models.brd_output import BRDOutput
from pm_agent_system.models.compliance_primitives import DataElement
from pm_agent_system.utils.render_build_spec import (
    render_raci_matrix,
    render_raci_matrix_markdown,
    render_stride_stub,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "brd_legacy.json"

STRIDE_MARKERS = (
    "**Spoofing.**",
    "**Tampering.**",
    "**Repudiation.**",
    "**Information disclosure.**",
    "**Denial of service.**",
    "**Elevation of privilege.**",
)


def _load_legacy_brd() -> BRDOutput:
    """Load a fresh legacy BRDOutput from the fixture on each call."""
    payload = json.loads(FIXTURE_PATH.read_text())
    return BRDOutput.model_validate(payload)


# --- STRIDE stub tests ---


def test_stride_returns_empty_when_no_triggers_met():
    brd = _load_legacy_brd()

    assert render_stride_stub(brd) == ""


def test_stride_renders_when_element_confidential_or_higher():
    brd = _load_legacy_brd()
    brd.data_handling_section.elements.append(
        DataElement(name="foo", classification=DataClassification.CONFIDENTIAL)
    )

    output = render_stride_stub(brd)

    assert output != ""
    assert output.startswith("## Threat Model (STRIDE Stub)")
    for marker in STRIDE_MARKERS:
        assert marker in output


def test_stride_renders_when_design_review_flag_true():
    brd = _load_legacy_brd()
    brd.privacy_considerations.design_review_flag = True

    output = render_stride_stub(brd)

    assert output != ""
    for marker in STRIDE_MARKERS:
        assert marker in output


def test_stride_renders_when_vendor_scenario_applies():
    brd = _load_legacy_brd()
    brd.vendor_scenarios_applied = ["SaaS usage"]

    output = render_stride_stub(brd)

    assert output != ""
    for marker in STRIDE_MARKERS:
        assert marker in output


def test_stride_does_not_render_for_public_only_elements():
    brd = _load_legacy_brd()
    brd.data_handling_section.elements.extend(
        [
            DataElement(name="public_a", classification=DataClassification.PUBLIC),
            DataElement(name="public_b", classification=DataClassification.PUBLIC),
        ]
    )

    assert render_stride_stub(brd) == ""


def test_stride_output_has_no_em_dash_punctuation():
    brd = _load_legacy_brd()
    brd.privacy_considerations.design_review_flag = True

    output = render_stride_stub(brd)

    assert "\u2014" not in output


# --- RACI matrix tests ---


def test_raci_returns_empty_list_when_no_triggers_met():
    brd = _load_legacy_brd()

    assert render_raci_matrix(brd) == []


def test_raci_returns_six_rows_on_vendor_scenario():
    brd = _load_legacy_brd()
    brd.vendor_scenarios_applied = ["data handling"]

    rows = render_raci_matrix(brd)

    assert len(rows) == 6


def test_raci_returns_six_rows_on_design_review_flag():
    brd = _load_legacy_brd()
    brd.privacy_considerations.design_review_flag = True

    rows = render_raci_matrix(brd)

    assert len(rows) == 6


def test_raci_rows_cover_the_owner_enum_in_order():
    brd = _load_legacy_brd()
    brd.privacy_considerations.design_review_flag = True

    rows = render_raci_matrix(brd)

    assert [row.role for row in rows] == [owner.value for owner in GateOwner]
    assert [row.role for row in rows] == [
        "PM",
        "Tech Lead",
        "Engineer",
        "Legal",
        "Security",
        "Privacy",
    ]


def test_raci_has_exactly_one_accountable():
    brd = _load_legacy_brd()
    brd.privacy_considerations.design_review_flag = True

    rows = render_raci_matrix(brd)

    accountable_rows = [r for r in rows if r.accountable]
    assert len(accountable_rows) == 1
    assert accountable_rows[0].role == "PM"


def test_raci_has_at_least_one_responsible():
    brd = _load_legacy_brd()
    brd.privacy_considerations.design_review_flag = True

    rows = render_raci_matrix(brd)
    by_role = {row.role: row for row in rows}

    assert sum(r.responsible for r in rows) >= 1
    assert by_role["Tech Lead"].responsible is True
    assert by_role["Engineer"].responsible is True
    assert all(isinstance(r, RACIRow) for r in rows)


def test_raci_markdown_empty_on_empty_rows():
    assert render_raci_matrix_markdown([]) == ""


def _accountable_cell_marked(line: str) -> bool:
    """Return True when the line is a RACI data row with 'x' in the Accountable column."""
    if not line.startswith("| "):
        return False
    cells = [cell.strip() for cell in line.split("|")[1:-1]]
    if len(cells) != 5:
        return False
    role, _responsible, accountable, _consulted, _informed = cells
    if role in {"Role", "---"}:
        return False
    return accountable == "x"


def test_raci_markdown_format():
    brd = _load_legacy_brd()
    brd.privacy_considerations.design_review_flag = True
    rows = render_raci_matrix(brd)

    markdown = render_raci_matrix_markdown(rows)

    assert markdown.startswith("## RACI Matrix")
    assert "| Role | Responsible | Accountable | Consulted | Informed |" in markdown
    for owner in GateOwner:
        assert f"| {owner.value} |" in markdown

    accountable_marks = sum(
        1 for line in markdown.splitlines() if _accountable_cell_marked(line)
    )
    assert accountable_marks == 1


def test_raci_consulted_assignments_track_triggers():
    brd = _load_legacy_brd()
    brd.privacy_considerations.design_review_flag = True

    rows = render_raci_matrix(brd)
    by_role = {row.role: row for row in rows}

    # No vendor scenario applied, so Legal is not consulted and defaults to informed.
    assert by_role["Legal"].consulted is False
    assert by_role["Legal"].informed is True

    # Privacy design review flag means Privacy is consulted.
    assert by_role["Privacy"].consulted is True

    # design_review_flag also triggers STRIDE, so Security is consulted.
    assert by_role["Security"].consulted is True
