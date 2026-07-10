"""Smoke test: full pipeline crew builds with all MCP tokens unset.

Validates Requirement 11.6: the pipeline completes construction without
raising when all MCP tokens are unset, and no MCP tool appears in any
agent's tool list.

No LLM calls are made. The test asserts the crew object exists and tool
lists match the pre-feature baseline.
"""

from __future__ import annotations

import pytest

from pm_agent_system.crew import PmAgentSystem


@pytest.fixture(autouse=True)
def _mcp_disabled(monkeypatch):
    """Force both MCP integrations off for the whole module.

    The builder_mcp and outlook_mcp tools are gated on the presence of
    their stdio binaries on PATH (they handle Midway auth themselves), not
    on token env vars. On an Amazon host where those binaries are
    installed, deleting env vars no longer disables them, so these
    'MCP off' baseline tests must patch the enablement gates directly.
    """
    monkeypatch.setattr("pm_agent_system.crew._builder_mcp_enabled", lambda: False)
    monkeypatch.setattr("pm_agent_system.crew._outlook_mcp_enabled", lambda: False)


def _tool_class_names(agent) -> list[str]:
    """Return ``type(tool).__name__`` for every tool attached to *agent*."""
    return [type(t).__name__ for t in (agent.tools or [])]


# ---------------------------------------------------------------------------
# Baseline tool lists (pre-MCP-feature) for the three agents that may
# receive MCP tools.
# ---------------------------------------------------------------------------
_EXTERNAL_RESEARCH_BASELINE = [
    "TavilySearchTool",
    "CompetitiveIntelTool",
    "FileReaderTool",
    "PriorArtSearchTool",
    "ObsidianSearchTool",
    "ObsidianReadTool",
]

_PRFAQ_BASELINE = [
    "FileReaderTool",
    "StyleGuideLoaderTool",
    "ObsidianSearchTool",
    "ObsidianReadTool",
]

_BRD_BASELINE = [
    "TavilySearchTool",
    "AWSPricingTool",
    "AWSDocsSearchTool",
    "AWSDocsReadTool",
    "FileReaderTool",
    "RequirementsReaderTool",
    "StyleGuideLoaderTool",
    "ObsidianSearchTool",
    "ObsidianReadTool",
]

_MCP_TOOL_NAMES = {"BuilderMCPTool", "OutlookMCPTool"}


def test_full_pipeline_crew_builds_without_mcp(monkeypatch):
    """Crew construction completes without raising when all MCP tokens are unset."""
    monkeypatch.delenv("BUILDER_MCP_TOKEN", raising=False)
    monkeypatch.delenv("OUTLOOK_MCP_TOKEN", raising=False)
    monkeypatch.delenv("MIDWAY_COOKIE_PATH", raising=False)

    system = PmAgentSystem()
    crew = system.full_pipeline_crew(skip_validation=True, skip_design=True)

    assert crew is not None
    assert len(crew.tasks) > 0
    assert len(crew.agents) > 0


def test_no_mcp_tools_in_any_agent_when_tokens_unset(monkeypatch):
    """No MCP tool appears in any agent's tool list when tokens are unset."""
    monkeypatch.delenv("BUILDER_MCP_TOKEN", raising=False)
    monkeypatch.delenv("OUTLOOK_MCP_TOKEN", raising=False)
    monkeypatch.delenv("MIDWAY_COOKIE_PATH", raising=False)

    system = PmAgentSystem()
    crew = system.full_pipeline_crew(skip_validation=True, skip_design=True)

    for agent in crew.agents:
        tool_names = _tool_class_names(agent)
        mcp_found = _MCP_TOOL_NAMES & set(tool_names)
        assert not mcp_found, (
            f"Agent '{agent.role}' has MCP tools {mcp_found} "
            f"when all MCP tokens are unset"
        )


def test_external_research_agent_baseline_tools(monkeypatch):
    """external_research_agent has exactly the baseline tools when MCP is off."""
    monkeypatch.delenv("BUILDER_MCP_TOKEN", raising=False)
    monkeypatch.delenv("OUTLOOK_MCP_TOKEN", raising=False)
    monkeypatch.delenv("MIDWAY_COOKIE_PATH", raising=False)

    system = PmAgentSystem()
    agent = system.external_research_agent()
    tool_names = _tool_class_names(agent)

    assert tool_names == _EXTERNAL_RESEARCH_BASELINE, (
        f"Expected {_EXTERNAL_RESEARCH_BASELINE}, got {tool_names}"
    )


def test_prfaq_agent_baseline_tools(monkeypatch):
    """prfaq_agent has exactly the baseline tools when MCP is off."""
    monkeypatch.delenv("BUILDER_MCP_TOKEN", raising=False)
    monkeypatch.delenv("OUTLOOK_MCP_TOKEN", raising=False)
    monkeypatch.delenv("MIDWAY_COOKIE_PATH", raising=False)

    system = PmAgentSystem()
    agent = system.prfaq_agent()
    tool_names = _tool_class_names(agent)

    assert tool_names == _PRFAQ_BASELINE, (
        f"Expected {_PRFAQ_BASELINE}, got {tool_names}"
    )


def test_brd_agent_baseline_tools(monkeypatch):
    """brd_agent has exactly the baseline tools when MCP is off."""
    monkeypatch.delenv("BUILDER_MCP_TOKEN", raising=False)
    monkeypatch.delenv("OUTLOOK_MCP_TOKEN", raising=False)
    monkeypatch.delenv("MIDWAY_COOKIE_PATH", raising=False)

    system = PmAgentSystem()
    agent = system.brd_agent()
    tool_names = _tool_class_names(agent)

    assert tool_names == _BRD_BASELINE, (
        f"Expected {_BRD_BASELINE}, got {tool_names}"
    )
