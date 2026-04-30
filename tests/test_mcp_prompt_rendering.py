"""Prompt-rendering checks for MCP tool references in agents.yaml and tasks.yaml.

Loads both YAML files, renders the updated backstories and task descriptions
with a representative payload, and asserts:
  - Zero banned words in newly added MCP blocks
  - Zero em dashes used as punctuation
  - Presence of conditional language in each of the three updated agent blocks
  - Presence of MCP tool references in each of the four updated task blocks
"""

import re
from pathlib import Path

import pytest
import yaml

CONFIG_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "pm_agent_system"
    / "config"
)

AGENTS_YAML = CONFIG_DIR / "agents.yaml"
TASKS_YAML = CONFIG_DIR / "tasks.yaml"

# Banned word list matching the project style rules.
BANNED = [
    "robust", "comprehensive", "powerful", "cutting-edge", "transformative",
    "game-changing", "revolutionary", "best-in-class", "seamless",
    "incredibly", "significantly", "essentially", "very", "really",
    "quite", "extremely", "strong", "leverage", "synergies",
    "drive alignment", "holistic", "unlock", "supercharge",
]

# Safe placeholder payload covering every template variable used in the
# task descriptions we check.
PAYLOAD = {
    "feature_summary": "placeholder feature summary",
    "goals": "placeholder goals",
    "timing": "placeholder timing",
    "user_summary": "placeholder user summary",
    "success_metrics": "placeholder success metrics",
    "known_constraints": "placeholder constraints",
    "internal_context": "placeholder internal context",
    "business_context": "placeholder business context",
    "prfaq_path": "output/prfaq.md",
    "research_path": "output/research.md",
    "design_brief_path": "output/design_brief.md",
    "requirements_path": "",
    "context_path": "",
    "context_text": "",
    "visual_style_guide_path": "",
}


@pytest.fixture(scope="module")
def agents_config() -> dict:
    with AGENTS_YAML.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def tasks_config() -> dict:
    with TASKS_YAML.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Helper: extract new MCP paragraphs from a block of text
# ---------------------------------------------------------------------------

def _extract_mcp_paragraphs(text: str) -> list[str]:
    """Return paragraphs that contain MCP conditional language.

    In YAML folded scalars, blank lines become single \\n characters.
    This function extracts from the marker to the next \\n boundary
    (or end of text).
    """
    markers = [
        "If the builder_mcp tool is available",
        "If the outlook_mcp tool is available",
        "If the ExternalResearchOutput contains internal findings",
        "If builder_mcp returns an error",
    ]
    paragraphs = []
    for marker in markers:
        idx = text.find(marker)
        if idx == -1:
            continue
        # Find the start of the line/paragraph containing the marker
        line_start = text.rfind("\n", 0, idx)
        start = line_start + 1 if line_start != -1 else 0
        # Walk forward to next newline or end of text
        end = text.find("\n", idx)
        if end == -1:
            end = len(text)
        paragraphs.append(text[start:end])
    return paragraphs


def _check_banned_words(text: str) -> list[str]:
    """Return any banned words found in text (case-insensitive, word-boundary)."""
    text_lower = text.lower()
    offenders = []
    for word in BANNED:
        pattern = r"(?<!\w)" + re.escape(word.lower()) + r"(?!\w)"
        if re.search(pattern, text_lower):
            offenders.append(word)
    return offenders


# ---------------------------------------------------------------------------
# Agent backstory tests
# ---------------------------------------------------------------------------

class TestExternalResearchAgentBackstory:
    def test_contains_builder_mcp_conditional(self, agents_config):
        backstory = agents_config["external_research_agent"]["backstory"]
        assert "if the builder_mcp tool is available" in backstory.lower(), (
            "external_research_agent backstory missing builder_mcp conditional"
        )

    def test_no_em_dashes(self, agents_config):
        backstory = agents_config["external_research_agent"]["backstory"]
        paragraphs = _extract_mcp_paragraphs(backstory)
        for p in paragraphs:
            assert "\u2014" not in p, "MCP paragraph contains an em dash"

    def test_no_banned_words_in_mcp_block(self, agents_config):
        backstory = agents_config["external_research_agent"]["backstory"]
        paragraphs = _extract_mcp_paragraphs(backstory)
        for p in paragraphs:
            offenders = _check_banned_words(p)
            assert offenders == [], f"banned words in MCP block: {offenders}"


