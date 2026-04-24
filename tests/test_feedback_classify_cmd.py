"""Tests for the `feedback classify` CLI command.

Mocks the CrewAI kickoff so tests run without Bedrock calls. Verifies
that the command reads target items, calls the crew with correct
inputs, writes classifier output back onto each item, and skips
already-classified items unless --rerun.
"""

import argparse
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from pm_agent_system.feedback_inbox import (
    load_feedback_by_id,
    write_feedback_item,
)
from pm_agent_system.models.feedback_classification import FeedbackClassification
from pm_agent_system.models.feedback_item import (
    ArtifactImpact,
    ContradictionFlag,
    FeedbackItem,
    ResearchGap,
)


@pytest.fixture
def tmp_inbox(tmp_path, monkeypatch):
    """Point OUTPUT_DIR at a temp dir and create the inbox."""
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    inbox = tmp_path / "feedback"
    inbox.mkdir(parents=True, exist_ok=True)
    return inbox


@pytest.fixture
def unclassified_item() -> FeedbackItem:
    """A feedback item with no classification (no affects yet)."""
    return FeedbackItem(
        id="fb-2026-04-24-001",
        source="VP Engineering",
        received=datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc),
        status="open",
        summary="Tighten competitive differentiation",
        raw_text="# Body\n\nVP wants callouts for specific competitors.",
    )


@pytest.fixture
def classified_item() -> FeedbackItem:
    """A feedback item that has already been classified."""
    return FeedbackItem(
        id="fb-2026-04-24-002",
        source="Legal",
        received=datetime(2026, 4, 24, 16, 0, tzinfo=timezone.utc),
        status="open",
        summary="Add GDPR language",
        affects=[
            ArtifactImpact(
                artifact="prfaq",
                sections=["customer_experience_narrative"],
                confidence=0.9,
                rationale="Legal compliance requirement",
            ),
        ],
        raw_text="Need explicit GDPR language.",
    )


def _make_mock_kickoff_result(classification: FeedbackClassification) -> MagicMock:
    """Build a mock CrewOutput whose tasks_output[0].pydantic == classification."""
    mock_task_output = MagicMock()
    mock_task_output.pydantic = classification
    result = MagicMock()
    result.tasks_output = [mock_task_output]
    return result


@pytest.fixture
def mock_crew():
    """Patch PmAgentSystem.feedback_classify_crew to return a mock crew.

    Usage in tests: call mock_crew(classification) to set the return value.

    Note: uses patch.object with a replacement function instead of
    patch(return_value=...) because CrewAI's @crew decorator wraps
    class methods in a descriptor. Replacing with a plain function
    sidesteps the descriptor and gives each instance.method() call
    the correct return value.
    """
    active_patchers = []

    def setup_and_track(classification: FeedbackClassification):
        mock_instance = MagicMock()
        mock_instance.kickoff.return_value = _make_mock_kickoff_result(classification)

        # Replace the method on the class with a plain function that returns
        # the mock. This bypasses CrewAI's @crew descriptor wrapping.
        def fake_crew(self):  # noqa: ARG001
            return mock_instance

        from pm_agent_system import main as _main

        patcher = patch.object(
            _main.PmAgentSystem,
            "feedback_classify_crew",
            fake_crew,
        )
        patcher.start()
        active_patchers.append(patcher)
        return mock_instance

    yield setup_and_track

    for p in active_patchers:
        p.stop()


# ---------- Tests ----------


