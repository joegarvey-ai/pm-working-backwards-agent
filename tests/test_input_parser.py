"""Tests for the unified input parser (YAML and markdown)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pm_agent_system import input_parser
from pm_agent_system.input_parser import (
    MARKDOWN_HEADING_TO_KEY,
    detect_input_format,
    parse_input,
    parse_markdown_input,
    parse_yaml_input,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = REPO_ROOT / "examples"


# ---------- detect_input_format ----------


def test_detect_yaml(tmp_path: Path) -> None:
    yaml_file = tmp_path / "input.yaml"
    yml_file = tmp_path / "input.yml"
    yaml_file.touch()
    yml_file.touch()
    assert detect_input_format(str(yaml_file)) == "yaml"
    assert detect_input_format(str(yml_file)) == "yaml"


def test_detect_markdown(tmp_path: Path) -> None:
    md_file = tmp_path / "input.md"
    md_file.touch()
    assert detect_input_format(str(md_file)) == "markdown"


def test_detect_unknown(tmp_path: Path) -> None:
    txt_file = tmp_path / "input.txt"
    txt_file.touch()
    with pytest.raises(ValueError, match=r"\.yaml.*\.yml.*\.md"):
        detect_input_format(str(txt_file))


# ---------- parse_markdown_input ----------


def _write(tmp_path: Path, name: str, content: str) -> str:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_parse_markdown_all_fields(tmp_path: Path) -> None:
    """All template headings filled → every mapped key populated."""
    sections = []
    for heading, key in MARKDOWN_HEADING_TO_KEY.items():
        title = heading.title().replace("/", "/")
        sections.append(f"## {title}\n\nvalue for {key}\n")
    content = "# Product Input Brief\n\n" + "\n".join(sections)
    path = _write(tmp_path, "all-fields.md", content)

    result = parse_markdown_input(path)

    for key in MARKDOWN_HEADING_TO_KEY.values():
        assert result[key] == f"value for {key}", f"missing {key}: {result.get(key)!r}"


def test_parse_markdown_optional_fields_blank(tmp_path: Path) -> None:
    """Required filled, optionals blank → optional keys are None."""
    content = """# Product Input Brief

## Product Name

Widget

## Feature / Idea Summary

Build a thing.

## Goals

Do well.

## Target Users

Anyone.

## Timing

Soon.

## Success Metrics


## Known Constraints


## Business Context


## Internal Context


## Style Guide


## Visual Style Guide

"""
    path = _write(tmp_path, "minimal.md", content)
    result = parse_markdown_input(path)

    assert result["product_name"] == "Widget"
    assert result["feature_summary"] == "Build a thing."
    for optional in (
        "success_metrics",
        "known_constraints",
        "business_context",
        "internal_context",
        "style_guide_path",
        "visual_style_guide_path",
    ):
        assert result[optional] is None, f"{optional} should be None, got {result[optional]!r}"


def test_parse_markdown_strips_html_comments(tmp_path: Path) -> None:
    content = """## Product Name
<!-- Short name for folder names. Required. -->
Widget
"""
    path = _write(tmp_path, "comment.md", content)
    result = parse_markdown_input(path)
    assert result["product_name"] == "Widget"
    assert "<!--" not in (result["product_name"] or "")


def test_parse_markdown_empty_field_with_only_comments(tmp_path: Path) -> None:
    content = """## Product Name
<!-- guidance only, no content -->


## Goals
Real goal.
"""
    path = _write(tmp_path, "comment-only.md", content)
    result = parse_markdown_input(path)
    assert result["product_name"] is None
    assert result["goals"] == "Real goal."


def test_parse_markdown_preserves_wikilinks(tmp_path: Path) -> None:
    content = """## Internal Context

See [[Current Architecture HLD]] and [[Q1 Analytics Usage Report]].
"""
    path = _write(tmp_path, "wikilink.md", content)
    result = parse_markdown_input(path)
    assert "[[Current Architecture HLD]]" in result["internal_context"]
    assert "[[Q1 Analytics Usage Report]]" in result["internal_context"]


def test_parse_markdown_preserves_multiline(tmp_path: Path) -> None:
    content = """## Feature / Idea Summary