class TestPrfaqAgentBackstory:
    def test_contains_outlook_mcp_conditional(self, agents_config):
        backstory = agents_config["prfaq_agent"]["backstory"]
        assert "if the outlook_mcp tool is available" in backstory.lower(), (
            "prfaq_agent backstory missing outlook_mcp conditional"
        )

    def test_no_em_dashes(self, agents_config):
        backstory = agents_config["prfaq_agent"]["backstory"]
        paragraphs = _extract_mcp_paragraphs(backstory)
        for p in paragraphs:
            assert "\u2014" not in p, "MCP paragraph contains an em dash"

    def test_no_banned_words_in_mcp_block(self, agents_config):
        backstory = agents_config["prfaq_agent"]["backstory"]
        paragraphs = _extract_mcp_paragraphs(backstory)
        for p in paragraphs:
            offenders = _check_banned_words(p)
            assert offenders == [], f"banned words in MCP block: {offenders}"


class TestBrdAgentBackstory:
    def test_contains_builder_mcp_conditional(self, agents_config):
        backstory = agents_config["brd_agent"]["backstory"]
        assert "if the builder_mcp tool is available" in backstory.lower(), (
            "brd_agent backstory missing builder_mcp conditional"
        )

    def test_contains_outlook_mcp_conditional(self, agents_config):
        backstory = agents_config["brd_agent"]["backstory"]
        assert "if the outlook_mcp tool is available" in backstory.lower(), (
            "brd_agent backstory missing outlook_mcp conditional"
        )

    def test_no_em_dashes(self, agents_config):
        backstory = agents_config["brd_agent"]["backstory"]
        paragraphs = _extract_mcp_paragraphs(backstory)
        for p in paragraphs:
            assert "\u2014" not in p, "MCP paragraph contains an em dash"

    def test_no_banned_words_in_mcp_block(self, agents_config):
        backstory = agents_config["brd_agent"]["backstory"]
        paragraphs = _extract_mcp_paragraphs(backstory)
        for p in paragraphs:
            offenders = _check_banned_words(p)
            assert offenders == [], f"banned words in MCP block: {offenders}"


# ---------------------------------------------------------------------------
# Task description tests
# ---------------------------------------------------------------------------

class TestExternalResearchTaskDescription:
    def test_contains_builder_mcp_reference(self, tasks_config):
        desc = tasks_config["external_research_task"]["description"]
        rendered = desc.format(**PAYLOAD)
        assert "builder_mcp" in rendered.lower(), (
            "external_research_task missing builder_mcp reference"
        )

    def test_no_em_dashes_in_mcp_block(self, tasks_config):
        desc = tasks_config["external_research_task"]["description"]
        rendered = desc.format(**PAYLOAD)
        paragraphs = _extract_mcp_paragraphs(rendered)
        for p in paragraphs:
            assert "\u2014" not in p, "MCP paragraph contains an em dash"

    def test_no_banned_words_in_mcp_block(self, tasks_config):
        desc = tasks_config["external_research_task"]["description"]
        rendered = desc.format(**PAYLOAD)
        paragraphs = _extract_mcp_paragraphs(rendered)
        for p in paragraphs:
            offenders = _check_banned_words(p)
            assert offenders == [], f"banned words in MCP block: {offenders}"


class TestResearchSynthesisTaskDescription:
    def test_contains_builder_mcp_reference(self, tasks_config):
        desc = tasks_config["research_synthesis_task"]["description"]
        rendered = desc.format(**PAYLOAD)
        assert "builder_mcp" in rendered.lower(), (
            "research_synthesis_task missing builder_mcp reference"
        )

    def test_no_em_dashes_in_mcp_block(self, tasks_config):
        desc = tasks_config["research_synthesis_task"]["description"]
        rendered = desc.format(**PAYLOAD)
        paragraphs = _extract_mcp_paragraphs(rendered)
        for p in paragraphs:
            assert "\u2014" not in p, "MCP paragraph contains an em dash"

    def test_no_banned_words_in_mcp_block(self, tasks_config):
        desc = tasks_config["research_synthesis_task"]["description"]
        rendered = desc.format(**PAYLOAD)
        paragraphs = _extract_mcp_paragraphs(rendered)
        for p in paragraphs:
            offenders = _check_banned_words(p)
            assert offenders == [], f"banned words in MCP block: {offenders}"