class TestFeedbackClassifyCommand:
    def test_classifies_unclassified_item_and_writes_back(
        self, tmp_inbox, unclassified_item, mock_crew
    ):
        """Classify an open, unclassified item and verify its frontmatter updates."""
        write_feedback_item(unclassified_item)

        classification = FeedbackClassification(
            affects=[
                ArtifactImpact(
                    artifact="prfaq",
                    sections=["press_release", "external_faqs"],
                    confidence=0.85,
                    rationale="Competitive positioning feedback",
                ),
            ],
            contradictions=[],
            research_gaps=[],
        )
        mock_crew(classification)

        from pm_agent_system.main import cmd_feedback_classify

        args = argparse.Namespace(item=None, rerun=False)
        cmd_feedback_classify(args)

        reloaded = load_feedback_by_id(unclassified_item.id)
        assert reloaded is not None
        assert len(reloaded.affects) == 1
        assert reloaded.affects[0].artifact == "prfaq"
        assert reloaded.affects[0].sections == ["press_release", "external_faqs"]

    def test_skips_already_classified_without_rerun(
        self, tmp_inbox, classified_item, mock_crew
    ):
        """An already-classified item is NOT reclassified without --rerun."""
        write_feedback_item(classified_item)

        # Set up a mock that would overwrite the existing classification
        # if called; we assert it is not called.
        mock_instance = mock_crew(FeedbackClassification(affects=[]))

        from pm_agent_system.main import cmd_feedback_classify

        args = argparse.Namespace(item=None, rerun=False)
        cmd_feedback_classify(args)

        # The crew should never have been kicked off
        mock_instance.kickoff.assert_not_called()

        # The item's affects stay intact
        reloaded = load_feedback_by_id(classified_item.id)
        assert reloaded is not None
        assert len(reloaded.affects) == 1
        assert reloaded.affects[0].sections == ["customer_experience_narrative"]

    def test_rerun_reclassifies_existing(self, tmp_inbox, classified_item, mock_crew):
        """--rerun forces reclassification even when affects is populated."""
        write_feedback_item(classified_item)

        new_classification = FeedbackClassification(
            affects=[
                ArtifactImpact(
                    artifact="brd",
                    sections=["risks"],
                    confidence=0.75,
                    rationale="Risk section impact",
                ),
            ],
        )
        mock_crew(new_classification)

        from pm_agent_system.main import cmd_feedback_classify

        args = argparse.Namespace(item=None, rerun=True)
        cmd_feedback_classify(args)

        reloaded = load_feedback_by_id(classified_item.id)
        assert reloaded is not None
        assert len(reloaded.affects) == 1
        assert reloaded.affects[0].artifact == "brd"

    def test_item_filter_classifies_only_named_item(
        self, tmp_inbox, unclassified_item, mock_crew
    ):
        """--item fb-ID limits classification to that single item."""
        other = FeedbackItem(
            id="fb-2026-04-24-002",
            source="Other",
            received=datetime(2026, 4, 24, 17, 0, tzinfo=timezone.utc),
            status="open",
            raw_text="Other feedback",
        )
        write_feedback_item(unclassified_item)
        write_feedback_item(other)

        mock_instance = mock_crew(
            FeedbackClassification(
                affects=[ArtifactImpact(artifact="prfaq", confidence=0.8)]
            )
        )

        from pm_agent_system.main import cmd_feedback_classify

        args = argparse.Namespace(item=unclassified_item.id, rerun=False)
        cmd_feedback_classify(args)

        # Crew kicked off exactly once (for the named item only)
        assert mock_instance.kickoff.call_count == 1

        # Named item got classified
        reloaded = load_feedback_by_id(unclassified_item.id)
        assert reloaded is not None
        assert len(reloaded.affects) == 1

        # Other item still unclassified
        other_reloaded = load_feedback_by_id(other.id)
        assert other_reloaded is not None
        assert len(other_reloaded.affects) == 0

    def test_writes_research_gaps_and_contradictions(
        self, tmp_inbox, unclassified_item, mock_crew
    ):
        """Classifier output's research_gaps and contradictions persist to disk."""
        write_feedback_item(unclassified_item)

        classification = FeedbackClassification(
            affects=[ArtifactImpact(artifact="prfaq", confidence=0.6)],
            research_gaps=[
                ResearchGap(
                    tool="tavily",
                    query="EU market size for doc tooling 2025",
                    rationale="Research did not cover EU",
                ),
            ],
            contradictions=[
                ContradictionFlag(
                    conflicts_with="prfaq v1.0 press_release",
                    summary="Feedback says Haiku-only; PRFAQ claims Sonnet",
                ),
            ],
        )
        mock_crew(classification)

        from pm_agent_system.main import cmd_feedback_classify

        args = argparse.Namespace(item=None, rerun=False)
        cmd_feedback_classify(args)

        reloaded = load_feedback_by_id(unclassified_item.id)
        assert reloaded is not None
        assert len(reloaded.research_gaps) == 1
        assert reloaded.research_gaps[0].tool == "tavily"
        assert len(reloaded.contradictions) == 1
        assert "Haiku" in reloaded.contradictions[0].summary

    def test_no_open_items_prints_message(self, tmp_inbox, mock_crew, capsys):
        """With an empty inbox, the command prints a no-items message."""
        mock_crew(FeedbackClassification())

        from pm_agent_system.main import cmd_feedback_classify

        args = argparse.Namespace(item=None, rerun=False)
        cmd_feedback_classify(args)

        captured = capsys.readouterr()
        assert "No open feedback items" in captured.out

    def test_missing_item_id_exits(self, tmp_inbox, mock_crew):
        """--item with a nonexistent ID causes a sys.exit."""
        mock_crew(FeedbackClassification())

        from pm_agent_system.main import cmd_feedback_classify

        args = argparse.Namespace(item="fb-does-not-exist", rerun=False)
        with pytest.raises(SystemExit):
            cmd_feedback_classify(args)