Paragraph one.

Paragraph two with more detail.

Paragraph three.
"""
    path = _write(tmp_path, "multiline.md", content)
    result = parse_markdown_input(path)
    assert "Paragraph one." in result["feature_summary"]
    assert "Paragraph two with more detail." in result["feature_summary"]
    assert "Paragraph three." in result["feature_summary"]
    # Line breaks preserved (not collapsed)
    assert "\n" in result["feature_summary"]


def test_parse_markdown_preserves_bullets(tmp_path: Path) -> None:
    content = """## Goals

- Reduce churn by 10%
- Grow active users 25%
- Ship by Q3
"""
    path = _write(tmp_path, "bullets.md", content)
    result = parse_markdown_input(path)
    assert "- Reduce churn by 10%" in result["goals"]
    assert "- Grow active users 25%" in result["goals"]
    assert "- Ship by Q3" in result["goals"]


def test_parse_markdown_ignores_frontmatter(tmp_path: Path) -> None:
    content = """---
tags: [pm, brief]
created: 2026-04-18
---
# Product Input Brief

## Product Name

Widget
"""
    path = _write(tmp_path, "frontmatter.md", content)
    result = parse_markdown_input(path)
    assert result["product_name"] == "Widget"
    # Frontmatter values must NOT leak into any field
    assert "tags" not in result
    assert "pm" not in (result.get("product_name") or "")


def test_parse_markdown_ignores_h1(tmp_path: Path) -> None:
    content = """# Product Input Brief

## Product Name

Widget
"""
    path = _write(tmp_path, "h1.md", content)
    result = parse_markdown_input(path)
    # The h1 should not become a field; product_name is the only key
    assert list(result.keys()) == ["product_name"]
    assert result["product_name"] == "Widget"


def test_parse_markdown_ignores_unknown_headings(tmp_path: Path) -> None:
    content = """## Product Name

Widget

## Notes to Self

random scribbles that should be dropped silently

## Goals

Do well.
"""
    path = _write(tmp_path, "unknown.md", content)
    result = parse_markdown_input(path)
    assert result["product_name"] == "Widget"
    assert result["goals"] == "Do well."
    assert "Notes to Self" not in result
    assert "random scribbles" not in str(result.values())


def test_parse_markdown_case_insensitive_headings(tmp_path: Path) -> None:
    content = """## product name

Widget

## GOALS

Win.

## Feature / IDEA Summary

