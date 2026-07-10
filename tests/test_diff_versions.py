"""Tests for the markdown diff utility.

The diff splits documents into sections by exact header text. If a PM
manually renames a header between versions, the diff treats it as a
deletion plus an addition — not as a modification. These tests pin
that behavior so it's an explicit known limitation, not a silent bug.
"""

from pathlib import Path

from pm_agent_system.utils.diff_versions import diff_markdown_versions


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_renamed_header_shows_as_remove_plus_add(tmp_path):
    """A renamed header (e.g. 'FAQ' -> 'Frequently Asked Questions') is
    reported as REMOVED + ADDED rather than CHANGED. This documents the
    known limitation for anyone considering fuzzy header matching later."""
    old = _write(tmp_path, "old.md", "## FAQ\n\nSome answers.\n")
    new = _write(tmp_path, "new.md", "## Frequently Asked Questions\n\nSome answers.\n")

    result = diff_markdown_versions(str(old), str(new))

    assert "REMOVED" in result
    assert "ADDED" in result
    assert "FAQ" in result
    assert "Frequently Asked Questions" in result


def test_modified_section_shows_as_changed(tmp_path):
    """A section with the same header but different body is CHANGED."""
    old = _write(tmp_path, "old.md", "## Overview\n\nShort.\n")
    new = _write(tmp_path, "new.md", "## Overview\n\nShort overview with more detail.\n")

    result = diff_markdown_versions(str(old), str(new))

    assert "CHANGED" in result
    assert "Overview" in result


def test_identical_documents_report_no_differences(tmp_path):
    content = "## Summary\n\nSame content.\n"
    old = _write(tmp_path, "old.md", content)
    new = _write(tmp_path, "new.md", content)

    result = diff_markdown_versions(str(old), str(new))

    assert "No differences" in result


def test_duplicate_headings_are_not_collapsed(tmp_path):
    """Two sections sharing a heading must both be diffed. Previously the
    second occurrence overwrote the first in the section dict, so a change
    to the first section was silently reported as 'No differences'."""
    old = _write(
        tmp_path, "old.md", "## Notes\n\nFirst note.\n\n## Notes\n\nSecond note.\n"
    )
    new = _write(
        tmp_path,
        "new.md",
        "## Notes\n\nFirst note EDITED with extra words.\n\n## Notes\n\nSecond note.\n",
    )

    result = diff_markdown_versions(str(old), str(new))

    assert "No differences" not in result
    assert "CHANGED" in result
    assert "Notes" in result


def test_duplicate_heading_removal_is_reported(tmp_path):
    """Dropping the second of two same-named sections is reported as REMOVED,
    disambiguated by an occurrence suffix rather than silently ignored."""
    old = _write(tmp_path, "old.md", "## Notes\n\nAAA.\n\n## Notes\n\nBBB.\n")
    new = _write(tmp_path, "new.md", "## Notes\n\nAAA.\n")

    result = diff_markdown_versions(str(old), str(new))

    assert "REMOVED" in result
