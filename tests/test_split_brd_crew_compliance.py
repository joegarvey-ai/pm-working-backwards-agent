"""Structural integration tests for the split BRD crew compliance sibling.

These tests verify crew wiring and environment-variable handling for the
compliance-aware BRD workstream without invoking live LLM calls. They exist
because a full crew kickoff against a real Anthropic or Bedrock backend is
slow, costly, and unsuitable for CI. Instead, we validate:

* The ``split_brd_crew`` is configured with the expected agents, tasks, async
  flags, output schemas, and context wiring.
* The ``brd_compliance_agent`` factory responds correctly to ``TAVILY_API_KEY``
  and ``DOVETAIL_API_TOKEN`` environment variables.
* The deterministic three-way assembly oracle from
  ``tests/test_brd_output_backward_compat.py`` produces a ``BRDOutput`` whose
  compliance-related fields carry through the way the LLM-driven assembly task
  is instructed to produce them.
* Gap-handling surfaces the rendered blockquote notice in the markdown
  renderer output when the compliance sibling reports a gap.

No test in this module calls ``crew.kickoff``; each test only instantiates the
crew or the agent factory.
"""

from pm_agent_system.crew import PmAgentSystem
from pm_agent_system.models import (
    BRDComplianceOutput,
    BRDOutput,
)
from pm_agent_system.utils.render_brd import (
    _GAP_NOTICE_BLOCKQUOTE,
    render_brd_to_markdown,
)

from tests.test_brd_output_backward_compat import (
    _assemble_brd_output_from_intermediates,
    _make_compliance_intermediate,
    _make_cost_risk_intermediate,
    _make_structure_intermediate,
)


def _tool_class_names(agent) -> list[str]:
    """Return the ``type(tool).__name__`` for every tool attached to an agent."""
    return [type(tool).__name__ for tool in (agent.tools or [])]


def test_split_brd_crew_wires_compliance_sibling_correctly():
    """The split BRD crew runs three async siblings feeding the assembly task.

    Validates Requirements 2.5, 4.2, and 16.3 by asserting the crew structure
    and then exercising the deterministic assembly oracle to confirm that a
    populated ``BRDComplianceOutput`` produces a ``BRDOutput`` with the three
    compliance-derived fields populated.
    """
    system = PmAgentSystem()
    crew = system.split_brd_crew()

    # Exactly four tasks in this crew: three siblings plus assembly.
    assert len(crew.tasks) == 4

    tasks_by_name = {task.name: task for task in crew.tasks}
    assert set(tasks_by_name) == {
        "brd_structure_task",
        "brd_cost_risk_task",
        "brd_compliance_task",
        "brd_assembly_task",
    }

    structure_task = tasks_by_name["brd_structure_task"]
    cost_risk_task = tasks_by_name["brd_cost_risk_task"]
    compliance_task = tasks_by_name["brd_compliance_task"]
    assembly_task = tasks_by_name["brd_assembly_task"]

    # Three siblings all run async; assembly runs after them.
    assert structure_task.async_execution is True
    assert cost_risk_task.async_execution is True
    assert compliance_task.async_execution is True
    assert not assembly_task.async_execution

    # Compliance task uses the dedicated output schema.
    assert compliance_task.output_pydantic is BRDComplianceOutput

    # Compliance task has a compliance-focused agent attached.
    assert compliance_task.agent is not None
    assert "compliance" in compliance_task.agent.role.lower()

    # Assembly task waits on all three siblings.
    assembly_context = assembly_task.context or []
    assert structure_task in assembly_context
    assert cost_risk_task in assembly_context
    assert compliance_task in assembly_context

    # Crew agent list contains the three specialists plus the assembly agent.
    agent_roles = [agent.role.lower() for agent in crew.agents]
    assert len(crew.agents) == 4
    assert any("compliance" in role for role in agent_roles)
    assert any("cost" in role or "risk" in role for role in agent_roles)
    assert any("assembly" in role for role in agent_roles)

    # End-to-end proxy: populated intermediates assemble into a BRDOutput
    # with populated data handling, compliance gates, and launch readiness.
    structure = _make_structure_intermediate()
    cost_risk = _make_cost_risk_intermediate()
    compliance = _make_compliance_intermediate()

    brd_output = _assemble_brd_output_from_intermediates(
        structure, cost_risk, compliance
    )

    assert isinstance(brd_output, BRDOutput)
    assert brd_output.data_handling_section.elements, (
        "expected populated data elements when the PRFAQ includes data handling"
    )
    assert brd_output.compliance_gates, "expected populated compliance gates"
    assert brd_output.launch_readiness_checklist, (
        "expected populated launch readiness checklist"
    )


