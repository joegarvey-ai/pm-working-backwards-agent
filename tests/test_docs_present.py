"""Smoke tests: docs and env config mention the expected MCP keys."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(rel_path: str) -> str:
    """Read a file relative to the repo root and return its content."""
    return (ROOT / rel_path).read_text(encoding="utf-8")


# ── .env.example contains each of the five new variable names ────────

class TestEnvExampleVariables:
    """Assert .env.example documents all five MCP environment variables."""

    def setup_method(self):
        self.content = _read(".env.example")

    def test_builder_mcp_token(self):
        assert "BUILDER_MCP_TOKEN" in self.content

    def test_builder_mcp_endpoint(self):
        assert "BUILDER_MCP_ENDPOINT" in self.content

    def test_outlook_mcp_token(self):
        assert "OUTLOOK_MCP_TOKEN" in self.content

    def test_outlook_mcp_endpoint(self):
        assert "OUTLOOK_MCP_ENDPOINT" in self.content

    def test_midway_cookie_path(self):
        assert "MIDWAY_COOKIE_PATH" in self.content


# ── docs/internal-mcp-setup.md contains mwinit -f ───────────────────

class TestSetupDocContent:
    """Assert the setup guide references the cookie refresh command."""

    def setup_method(self):
        self.content = _read("docs/internal-mcp-setup.md")

    def test_mwinit_command(self):
        assert "mwinit -f" in self.content


# ── agents.yaml contains conditional MCP language per agent ──────────

class TestAgentsYamlMCPLanguage:
    """Assert each updated backstory mentions its MCP tool reference."""

    def setup_method(self):
        self.content = _read("src/pm_agent_system/config/agents.yaml")

    def test_external_research_agent_builder_mcp(self):
        # The external_research_agent backstory should reference builder_mcp
        ext_start = self.content.index("external_research_agent:")
        # Find the next top-level agent key to bound the section
        next_agent = self.content.index("\ncustomer_evidence_agent:", ext_start)
        section = self.content[ext_start:next_agent]
        assert "builder_mcp" in section

    def test_prfaq_agent_outlook_mcp(self):
        # The prfaq_agent backstory should reference outlook_mcp
        prfaq_start = self.content.index("prfaq_agent:")
        next_agent = self.content.index("\ndesign_brief_agent:", prfaq_start)
        section = self.content[prfaq_start:next_agent]
        assert "outlook_mcp" in section

    def test_brd_agent_builder_mcp(self):
        # The brd_agent backstory should reference builder_mcp
        brd_start = self.content.index("brd_agent:")
        next_agent = self.content.index("\nfeedback_classifier_agent:", brd_start)
        section = self.content[brd_start:next_agent]
        assert "builder_mcp" in section

    def test_brd_agent_outlook_mcp(self):
        # The brd_agent backstory should also reference outlook_mcp
        brd_start = self.content.index("brd_agent:")
        next_agent = self.content.index("\nfeedback_classifier_agent:", brd_start)
        section = self.content[brd_start:next_agent]
        assert "outlook_mcp" in section