Ship a thing.
"""
    path = _write(tmp_path, "case.md", content)
    result = parse_markdown_input(path)
    assert result["product_name"] == "Widget"
    assert result["goals"] == "Win."
    assert result["feature_summary"] == "Ship a thing."


# ---------- parse_input dispatch ----------


def test_parse_input_routes_correctly(tmp_path: Path, monkeypatch) -> None:
    yaml_file = tmp_path / "x.yaml"
    md_file = tmp_path / "x.md"
    yaml_file.write_text("foo: bar\n", encoding="utf-8")
    md_file.write_text("## Product Name\n\nW\n", encoding="utf-8")

    calls: list[str] = []

    def fake_yaml(p: str) -> dict:
        calls.append(f"yaml:{p}")
        return {"_format": "yaml"}

    def fake_md(p: str) -> dict:
        calls.append(f"md:{p}")
        return {"_format": "md"}

    monkeypatch.setattr(input_parser, "parse_yaml_input", fake_yaml)
    monkeypatch.setattr(input_parser, "parse_markdown_input", fake_md)

    assert parse_input(str(yaml_file)) == {"_format": "yaml"}
    assert parse_input(str(md_file)) == {"_format": "md"}
    assert calls == [f"yaml:{yaml_file}", f"md:{md_file}"]


# ---------- Cross-format equivalence ----------


def _normalize(value) -> str:
    """Collapse any whitespace run to a single space, strip ends.

    YAML folded scalars (``>``) collapse newlines into spaces; markdown
    preserves them. Both express the same semantic content.
    """
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def test_yaml_and_markdown_produce_same_dict() -> None:
    """Parse the YAML and markdown reference examples; assert equivalent values
    for every key the two formats share."""
    yaml_path = EXAMPLES / "input.yaml"
    md_path = EXAMPLES / "input-brief-example.md"
    assert yaml_path.exists() and md_path.exists()

    yaml_dict = parse_yaml_input(str(yaml_path))
    md_dict = parse_markdown_input(str(md_path))

    shared_keys = set(yaml_dict.keys()) & set(md_dict.keys())
    # The two reference files MUST share every required + encouraged field
    expected_shared = {
        "product_name",
        "initiative",
        "feature_summary",
        "goals",
        "user_summary",
        "timing",
        "success_metrics",
        "known_constraints",
        "internal_context",
        "business_context",
    }
    missing = expected_shared - shared_keys
    assert not missing, f"shared keys missing from one example: {missing}"

    mismatches = []
    for key in expected_shared:
        y = _normalize(yaml_dict.get(key))
        m = _normalize(md_dict.get(key))
        if y != m:
            mismatches.append((key, y, m))
    assert not mismatches, "value mismatches:\n" + "\n".join(
        f"  {k}: yaml={y!r} md={m!r}" for k, y, m in mismatches
    )


# ---------- encoding tolerance (Windows PM input) ----------


def _write_bytes(tmp_path: Path, name: str, data: bytes) -> str:
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def test_parse_markdown_cp1252(tmp_path: Path) -> None:
    """A brief pasted from Word/Outlook (cp1252 smart quotes, em dash) parses
    instead of crashing with UnicodeDecodeError, recovering the characters."""
    text = (
        "## Product Name\n\nWidget\n\n"
        "## Feature / Idea Summary\n\nWe’re building a “smart” tool — really.\n"
    )
    path = _write_bytes(tmp_path, "cp1252.md", text.encode("cp1252"))

    result = parse_markdown_input(path)

    assert result["product_name"] == "Widget"
    summary = result["feature_summary"]
    assert "’" in summary  # right single quote
    assert "“" in summary and "”" in summary  # curly double quotes
    assert "—" in summary  # em dash


def test_parse_markdown_utf8_bom(tmp_path: Path) -> None:
    """A UTF-8 file saved with a BOM (Windows Notepad) does not leak a U+FEFF
    into the first heading; the product name is read cleanly."""
    data = b"\xef\xbb\xbf" + "## Product Name\n\nWidget\n".encode("utf-8")
    path = _write_bytes(tmp_path, "bom.md", data)

    result = parse_markdown_input(path)

    assert result["product_name"] == "Widget"


def test_parse_markdown_undefined_bytes_does_not_crash(tmp_path: Path) -> None:
    """Genuinely undecodable bytes fall back to replacement rather than
    aborting the whole command with a traceback."""
    data = "## Product Name\n\nWidget\n\n## Feature / Idea Summary\n\n".encode("utf-8")
    data += bytes([0x81, 0x90]) + b"\n"  # undefined in cp1252, invalid utf-8
    path = _write_bytes(tmp_path, "garbage.md", data)

    result = parse_markdown_input(path)  # must not raise

    assert result["product_name"] == "Widget"


def test_parse_yaml_cp1252(tmp_path: Path) -> None:
    """A cp1252-encoded YAML value with a smart quote is recovered."""
    text = 'product_name: "Widget’s"\nfeature_summary: "Do a thing."\n'
    path = _write_bytes(tmp_path, "input.yaml", text.encode("cp1252"))

    result = parse_yaml_input(path)

    assert result["product_name"] == "Widget’s"


def test_parse_yaml_non_mapping_returns_empty(tmp_path: Path) -> None:
    """A top-level scalar/list (not a mapping) returns {} so validation can
    report missing fields cleanly instead of raising AttributeError."""
    path = _write_bytes(tmp_path, "prose.yaml", b"just prose, not a mapping\n")

    assert parse_yaml_input(path) == {}
