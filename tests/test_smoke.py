"""Smoke test: confirm the project imports and crews instantiate."""


def test_import():
    """The main module should import without errors."""
    from pm_agent_system.crew import PmAgentSystem
    assert PmAgentSystem is not None


def test_models_import():
    """All Pydantic models should import without errors."""
    from pm_agent_system.models import ResearchOutput, PRFAQOutput, BRDOutput, CodingPromptOutput
    assert ResearchOutput is not None
    assert PRFAQOutput is not None
    assert BRDOutput is not None
    assert CodingPromptOutput is not None
