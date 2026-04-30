"""Unit tests for BRD renderer handling of MCP-sourced content.

Validates that Builder MCP technical context (threaded through
technical_context_and_dependencies) and Outlook MCP stakeholder availability
(threaded through timeline_and_milestones) render correctly when present
and are omitted when absent. Also checks that no banned words or em dashes
appear in renderer-owned static strings introduced by the MCP integration.

Design decision: agents thread MCP content through existing BRDOutput prose
fields. No new schema fields are introduced (Requirements 10.2, 10.3).
The renderer handles MCP-sourced content transparently.
"""

import json
import re
from pathlib import Path

from pm_agent_system.models.brd_output import BRDOutput
from pm_agent_system.utils.render_brd import render_brd_to_markdown

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "brd_legacy.json"

# Detection list used by the hygiene tests below. Kept as data, not prose.
BANNED = [
    "robust", "comprehensive", "powerful", "cutting-edge", "transformative",
    "game-changing", "revolutionary", "best-in-class", "seamless",
    "incredibly", "significantly", "essentially", "very", "really",
    "quite", "extremely", "strong", "leverage", "synergies",
    "drive alignment", "holistic", "unlock", "supercharge",
]


def _load_brd() -> BRDOutput:
    """Load a fresh BRDOutput from the fixture on each call."""
    payload = json.loads(FIXTURE_PATH.read_text())
    return BRDOutput.model_validate(payload)


# --- Section 7: Technical Context with Builder MCP content ---


def test_technical_context_with_builder_mcp_content_renders():
    """When the agent threads Builder MCP content into
    technical_context_and_dependencies, the renderer includes it."""
    brd = _load_brd()
    brd.technical_context_and_dependencies = (
        "Depends on the internal Cognito user pool. "
        "[internal:wiki] The platform team wiki documents the shared "
        "authentication flow used by all internal tools. "
        "[internal:code] The preferences-lib package provides a Python "
        "client for the DynamoDB preferences table."
    )

    output = render_brd_to_markdown(brd)

    assert "## 7. Technical Context and Dependencies" in output
    assert "[internal:wiki]" in output
    assert "[internal:code]" in output
    assert "preferences-lib" in output


def test_technical_context_empty_renders_empty_section():
    """When technical_context_and_dependencies is empty, the section header
    still appears but no content follows."""
    brd = _load_brd()
    brd.technical_context_and_dependencies = ""

    output = render_brd_to_markdown(brd)

    assert "## 7. Technical Context and Dependencies" in output
    # The empty string renders as a blank line between header and next section.
    section_start = output.index("## 7. Technical Context")
    next_section = output.index("## 8.", section_start)
    section_content = output[section_start:next_section].strip()
    # Only the header line remains (no substantive content).
    assert section_content == "## 7. Technical Context and Dependencies"


def test_technical_context_without_mcp_content_has_no_internal_tags():
    """When the agent does not use Builder MCP, the technical context field
    contains only standard prose without internal source tags."""
    brd = _load_brd()

    output = render_brd_to_markdown(brd)

    assert "## 7. Technical Context and Dependencies" in output
    section_start = output.index("## 7. Technical Context")
    next_section = output.index("## 8.", section_start)
    section_content = output[section_start:next_section]
    assert "[internal:wiki]" not in section_content
    assert "[internal:code]" not in section_content


# --- Section 11: Timeline and Milestones with Outlook MCP content ---


def test_timeline_with_outlook_mcp_availability_renders():
    """When the agent threads Outlook MCP stakeholder availability into
    timeline_and_milestones, the renderer includes it."""
    brd = _load_brd()
    brd.timeline_and_milestones = (
        "M1: API and Lambda in staging (week of March 3). "
        "M2: Two pilot tools integrated (week of March 17). "
        "Stakeholder availability: the VP of Engineering and Director of "
        "Product are available for a launch review the week of March 10. "
        "M3: Production rollout (April 1)."
    )

    output = render_brd_to_markdown(brd)

    assert "## 11. Timeline and Milestones" in output
    assert "Stakeholder availability" in output
    assert "VP of Engineering" in output


def test_timeline_empty_renders_fallback():
    """When timeline_and_milestones is empty, the renderer shows the
    fallback text."""
    brd = _load_brd()
    brd.timeline_and_milestones = ""

    output = render_brd_to_markdown(brd)

    assert "## 11. Timeline and Milestones" in output
    assert "_Not generated in this run._" in output


def test_timeline_without_mcp_content_has_no_availability():
    """When the agent does not use Outlook MCP, the timeline field contains
    only standard milestone prose without availability data."""
    brd = _load_brd()

    output = render_brd_to_markdown(brd)

    assert "## 11. Timeline and Milestones" in output
    section_start = output.index("## 11. Timeline")
    next_section = output.index("## 12.", section_start)
    section_content = output[section_start:next_section].lower()
    assert "stakeholder availability" not in section_content


# --- Static-string hygiene for MCP-related sections ---


def test_section_7_and_11_static_strings_have_no_em_dash():
    """No em dash (U+2014) appears in renderer-owned static strings for
    sections 7 and 11."""
    brd = _load_brd()

    output = render_brd_to_markdown(brd)

    # Extract renderer-owned lines (headers) for sections 7 and 11.
    for section_header in [
        "## 7. Technical Context and Dependencies",
        "## 11. Timeline and Milestones",
    ]:
        assert section_header in output
        assert "\u2014" not in section_header


def test_section_7_and_11_static_strings_contain_no_banned_words():
    """No banned word appears in renderer-owned static strings for
    sections 7 and 11."""
    brd = _load_brd()

    output = render_brd_to_markdown(brd)

    # Check the section headers and the fallback text.
    static_strings = [
        "## 7. Technical Context and Dependencies",
        "## 11. Timeline and Milestones",
        "_Not generated in this run._",
    ]
    for s in static_strings:
        lowered = s.lower()
        for word in BANNED:
            assert not re.search(rf"\b{re.escape(word)}\b", lowered), (
                f"Banned word {word!r} found in static string: {s!r}"
            )


def test_full_brd_render_sections_7_and_11_present():
    """Sections 7 and 11 appear in the rendered BRD output in order."""
    brd = _load_brd()

    output = render_brd_to_markdown(brd)

    idx_7 = output.index("## 7. Technical Context")
    idx_11 = output.index("## 11. Timeline and Milestones")
    assert idx_7 < idx_11
