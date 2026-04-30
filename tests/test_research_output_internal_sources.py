"""Tests for the optional internal-sources schema extension (Requirement 9).

Validates that:
- Existing payloads without the new fields still validate (backward compat).
- The new fields default to empty lists.
- render_research_to_markdown renders the "Internal Sources" subsection when
  populated and omits it when empty.
"""

from pm_agent_system.models.research_intermediate import ExternalResearchOutput
from pm_agent_system.models.research_output import MarketSizing, ResearchOutput
from pm_agent_system.utils.render_markdown import render_research_to_markdown


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_market_sizing() -> MarketSizing:
    return MarketSizing(summary="$1B TAM", data_points=["point"], sources=["src"])


def _minimal_research(**overrides) -> ResearchOutput:
    defaults = dict(
        context="Test context.",
        executive_summary="Test summary.",
        market_sizing=_minimal_market_sizing(),
        strategic_implications="Test implications.",
    )
    defaults.update(overrides)
    return ResearchOutput(**defaults)


def _minimal_external_research(**overrides) -> dict:
    defaults = dict(
        market_sizing={"summary": "$1B", "data_points": ["p1"], "sources": ["s1"]},
    )
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Task 10.1 / 10.2: Schema backward compatibility
# ---------------------------------------------------------------------------

class TestExternalResearchOutputBackwardCompat:
    """ExternalResearchOutput payloads without internal_findings still validate."""

    def test_legacy_payload_without_internal_findings_validates(self):
        payload = _minimal_external_research()
        result = ExternalResearchOutput.model_validate(payload)
        assert isinstance(result, ExternalResearchOutput)

    def test_internal_findings_defaults_to_empty_list(self):
        payload = _minimal_external_research()
        result = ExternalResearchOutput.model_validate(payload)
        assert result.internal_findings == []

    def test_internal_findings_round_trips_when_provided(self):
        findings = ["Wiki: auth service design doc", "Code: auth-service repo"]
        payload = _minimal_external_research(internal_findings=findings)
        result = ExternalResearchOutput.model_validate(payload)
        assert result.internal_findings == findings

    def test_existing_fields_preserved_with_internal_findings(self):
        payload = _minimal_external_research(
            external_gaps=["gap1"],
            internal_findings=["finding1"],
        )
        result = ExternalResearchOutput.model_validate(payload)
        assert result.external_gaps == ["gap1"]
        assert result.internal_findings == ["finding1"]


class TestResearchOutputBackwardCompat:
    """ResearchOutput payloads without internal_sources still validate."""

    def test_legacy_payload_without_internal_sources_validates(self):
        result = _minimal_research()
        assert isinstance(result, ResearchOutput)

    def test_internal_sources_defaults_to_empty_list(self):
        result = _minimal_research()
        assert result.internal_sources == []

    def test_internal_sources_round_trips_when_provided(self):
        sources = ["[internal:wiki] Auth design doc", "[internal:code] auth-service"]
        result = _minimal_research(internal_sources=sources)
        assert result.internal_sources == sources

    def test_existing_fields_preserved_with_internal_sources(self):
        result = _minimal_research(
            sources=["https://example.com"],
            internal_sources=["[internal:wiki] doc"],
        )
        assert result.sources == ["https://example.com"]
        assert result.internal_sources == ["[internal:wiki] doc"]


# ---------------------------------------------------------------------------
# Task 10.3: Renderer output
# ---------------------------------------------------------------------------

class TestRenderResearchInternalSources:
    """render_research_to_markdown handles the internal_sources field."""

    def test_internal_sources_subsection_rendered_when_populated(self):
        output = _minimal_research(
            internal_sources=[
                "[internal:wiki] Auth design doc",
                "[internal:code] auth-service repo",
            ],
        )
        md = render_research_to_markdown(output)
        assert "### Internal Sources" in md
        assert "- [internal:wiki] Auth design doc" in md
        assert "- [internal:code] auth-service repo" in md

    def test_internal_sources_subsection_omitted_when_empty(self):
        output = _minimal_research(internal_sources=[])
        md = render_research_to_markdown(output)
        assert "### Internal Sources" not in md

    def test_internal_sources_subsection_omitted_when_default(self):
        output = _minimal_research()
        md = render_research_to_markdown(output)
        assert "### Internal Sources" not in md

    def test_internal_sources_appears_after_sources_section(self):
        output = _minimal_research(
            sources=["https://example.com"],
            internal_sources=["[internal:wiki] doc"],
        )
        md = render_research_to_markdown(output)
        sources_pos = md.index("## 6. Sources")
        internal_pos = md.index("### Internal Sources")
        assert internal_pos > sources_pos

    def test_public_sources_still_rendered_alongside_internal(self):
        output = _minimal_research(
            sources=["https://example.com"],
            internal_sources=["[internal:wiki] doc"],
        )
        md = render_research_to_markdown(output)
        assert "- https://example.com" in md
        assert "- [internal:wiki] doc" in md
