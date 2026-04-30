"""Unit tests for PRFAQ renderer handling of MCP-sourced content.

Validates that Outlook MCP stakeholder scheduling context, threaded through
existing Internal FAQ entries by the agent, renders correctly when present
and is omitted when absent. Also checks that no banned words or em dashes
appear in renderer-owned static strings.

Design decision: agents thread Outlook MCP content through existing
PRFAQOutput.internal_faqs entries. No new schema fields are introduced
(Requirement 10.1). The renderer handles MCP-sourced content transparently.
"""

import json
import re
from pathlib import Path

from pm_agent_system.models import PRFAQOutput
from pm_agent_system.models.prfaq_output import FAQ
from pm_agent_system.utils.render_prfaq import render_prfaq_to_markdown

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "prfaq_with_data_handling.json"

# Detection list used by the hygiene tests below. Kept as data, not prose.
BANNED = [
    "robust", "comprehensive", "powerful", "cutting-edge", "transformative",
    "game-changing", "revolutionary", "best-in-class", "seamless",
    "incredibly", "significantly", "essentially", "very", "really",
    "quite", "extremely", "strong", "leverage", "synergies",
    "drive alignment", "holistic", "unlock", "supercharge",
]


def _load_prfaq() -> PRFAQOutput:
    """Load a fresh PRFAQOutput from the fixture on each call."""
    payload = json.loads(FIXTURE_PATH.read_text())
    return PRFAQOutput.model_validate(payload)


# --- MCP-sourced content renders through existing Internal FAQ entries ---


def test_internal_faq_with_scheduling_content_renders():
    """When an agent threads Outlook MCP scheduling context into an Internal
    FAQ entry, the renderer includes it in the Internal FAQs section."""
    prfaq = _load_prfaq()
    scheduling_faq = FAQ(
        question="What is the stakeholder availability for the launch review?",
        answer=(
            "Based on stakeholder availability data, the VP of Engineering "
            "and the Director of Product are both available the week of "
            "March 10. A 90-minute review slot is open on Wednesday March 12 "
            "from 2:00 to 3:30 PM."
        ),
        audience="internal",
    )
    prfaq.internal_faqs.append(scheduling_faq)

    output = render_prfaq_to_markdown(prfaq)

    assert "stakeholder availability" in output
    assert "March 12" in output
    assert "## Internal FAQs" in output


def test_internal_faq_without_scheduling_content_omits_scheduling():
    """When no Internal FAQ entry contains scheduling context, the rendered
    output does not mention stakeholder availability."""
    prfaq = _load_prfaq()

    output = render_prfaq_to_markdown(prfaq)

    # The fixture has no scheduling-related FAQ entries.
    assert "stakeholder availability" not in output.lower()


def test_internal_faqs_section_renders_all_entries():
    """All Internal FAQ entries render, whether MCP-sourced or not."""
    prfaq = _load_prfaq()
    original_count = len(prfaq.internal_faqs)

    output = render_prfaq_to_markdown(prfaq)

    # Each FAQ renders as a bold Q: line.
    faq_count = output.count("**Q: ")
    # external_faqs + internal_faqs
    expected = len(prfaq.external_faqs) + original_count
    assert faq_count == expected


def test_empty_internal_faqs_renders_section_header_only():
    """When internal_faqs is empty, the section header still appears but
    no FAQ entries render."""
    prfaq = _load_prfaq()
    # Clear internal_faqs directly on the loaded instance.
    prfaq.internal_faqs = []

    output = render_prfaq_to_markdown(prfaq)

    assert "## Internal FAQs" in output
    # No Q: lines in the Internal FAQs section
    internal_section_start = output.index("## Internal FAQs")
    next_section = output.index("## Customer Experience", internal_section_start)
    internal_section = output[internal_section_start:next_section]
    assert "**Q: " not in internal_section


# --- Static-string hygiene ---


def test_renderer_static_strings_have_no_em_dash_punctuation():
    """No em dash (U+2014) appears in renderer-owned static strings."""
    prfaq = _load_prfaq()

    output = render_prfaq_to_markdown(prfaq)

    # Check only the section headers and structural text, not user content.
    headers = [
        line for line in output.split("\n")
        if line.startswith("#") or line.startswith("|")
    ]
    for header in headers:
        assert "\u2014" not in header, (
            f"Em dash found in renderer static string: {header!r}"
        )


def test_renderer_static_strings_contain_no_banned_words():
    """No banned word appears in renderer-owned static strings."""
    prfaq = _load_prfaq()

    output = render_prfaq_to_markdown(prfaq)

    # Extract renderer-owned lines (headers, table markers, structural text).
    renderer_lines = [
        line for line in output.split("\n")
        if line.startswith("#") or line.startswith("|") or line.startswith("> ")
    ]
    lowered = " ".join(renderer_lines).lower()

    for word in BANNED:
        assert not re.search(rf"\b{re.escape(word)}\b", lowered), (
            f"Banned word found in renderer static strings: {word!r}"
        )
