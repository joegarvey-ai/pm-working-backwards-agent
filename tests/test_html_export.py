"""Tests for the HTML export module."""

from pm_agent_system.html_export import markdown_to_html


def test_produces_valid_html_structure():
    md = "# Hello\n\nSome text."
    html = markdown_to_html(md, title="Test")
    assert "<!DOCTYPE html>" in html
    assert "<title>Test</title>" in html
    assert "<style>" in html
    assert "<h1>" in html
    assert "Some text." in html


def test_strips_frontmatter():
    md = '---\ntype: brd\nversion: "1.0"\n---\n\n# BRD\n\nContent.'
    html = markdown_to_html(md, title="BRD")
    assert "type: brd" not in html
    assert "<h1>" in html
    assert "Content." in html


def test_renders_tables():
    md = "| A | B |\n| --- | --- |\n| 1 | 2 |"
    html = markdown_to_html(md)
    assert "<table>" in html
    assert "<th>" in html
    assert "<td>" in html


def test_renders_code_blocks():
    md = "```python\nprint('hello')\n```"
    html = markdown_to_html(md)
    assert "<pre>" in html
    assert "code" in html


def test_renders_blockquotes_for_warnings():
    md = "> **Warning** Something is wrong.\n>\n> Details here."
    html = markdown_to_html(md)
    assert "<blockquote>" in html
    assert "Warning" in html


def test_no_external_resources():
    md = "# Test\n\nContent."
    html = markdown_to_html(md)
    assert "<link" not in html
    assert "<script" not in html
    assert "cdn" not in html.lower()
    assert "http://" not in html
    assert "https://" not in html


def test_inline_css_under_150_lines():
    """CSS should be compact — under 150 lines."""
    md = "# Test"
    html = markdown_to_html(md)
    # Extract CSS between <style> tags
    start = html.index("<style>") + len("<style>")
    end = html.index("</style>")
    css = html[start:end]
    line_count = len(css.strip().splitlines())
    assert line_count < 150, f"CSS is {line_count} lines, expected under 150"
