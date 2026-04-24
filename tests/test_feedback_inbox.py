"""Tests for the feedback inbox parser and FeedbackItem model."""

from datetime import datetime, timezone

import pytest

from pm_agent_system.feedback_inbox import (
    get_inbox_dir,
    load_all_feedback,
    load_feedback_by_id,
    next_feedback_id,
    parse_feedback_file,
    write_feedback_item,
)
from pm_agent_system.models.feedback_item import (
    ArtifactImpact,
    ContradictionFlag,
    FeedbackItem,
    ResearchGap,
    VersionRef,
)


# ---------- Fixtures ----------


@pytest.fixture
def tmp_inbox(tmp_path, monkeypatch):
    """Point OUTPUT_DIR at a temp dir and return the inbox path."""
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    inbox = tmp_path / "feedback"
    inbox.mkdir(parents=True, exist_ok=True)
    return inbox


@pytest.fixture
def sample_item() -> FeedbackItem:
    return FeedbackItem(
        id="fb-2026-04-24-001",
        source="VP Engineering (Sam Chen)",
        received=datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc),
        status="open",
        summary="Ask for tighter differentiation vs Swimm and Readme",
        affects=[
            ArtifactImpact(
                artifact="prfaq",
                sections=["press_release", "external_faqs"],
                confidence=0.9,
                rationale="Direct competitive positioning feedback",
            ),
        ],
        raw_text="# Feedback body\n\nVP said the solution overview reads generic.",
    )


# ---------- Model-level tests ----------


