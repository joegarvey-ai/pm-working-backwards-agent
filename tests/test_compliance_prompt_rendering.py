"""Prompt-rendering checks for the brd_compliance_task description in tasks.yaml.

Loads the YAML file directly, renders the task description with a safe
payload, and asserts style rules plus verbatim enumeration of the
classification levels, vendor scenarios, compliance gates, and gate owners
that Requirement 13 pins down.
"""

import re
from pathlib import Path

import pytest
import yaml

TASKS_YAML = (
    Path(__file__).parent.parent
    / "src"
    / "pm_agent_system"
    / "config"
    / "tasks.yaml"
)

# Safe placeholder payload. Values avoid flagged vocabulary and
# organization-internal nouns. Keys cover every placeholder present in
# the brd_compliance_task description.
PAYLOAD = {
    "feature_summary": "placeholder feature summary",
    "goals": "placeholder goals",
    "user_summary": "placeholder user summary",
    "known_constraints": "placeholder constraints",
    "business_context": "placeholder business context",
    "prfaq_path": "output/prfaq.md",
    "research_path": "output/research.md",
}

# Detection list referenced by Requirement 13.1. Used to verify that no
# occurrence appears outside the quoted enumeration of the list itself.
BANNED = [
    "robust", "comprehensive", "powerful", "cutting-edge", "transformative",
    "game-changing", "revolutionary", "best-in-class", "seamless",
    "incredibly", "significantly", "essentially", "very", "really",
    "quite", "extremely", "strong", "leverage", "synergies",
    "drive alignment", "holistic", "unlock", "supercharge",
]


@pytest.fixture(scope="module")
def rendered_description() -> str:
    with TASKS_YAML.open("r", encoding="utf-8") as handle:
        tasks = yaml.safe_load(handle)
    description = tasks["brd_compliance_task"]["description"]
    return description.format(**PAYLOAD)


def test_brd_compliance_task_description_renders(rendered_description: str):
    assert rendered_description.strip(), "rendered description should be non-empty"
    # Placeholder names must be substituted, not left as literals.
    for key, value in PAYLOAD.items():
        assert "{" + key + "}" not in rendered_description, (
            f"placeholder {{{key}}} was not substituted"
        )
        assert value in rendered_description, (
            f"substituted value for {key} not found in rendered output"
        )


def test_brd_compliance_task_prompt_enumerates_all_five_classifications(
    rendered_description: str,
):
    # Validates: Requirements 13.1
    for level in ["Public", "Confidential", "Highly Confidential", "Restricted", "Critical"]:
        assert level in rendered_description, (
            f"classification level {level!r} not enumerated in prompt"
        )


def test_brd_compliance_task_prompt_enumerates_all_seven_vendor_scenarios(
    rendered_description: str,
):
    scenarios = [
        "Data sharing",
        "Data handling",
        "Content hosting",
        "Product development",
        "Environment connection",
        "SaaS usage",
        "Endorsement or referral",
    ]
    for scenario in scenarios:
        assert scenario in rendered_description, (
            f"vendor scenario {scenario!r} not enumerated in prompt"
        )


def test_brd_compliance_task_prompt_enumerates_all_four_compliance_gates(
    rendered_description: str,
):
    gates = [
        "security review",
        "privacy review",
        "legal or contract review",
        "procurement review",
    ]
    for gate in gates:
        assert gate in rendered_description, (
            f"compliance gate {gate!r} not enumerated in prompt"
        )


def test_brd_compliance_task_prompt_enumerates_all_six_gate_owners(
    rendered_description: str,
):
    owners = ["PM", "Tech Lead", "Engineer", "Legal", "Security", "Privacy"]
    for owner in owners:
        # Word-boundary match so short tokens like PM do not collide with words.
        pattern = r"\b" + re.escape(owner) + r"\b"
        assert re.search(pattern, rendered_description), (
            f"gate owner {owner!r} not enumerated in prompt"
        )


def test_brd_compliance_task_prompt_contains_verbatim_start_early_note(
    rendered_description: str,
):
    # Validates: Requirements 13.2 (voice) and the start-early note from the design
    expected = "start early, run in parallel, do not launch with open Critical or High findings"
    assert expected in rendered_description


def test_brd_compliance_task_prompt_has_no_em_dash_punctuation(
    rendered_description: str,
):
    # Validates: Requirements 13.2
    assert "\u2014" not in rendered_description, "prompt contains an em dash character"


def test_brd_compliance_task_prompt_has_no_banned_words_outside_quoted_list(
    rendered_description: str,
):
    # Validates: Requirements 13.1
    # Strip quoted strings so the enumerated detection list does not
    # trigger its own detector.
    scrubbed = re.sub(r'"[^"]*"', '""', rendered_description).lower()
    offenders: list[str] = []
    for word in BANNED:
        pattern = r"(?<!\w)" + re.escape(word.lower()) + r"(?!\w)"
        if re.search(pattern, scrubbed):
            offenders.append(word)
    assert offenders == [], (
        f"flagged words found outside the quoted enumeration: {offenders}"
    )
