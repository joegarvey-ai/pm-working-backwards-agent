"""Tests for the BRD functional-requirement markdown parser.

The parser recovers functional requirements from a *rendered* BRD markdown
file (no structured BRDOutput is persisted to disk). To guarantee the parser
tracks whatever the renderer emits, the primary test round-trips a constructed
BRDOutput through the real ``render_brd_to_markdown`` and asserts the parser
recovers every FR faithfully. If the renderer's FR format ever changes, this
test fails — exactly the coupling we want.
"""

from __future__ import annotations

from pm_agent_system.brd_fr_parser import (
    parse_brd_file,
    parse_functional_requirements,
)
from pm_agent_system.models.brd_output import (
    BRDOutput,
    FunctionalRequirement,
    NonFunctionalRequirement,
    Risk,
    SuccessMetric,
    UserStory,
)
from pm_agent_system.models.prfaq_output import VersionEntry
from pm_agent_system.utils import render_brd_to_markdown


def _minimal_brd(frs: list[FunctionalRequirement]) -> BRDOutput:
    """Construct a schema-valid BRDOutput with the given FRs."""
    return BRDOutput(
        executive_summary="Exec summary.",
        problem_statement="Problem.",
        proposed_solution_overview="Solution.\n\n```mermaid\ngraph TD\nA-->B\n```",
        user_stories=[
            UserStory(id="US-001", persona="PM", action="do a thing", outcome="win", priority="P0"),
            UserStory(id="US-002", persona="dev", action="build a thing", outcome="ship", priority="P1"),
            UserStory(id="US-003", persona="ops", action="run a thing", outcome="uptime", priority="P2"),
        ],
        functional_requirements=frs,
        non_functional_requirements=[
            NonFunctionalRequirement(id="NFR-001", category="performance", description="fast", acceptance_criteria=["p99 < 100ms"]),
            NonFunctionalRequirement(id="NFR-002", category="security", description="safe", acceptance_criteria=["encrypted at rest"]),
        ],
        risks=[
            Risk(description="risk one", likelihood="low", impact="minor", mitigation="watch"),
            Risk(description="risk two", likelihood="high", impact="major", mitigation="plan"),
        ],
        success_metrics=[
            SuccessMetric(metric="adoption", target_value="50%", measurement_method="CloudWatch", timeline="Q3"),
        ],
        version_history=[VersionEntry(version="1.0", date="2026-07-13", author="agent", changes="initial")],
    )


def _fr(id_, desc, **kw) -> FunctionalRequirement:
    return FunctionalRequirement(
        id=id_,
        description=desc,
        rationale=kw.get("rationale", "because reasons"),
        acceptance_criteria=kw.get("acceptance_criteria", ["Given X when Y then Z"]),
        related_user_stories=kw.get("related_user_stories", ["US-001"]),
        traceability=kw.get("traceability", "PRFAQ FAQ #1"),
        origin=kw.get("origin", "agent-generated"),
    )


class TestRoundTripWithRenderer:
    def test_recovers_all_frs_from_rendered_brd(self):
        frs = [
            _fr("FR-001", "The system shall publish an approved artifact to a document store",
                acceptance_criteria=["Given an approved PRFAQ when the PM confirms then a doc is created",
                                     "Given a transport error then the command fails soft"],
                related_user_stories=["US-001", "US-002"],
                traceability="PRFAQ FAQ #3"),
            _fr("FR-002", "The system shall create one Taskei task per requirement",
                acceptance_criteria=["Given a BRD when seeded then N tasks exist"],
                related_user_stories=["US-003"]),
            _fr("FR-003", "The system shall ingest stakeholder feedback from Slack"),
        ]
        md = render_brd_to_markdown(_minimal_brd(frs))
        parsed = parse_functional_requirements(md)

        assert [p.id for p in parsed] == ["FR-001", "FR-002", "FR-003"]

        fr1 = parsed[0]
        assert fr1.description.startswith("The system shall publish an approved artifact")
        assert fr1.rationale == "because reasons"
        assert fr1.origin == "agent-generated"
        assert fr1.traceability == "PRFAQ FAQ #3"
        assert fr1.related_user_stories == ["US-001", "US-002"]
        assert len(fr1.acceptance_criteria) == 2
        assert fr1.acceptance_criteria[0].startswith("Given an approved PRFAQ")

        # Second FR's acceptance criteria didn't bleed into the first.
        assert parsed[1].acceptance_criteria == ["Given a BRD when seeded then N tasks exist"]

    def test_stops_at_non_functional_section(self):
        # NFR-001/002 must not be picked up as FRs (schema requires >=3 FRs).
        frs = [
            _fr("FR-001", "first functional requirement"),
            _fr("FR-002", "second functional requirement"),
            _fr("FR-003", "third functional requirement"),
        ]
        md = render_brd_to_markdown(_minimal_brd(frs))
        parsed = parse_functional_requirements(md)
        assert [p.id for p in parsed] == ["FR-001", "FR-002", "FR-003"]
        assert all("NFR" not in p.id for p in parsed)


class TestTolerance:
    def test_no_fr_section_returns_empty(self):
        assert parse_functional_requirements("# Some doc\n\nNo requirements here.") == []

    def test_empty_string_returns_empty(self):
        assert parse_functional_requirements("") == []

    def test_handles_manual_markdown_shape(self):
        md = (
            "## 5. Functional Requirements\n\n"
            "### FR-042: The system shall do the needful\n\n"
            "**Rationale:** it is needed\n\n"
            "**Acceptance criteria:**\n"
            "- crit one\n"
            "- crit two\n\n"
            "## 6. Non-Functional Requirements\n"
        )
        parsed = parse_functional_requirements(md)
        assert len(parsed) == 1
        assert parsed[0].id == "FR-042"
        assert parsed[0].acceptance_criteria == ["crit one", "crit two"]

    def test_parse_missing_file_returns_empty(self, tmp_path):
        assert parse_brd_file(tmp_path / "does_not_exist.md") == []

    def test_parse_file_round_trip(self, tmp_path):
        frs = [
            _fr("FR-001", "persisted requirement one"),
            _fr("FR-002", "persisted requirement two"),
            _fr("FR-003", "persisted requirement three"),
        ]
        md = render_brd_to_markdown(_minimal_brd(frs))
        p = tmp_path / "brd_test_v1.0.md"
        p.write_text(md, encoding="utf-8")
        parsed = parse_brd_file(p)
        assert [x.id for x in parsed] == ["FR-001", "FR-002", "FR-003"]
