"""Unified input parsing for PM input files.

Accepts either YAML (``.yaml``/``.yml``) or Obsidian-style markdown (``.md``)
and returns the same dict structure that the rest of the pipeline expects.

The markdown format is the recommended default for PMs; YAML stays as a
backward-compatible option for developers and CI/CD.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

from pm_agent_system.utils.text_io import read_text_lenient


# ---------- Field mapping ----------

# Markdown heading text (case-insensitive) → input dict key.
MARKDOWN_HEADING_TO_KEY: dict[str, str] = {
    "product name": "product_name",
    "initiative": "initiative",
    "feature / idea summary": "feature_summary",
    "goals": "goals",
    "target users": "user_summary",
    "timing": "timing",
    "success metrics": "success_metrics",
    "known constraints": "known_constraints",
    "business context": "business_context",
    "internal context": "internal_context",
    "style guide": "style_guide_path",
    "visual style guide": "visual_style_guide_path",
}


# ---------- Format detection ----------


def detect_input_format(file_path: str) -> str:
    """Return ``"yaml"`` or ``"markdown"`` based on extension.

    Raises ``ValueError`` for any other extension.
    """
    suffix = Path(file_path).suffix.lower()
    if suffix in (".yaml", ".yml"):
        return "yaml"
    if suffix == ".md":
        return "markdown"
    raise ValueError(
        f"Input file must be .yaml, .yml, or .md (got '{suffix}')"
    )


# ---------- YAML ----------


def parse_yaml_input(file_path: str) -> dict:
    """Load a YAML input file into a dict.

    A top-level scalar or list (i.e. not a mapping) returns ``{}`` so that
    ``validate_input`` reports the missing required fields cleanly instead of
    raising ``AttributeError`` on a later ``.get()``.
    """
    content = read_text_lenient(file_path)
    data = yaml.safe_load(content)
    return data if isinstance(data, dict) else {}


# ---------- Markdown ----------

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_H2_LINE_RE = re.compile(r"^##\s+(.+?)\s*$")
_H1_LINE_RE = re.compile(r"^#\s+.+$")


def _strip_frontmatter(text: str) -> str:
    """Remove leading YAML frontmatter (``---\n...\n---\n``) if present."""
    return _FRONTMATTER_RE.sub("", text, count=1)


def _strip_html_comments(text: str) -> str:
    """Remove all HTML comments from a string."""
    return _HTML_COMMENT_RE.sub("", text)


def parse_markdown_input(file_path: str) -> dict:
    """Parse an Obsidian-style markdown input brief into a dict.

    - Splits on h2 (``## ``) headings
    - Strips HTML comments (template guidance) from field values
    - Preserves wikilinks, multi-line content, and bullet lists as-is
    - Ignores YAML frontmatter, the h1 title, and unknown headings
    - Heading match is case-insensitive
    - Empty fields (only whitespace/comments) → None
    """
    raw = read_text_lenient(file_path)
    body = _strip_frontmatter(raw)

    result: dict[str, str | None] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        if current_key is None:
            return
        joined = "\n".join(current_lines)
        cleaned = _strip_html_comments(joined).strip()
        result[current_key] = cleaned if cleaned else None

    for line in body.splitlines():
        h2_match = _H2_LINE_RE.match(line)
        if h2_match:
            _flush()
            heading = h2_match.group(1).strip().lower()
            current_key = MARKDOWN_HEADING_TO_KEY.get(heading)
            current_lines = []
            continue

        if _H1_LINE_RE.match(line) and current_key is None:
            # Skip the document title before any h2 has been seen.
            continue

        if current_key is not None:
            current_lines.append(line)

    _flush()
    return result


# ---------- Unified entry point ----------


def parse_input(file_path: str) -> dict:
    """Read a PM input file and return its parsed dict.

    Dispatches on file extension. The returned dict has the same keys
    regardless of input format, so downstream code (validation, vault
    integration, crew kickoff) does not need to know which format was used.
    """
    path = Path(file_path)
    if not path.exists():
        print(f"Error: Input file not found: {path}")
        sys.exit(1)

    fmt = detect_input_format(file_path)
    if fmt == "markdown":
        return parse_markdown_input(file_path)
    return parse_yaml_input(file_path)
