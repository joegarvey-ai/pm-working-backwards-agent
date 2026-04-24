"""Tests for the artifact summary utility used by the feedback classifier."""

import pytest

from pm_agent_system.artifact_summary import (
    latest_artifact_path,
    read_all_summaries,
    read_artifact_summary,
)


@pytest.fixture
def tmp_output(tmp_path, monkeypatch):
    """Point OUTPUT_DIR at a temp directory."""
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    return tmp_path


# ---------- latest_artifact_path ----------


class TestLatestArtifactPath:
    def test_returns_none_when_no_files(self, tmp_output):
        assert latest_artifact_path("prfaq") is None

    def test_finds_single_version(self, tmp_output):
        p = tmp_output / "prfaq_slug_v1.0.md"
        p.write_text("# PRFAQ v1\n", encoding="utf-8")
        assert latest_artifact_path("prfaq") == p

    def test_picks_highest_version(self, tmp_output):
        (tmp_output / "prfaq_slug_v1.0.md").write_text("v1.0", encoding="utf-8")
        (tmp_output / "prfaq_slug_v1.2.md").write_text("v1.2", encoding="utf-8")
        (tmp_output / "prfaq_slug_v2.0.md").write_text("v2.0", encoding="utf-8")
        result = latest_artifact_path("prfaq")
        assert result is not None
        assert result.name == "prfaq_slug_v2.0.md"

    def test_ignores_unversioned_files(self, tmp_output):
        (tmp_output / "prfaq_slug.md").write_text("no version", encoding="utf-8")
        (tmp_output / "prfaq_slug_v1.0.md").write_text("v1.0", encoding="utf-8")
        result = latest_artifact_path("prfaq")
        assert result is not None
        assert result.name == "prfaq_slug_v1.0.md"

    def test_respects_artifact_type(self, tmp_output):
        (tmp_output / "brd_slug_v1.0.md").write_text("brd", encoding="utf-8")
        (tmp_output / "prfaq_slug_v1.0.md").write_text("prfaq", encoding="utf-8")
        assert latest_artifact_path("prfaq").name == "prfaq_slug_v1.0.md"
        assert latest_artifact_path("brd").name == "brd_slug_v1.0.md"
        assert latest_artifact_path("research_brief") is None


# ---------- read_artifact_summary ----------


class TestReadArtifactSummary:
    def test_returns_empty_when_no_file(self, tmp_output):
        assert read_artifact_summary("prfaq") == ""

    def test_returns_short_body_untrimmed(self, tmp_output):
        short = "# Short PRFAQ\n\nJust one section.\n"
        (tmp_output / "prfaq_slug_v1.0.md").write_text(short, encoding="utf-8")
        assert read_artifact_summary("prfaq") == short

    def test_strips_frontmatter(self, tmp_output):
        content = (
            "---\n"
            "title: Test\n"
            "version: 1.0\n"
            "---\n"
            "\n"
            "# Body starts here\n"
            "\n"
            "Content.\n"
        )
        (tmp_output / "prfaq_slug_v1.0.md").write_text(content, encoding="utf-8")
        summary = read_artifact_summary("prfaq")
        assert "title:" not in summary
        assert summary.startswith("# Body starts here")

    def test_truncates_long_content(self, tmp_output):
        # 3000-char body exceeds 2000-char cap
        long_body = "# Long\n\n" + ("x" * 3000)
        (tmp_output / "prfaq_slug_v1.0.md").write_text(long_body, encoding="utf-8")
        summary = read_artifact_summary("prfaq")
        assert len(summary) <= 2500  # 2000 cap + truncation marker
        assert "truncated" in summary

    def test_preserves_headers_in_summary(self, tmp_output):
        content = (
            "# Main title\n\n"
            "## Section 1\n\nBody.\n\n"
            "## Section 2\n\nMore body.\n"
        )
        (tmp_output / "prfaq_slug_v1.0.md").write_text(content, encoding="utf-8")
        summary = read_artifact_summary("prfaq")
        assert "# Main title" in summary
        assert "## Section 1" in summary


# ---------- read_all_summaries ----------


class TestReadAllSummaries:
    def test_returns_empty_strings_when_nothing_exists(self, tmp_output):
        summaries = read_all_summaries()
        assert set(summaries.keys()) == {
            "research_brief", "prfaq", "design_brief", "brd", "build_spec"
        }
        assert all(v == "" for v in summaries.values())

    def test_populates_available_artifacts(self, tmp_output):
        (tmp_output / "prfaq_slug_v1.0.md").write_text("# PRFAQ\n", encoding="utf-8")
        (tmp_output / "brd_slug_v1.0.md").write_text("# BRD\n", encoding="utf-8")
        summaries = read_all_summaries()
        assert summaries["prfaq"].startswith("# PRFAQ")
        assert summaries["brd"].startswith("# BRD")
        assert summaries["research_brief"] == ""
        assert summaries["design_brief"] == ""
        assert summaries["build_spec"] == ""
