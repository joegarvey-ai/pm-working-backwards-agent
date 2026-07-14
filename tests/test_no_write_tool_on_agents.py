"""Safety guard: no write-back capability is ever attached to an agent.

Audit item #19's central design rule: publishing to Quip, creating Taskei
tasks, and ingesting Slack feedback are HUMAN actions invoked from the CLI
after the PM approves an artifact — never autonomous agent actions. This test
enforces that rule structurally, so a future change that (say) turns a write
helper into a BaseTool and attaches it to an agent fails CI.

Two layers of defense are asserted:
1. The write-back modules expose NO CrewAI BaseTool subclass — there is no
   write *tool* that could be attached in the first place.
2. Building every crew (with all optional MCP integrations forced ON) and
   enumerating every agent shows no tool whose class or module is related to
   write-back.
"""

from __future__ import annotations

import inspect

import pytest
from crewai.tools import BaseTool

from pm_agent_system.crew import PmAgentSystem


# Substrings that would betray a write capability leaking onto an agent.
_FORBIDDEN_TOOL_SUBSTRINGS = ("write_back", "writeback", "publish", "taskeicreate", "seed_taskei", "ingest")


# Every @agent-decorated builder on the crew class. Enumerated explicitly (not
# discovered) so that adding a new agent without updating this list is a
# visible omission — and so a typo can't silently reduce coverage to zero.
_AGENT_METHODS = [
    "research_agent",
    "external_research_agent",
    "customer_evidence_agent",
    "prfaq_agent",
    "design_brief_agent",
    "brd_agent",
    "brd_cost_risk_agent",
    "brd_compliance_agent",
    "brd_assembly_agent",
    "feedback_classifier_agent",
]


def _all_agents(system: PmAgentSystem):
    """Instantiate every agent-builder method on the crew class."""
    agents = []
    for name in _AGENT_METHODS:
        method = getattr(system, name, None)
        assert method is not None, (
            f"Agent builder '{name}' not found on PmAgentSystem — update "
            f"_AGENT_METHODS if the crew's agents changed."
        )
        agents.append((name, method()))
    return agents


@pytest.fixture
def all_mcp_enabled(monkeypatch):
    """Force every optional MCP integration ON so any write tool would surface.

    The write helpers gate on the builder-mcp/slack-mcp binaries, exactly like
    the read tools. Forcing the enable predicates True guarantees that if a
    write tool were (incorrectly) attached behind one of those gates, it would
    appear in the agent's tool list here. The Part B read integrations are
    included so their (legitimately agent-attached) read tools are enumerated
    too — the guard confirms none of them trips a write substring.
    """
    for pred in (
        "_builder_mcp_enabled",
        "_outlook_mcp_enabled",
        "_wb_ai_enabled",
        "_software_catalog_enabled",
        "_quicksight_enabled",
        "_pippin_enabled",
        "_virtual_pm_enabled",
    ):
        monkeypatch.setattr(f"pm_agent_system.crew.{pred}", lambda: True, raising=False)
    monkeypatch.setenv("DOVETAIL_API_TOKEN", "test-token")


class TestNoWriteToolClass:
    def test_write_back_module_exposes_no_basetool(self):
        import pm_agent_system.tools.write_back as wb

        tool_classes = [
            obj for _, obj in inspect.getmembers(wb, inspect.isclass)
            if issubclass(obj, BaseTool) and obj is not BaseTool
        ]
        assert tool_classes == [], (
            f"write_back.py must expose NO CrewAI BaseTool (writes are human CLI "
            f"actions, not agent tools); found: {tool_classes}"
        )

    def test_feedback_ingest_module_exposes_no_basetool(self):
        import pm_agent_system.feedback_ingest as fi

        tool_classes = [
            obj for _, obj in inspect.getmembers(fi, inspect.isclass)
            if issubclass(obj, BaseTool) and obj is not BaseTool
        ]
        assert tool_classes == []

    def test_write_back_not_re_exported_from_tools_package(self):
        import pm_agent_system.tools as tools_pkg

        assert not hasattr(tools_pkg, "WriteBackTool")
        # Nothing in the tools package __all__ references write-back.
        for name in getattr(tools_pkg, "__all__", []):
            assert "write" not in name.lower() and "publish" not in name.lower()


class TestNoWriteToolOnAnyAgent:
    def test_no_agent_carries_a_write_tool(self, all_mcp_enabled):
        system = PmAgentSystem()
        agents = _all_agents(system)
        assert agents, "Expected to build at least one agent"

        for agent_name, agent in agents:
            for tool in (agent.tools or []):
                cls_name = type(tool).__name__.lower()
                module = (type(tool).__module__ or "").lower()
                tool_name = (getattr(tool, "name", "") or "").lower()
                blob = f"{cls_name} {module} {tool_name}"
                for bad in _FORBIDDEN_TOOL_SUBSTRINGS:
                    assert bad not in blob, (
                        f"Agent '{agent_name}' carries a tool that looks like a "
                        f"write capability ({bad!r} in {blob!r}). Writes must be "
                        f"human-invoked CLI actions, never agent tools."
                    )

    def test_full_pipeline_crew_builds_without_write_tools(self, all_mcp_enabled):
        system = PmAgentSystem()
        crew = system.full_pipeline_crew()
        for agent in crew.agents:
            for tool in (agent.tools or []):
                module = (type(tool).__module__ or "").lower()
                assert "write_back" not in module
                assert "feedback_ingest" not in module