class TestFeedbackItemModel:
    def test_model_round_trip(self, sample_item):
        """Serialize to dict and back without loss."""
        data = sample_item.model_dump()
        reconstructed = FeedbackItem.model_validate(data)
        assert reconstructed == sample_item

    def test_frontmatter_dict_excludes_raw_text(self, sample_item):
        fm = sample_item.frontmatter_dict()
        assert "raw_text" not in fm
        assert fm["id"] == "fb-2026-04-24-001"
        assert fm["status"] == "open"

    def test_defaults(self):
        item = FeedbackItem(
            id="fb-2026-01-01-001",
            source="Anon",
            received=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert item.status == "open"
        assert item.affects == []
        assert item.research_gaps == []
        assert item.contradictions == []
        assert item.incorporated_in == []

    def test_research_gap_model(self):
        gap = ResearchGap(
            tool="tavily",
            query="EU market size for documentation tools 2025",
            rationale="Original research covered US only",
        )
        assert gap.tool == "tavily"
        assert "EU" in gap.query

    def test_contradiction_flag_model(self):
        flag = ContradictionFlag(
            conflicts_with="fb-2026-04-24-002",
            summary="VP wants scope cut but Eng wants scope expanded",
        )
        assert flag.conflicts_with == "fb-2026-04-24-002"

    def test_version_ref_model(self):
        ref = VersionRef(
            artifact="prfaq",
            version="1.2",
            incorporated_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
        )
        assert ref.version == "1.2"


# ---------- Parser tests ----------


class TestParser:
    def test_parse_valid_file(self, tmp_inbox, sample_item):
        path = write_feedback_item(sample_item)
        loaded = parse_feedback_file(path)
        assert loaded is not None
        assert loaded.id == sample_item.id
        assert loaded.source == sample_item.source
        assert loaded.status == "open"
        assert len(loaded.affects) == 1
        assert loaded.affects[0].artifact == "prfaq"
        assert "VP" in loaded.raw_text

    def test_parse_missing_file(self, tmp_inbox):
        result = parse_feedback_file(tmp_inbox / "does-not-exist.md")
        assert result is None

    def test_parse_no_frontmatter(self, tmp_inbox):
        path = tmp_inbox / "fb-no-fm.md"
        path.write_text("# No frontmatter here\n\nJust a body.", encoding="utf-8")
        result = parse_feedback_file(path)
        assert result is None

    def test_parse_invalid_yaml(self, tmp_inbox):
        path = tmp_inbox / "fb-bad-yaml.md"
        path.write_text("---\nid: [broken: yaml\n---\n\nbody", encoding="utf-8")
        result = parse_feedback_file(path)
        assert result is None

    def test_parse_missing_required_fields(self, tmp_inbox):
        path = tmp_inbox / "fb-incomplete.md"
        path.write_text(
            "---\nid: fb-test\nstatus: open\n---\n\nbody\n",
            encoding="utf-8",
        )
        # Missing source and received fields -> validation fails
        result = parse_feedback_file(path)
        assert result is None

    def test_summary_auto_fill_from_body(self, tmp_inbox):
        path = tmp_inbox / "fb-auto-summary.md"
        path.write_text(
            '---\nid: fb-2026-01-01-001\n'
            'source: Anon\n'
            'received: "2026-01-01T00:00:00Z"\n'
            "status: open\n"
            "---\n\n"
            "# The PM should add a cost metric\n\n"
            "Longer details below.\n",
            encoding="utf-8",
        )
        item = parse_feedback_file(path)
        assert item is not None
        assert item.summary == "The PM should add a cost metric"


# ---------- Write tests ----------


class TestWrite:
    def test_write_then_read_round_trip(self, tmp_inbox, sample_item):
        path = write_feedback_item(sample_item)
        assert path.exists()
        loaded = parse_feedback_file(path)
        assert loaded is not None
        assert loaded.id == sample_item.id
        assert loaded.raw_text == sample_item.raw_text
        # Frontmatter round-trip preserves the affects structure
        assert len(loaded.affects) == 1
        assert loaded.affects[0].sections == ["press_release", "external_faqs"]

    def test_write_overwrites_existing(self, tmp_inbox, sample_item):
        write_feedback_item(sample_item)
        sample_item.status = "incorporated"
        sample_item.incorporated_in = [
            VersionRef(
                artifact="prfaq",
                version="1.1",
                incorporated_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
            )
        ]
        write_feedback_item(sample_item)
        loaded = load_feedback_by_id(sample_item.id)
        assert loaded is not None
        assert loaded.status == "incorporated"
        assert len(loaded.incorporated_in) == 1


# ---------- load_all and id-generation tests ----------


class TestLoadAll:
    def test_empty_inbox(self, tmp_inbox):
        assert load_all_feedback() == []

    def test_returns_items_sorted_by_received(self, tmp_inbox):
        older = FeedbackItem(
            id="fb-2026-04-20-001",
            source="Older source",
            received=datetime(2026, 4, 20, tzinfo=timezone.utc),
            raw_text="older",
        )
        newer = FeedbackItem(
            id="fb-2026-04-24-001",
            source="Newer source",
            received=datetime(2026, 4, 24, tzinfo=timezone.utc),
            raw_text="newer",
        )
        # Write newer first to verify sort order is by received, not filesystem order
        write_feedback_item(newer)
        write_feedback_item(older)

        items = load_all_feedback()
        assert len(items) == 2
        assert items[0].id == older.id
        assert items[1].id == newer.id

    def test_skips_invalid_files(self, tmp_inbox, sample_item):
        write_feedback_item(sample_item)
        # Drop an invalid file alongside
        (tmp_inbox / "broken.md").write_text("no frontmatter", encoding="utf-8")
        items = load_all_feedback()
        assert len(items) == 1
        assert items[0].id == sample_item.id


class TestIdGeneration:
    def test_first_id_for_today(self, tmp_inbox):
        today = datetime(2026, 4, 24, tzinfo=timezone.utc)
        assert next_feedback_id(today) == "fb-2026-04-24-001"

    def test_increments_past_existing(self, tmp_inbox):
        today = datetime(2026, 4, 24, tzinfo=timezone.utc)
        # Drop three existing items for today
        for seq in (1, 2, 5):
            item = FeedbackItem(
                id=f"fb-2026-04-24-{seq:03d}",
                source="Test",
                received=today,
                raw_text="",
            )
            write_feedback_item(item)
        # Next ID picks up from the highest existing sequence (5 -> 6)
        assert next_feedback_id(today) == "fb-2026-04-24-006"

    def test_ignores_other_days(self, tmp_inbox):
        yesterday_item = FeedbackItem(
            id="fb-2026-04-23-099",
            source="Test",
            received=datetime(2026, 4, 23, tzinfo=timezone.utc),
            raw_text="",
        )
        write_feedback_item(yesterday_item)
        today = datetime(2026, 4, 24, tzinfo=timezone.utc)
        assert next_feedback_id(today) == "fb-2026-04-24-001"


# ---------- get_inbox_dir tests ----------


class TestInboxDir:
    def test_creates_directory_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
        # Explicitly do not create feedback/ up front
        inbox_path = tmp_path / "feedback"
        assert not inbox_path.exists()

        resolved = get_inbox_dir()
        assert resolved.exists()
        assert resolved.is_dir()

    def test_respects_output_dir_env(self, tmp_path, monkeypatch):
        custom = tmp_path / "custom_output"
        monkeypatch.setenv("OUTPUT_DIR", str(custom))
        resolved = get_inbox_dir()
        assert resolved == (custom / "feedback").resolve()