def test_split_brd_crew_preserves_gap_flag_end_to_end():
    """When the compliance sibling flags a gap the rendered BRD shows the notice.

    Validates Requirements 5.4, 15.2, and 16.4 by constructing a
    ``BRDComplianceOutput`` in its gap-flag state, assembling into a
    ``BRDOutput``, and rendering to markdown. The rendered output must carry
    the verbatim gap-notice blockquote and the data-handling section must be
    empty.
    """
    structure = _make_structure_intermediate()
    cost_risk = _make_cost_risk_intermediate()
    compliance = BRDComplianceOutput(
        data_elements=[],
        dataset_classification=None,
        vendor_considerations="No third party is involved.",
        vendor_scenarios_applied=[],
        compliance_gates=[],
        launch_readiness_checklist=[],
        post_launch_maintenance="",
        data_handling_gap_flag=True,
        data_handling_gaps=["PRFAQ lacked a data handling section"],
    )

    brd_output = _assemble_brd_output_from_intermediates(
        structure, cost_risk, compliance
    )

    assert brd_output.data_handling_section.gap_flag is True
    assert brd_output.data_handling_section.elements == []
    assert brd_output.data_handling_section.dataset_classification is None

    rendered = render_brd_to_markdown(brd_output)
    assert _GAP_NOTICE_BLOCKQUOTE in rendered


def test_brd_compliance_agent_unaffected_by_dovetail_api_token_unset(monkeypatch):
    """``DOVETAIL_API_TOKEN`` unset does not break the compliance agent.

    Validates Requirements 15.1 and 16.5 by confirming the compliance agent
    instantiates without Dovetail credentials and does not carry a Dovetail
    tool. The agent factory must still attach ``FileReaderTool`` so it can
    read the PRFAQ from disk.
    """
    monkeypatch.delenv("DOVETAIL_API_TOKEN", raising=False)

    system = PmAgentSystem()
    agent = system.brd_compliance_agent()

    tool_names = _tool_class_names(agent)
    assert "FileReaderTool" in tool_names
    assert not any("Dovetail" in name for name in tool_names), (
        f"compliance agent should not carry a Dovetail tool, got {tool_names}"
    )


def test_brd_compliance_agent_excludes_tavily_when_key_unset(monkeypatch):
    """Tavily is attached only when ``TAVILY_API_KEY`` is present.

    Validates Requirements 7.4 and 15.4 by confirming that the compliance
    agent omits ``TavilySearchTool`` when no API key is set (so attempted
    regulation lookups would be recorded as gaps by the task rules) and that
    the tool reappears once the key is provided.
    """
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    system_without_key = PmAgentSystem()
    agent_without_key = system_without_key.brd_compliance_agent()

    tool_names_without = _tool_class_names(agent_without_key)
    assert "FileReaderTool" in tool_names_without
    assert "TavilySearchTool" not in tool_names_without, (
        f"Tavily should be excluded when TAVILY_API_KEY is unset, got {tool_names_without}"
    )

    monkeypatch.setenv("TAVILY_API_KEY", "fake-key-for-test")

    system_with_key = PmAgentSystem()
    agent_with_key = system_with_key.brd_compliance_agent()

    tool_names_with = _tool_class_names(agent_with_key)
    assert "FileReaderTool" in tool_names_with
    assert "TavilySearchTool" in tool_names_with, (
        f"Tavily should be attached when TAVILY_API_KEY is set, got {tool_names_with}"
    )


def test_brd_assembly_agent_has_no_tools():
    """Requirement 17.1: the no-tools brd_assembly_agent carries an empty tool list."""
    system = PmAgentSystem()
    agent = system.brd_assembly_agent()

    tools = agent.tools or []
    assert tools == [], (
        f"brd_assembly_agent must have zero tools, got {[type(t).__name__ for t in tools]}"
    )
    assert "assembly" in agent.role.lower()


def test_split_brd_crew_uses_assembly_agent_on_assembly_task():
    """Requirement 17.2: the assembly task is attached to brd_assembly_agent."""
    system = PmAgentSystem()
    crew = system.split_brd_crew()

    tasks_by_name = {task.name: task for task in crew.tasks}
    assembly_task = tasks_by_name["brd_assembly_task"]

    assert assembly_task.agent is not None
    assert "assembly" in assembly_task.agent.role.lower()
    assert (assembly_task.agent.tools or []) == []