class TestGeneratePrfaqTaskDescription:
    def test_contains_outlook_mcp_reference(self, tasks_config):
        desc = tasks_config["generate_prfaq"]["description"]
        rendered = desc.format(**PAYLOAD)
        assert "outlook_mcp" in rendered.lower(), (
            "generate_prfaq missing outlook_mcp reference"
        )

    def test_no_em_dashes_in_mcp_block(self, tasks_config):
        desc = tasks_config["generate_prfaq"]["description"]
        rendered = desc.format(**PAYLOAD)
        paragraphs = _extract_mcp_paragraphs(rendered)
        for p in paragraphs:
            assert "\u2014" not in p, "MCP paragraph contains an em dash"

    def test_no_banned_words_in_mcp_block(self, tasks_config):
        desc = tasks_config["generate_prfaq"]["description"]
        rendered = desc.format(**PAYLOAD)
        paragraphs = _extract_mcp_paragraphs(rendered)
        for p in paragraphs:
            offenders = _check_banned_words(p)
            assert offenders == [], f"banned words in MCP block: {offenders}"


class TestBrdStructureTaskDescription:
    def test_contains_builder_mcp_reference(self, tasks_config):
        desc = tasks_config["brd_structure_task"]["description"]
        rendered = desc.format(**PAYLOAD)
        assert "builder_mcp" in rendered.lower(), (
            "brd_structure_task missing builder_mcp reference"
        )

    def test_contains_outlook_mcp_reference(self, tasks_config):
        desc = tasks_config["brd_structure_task"]["description"]
        rendered = desc.format(**PAYLOAD)
        assert "outlook_mcp" in rendered.lower(), (
            "brd_structure_task missing outlook_mcp reference"
        )

    def test_no_em_dashes_in_mcp_block(self, tasks_config):
        desc = tasks_config["brd_structure_task"]["description"]
        rendered = desc.format(**PAYLOAD)
        paragraphs = _extract_mcp_paragraphs(rendered)
        for p in paragraphs:
            assert "\u2014" not in p, "MCP paragraph contains an em dash"

    def test_no_banned_words_in_mcp_block(self, tasks_config):
        desc = tasks_config["brd_structure_task"]["description"]
        rendered = desc.format(**PAYLOAD)
        paragraphs = _extract_mcp_paragraphs(rendered)
        for p in paragraphs:
            offenders = _check_banned_words(p)
            assert offenders == [], f"banned words in MCP block: {offenders}"


class TestGenerateBrdStandaloneTaskDescription:
    def test_contains_builder_mcp_reference(self, tasks_config):
        desc = tasks_config["generate_brd_standalone"]["description"]
        rendered = desc.format(**PAYLOAD)
        assert "builder_mcp" in rendered.lower(), (
            "generate_brd_standalone missing builder_mcp reference"
        )

    def test_contains_outlook_mcp_reference(self, tasks_config):
        desc = tasks_config["generate_brd_standalone"]["description"]
        rendered = desc.format(**PAYLOAD)
        assert "outlook_mcp" in rendered.lower(), (
            "generate_brd_standalone missing outlook_mcp reference"
        )

    def test_no_em_dashes_in_mcp_block(self, tasks_config):
        desc = tasks_config["generate_brd_standalone"]["description"]
        rendered = desc.format(**PAYLOAD)
        paragraphs = _extract_mcp_paragraphs(rendered)
        for p in paragraphs:
            assert "\u2014" not in p, "MCP paragraph contains an em dash"

    def test_no_banned_words_in_mcp_block(self, tasks_config):
        desc = tasks_config["generate_brd_standalone"]["description"]
        rendered = desc.format(**PAYLOAD)
        paragraphs = _extract_mcp_paragraphs(rendered)
        for p in paragraphs:
            offenders = _check_banned_words(p)
            assert offenders == [], f"banned words in MCP block: {offenders}"
