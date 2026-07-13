"""Frontmatter parsing and version-string helpers.

Extracted from ``main.py`` (audit item #16). These functions read the YAML
frontmatter that renderers write as the source of truth for version metadata,
and increment version strings tolerantly so a hand-edited or LLM-emitted
version never crashes a revise flow.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _prfaq_version_from_output(obj) -> str:
    """Resolve the version string from a PRFAQOutput's version_history."""
    return obj.version_history[-1].version if obj.version_history else "1.0"


def _brd_version_from_output(obj) -> str:
    return obj.version_history[-1].version if obj.version_history else "1.0"


def read_frontmatter(filepath: Path) -> dict:
    """Parse YAML frontmatter from a markdown file.

    Returns an empty-defaults dict if no frontmatter is found, so older
    files written before frontmatter existed still load cleanly.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return {"version": "0.0", "slug": "", "type": ""}

    match = FRONTMATTER_RE.match(text)
    if not match:
        return {"version": "0.0", "slug": "", "type": ""}

    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {"version": "0.0", "slug": "", "type": ""}

    data.setdefault("version", "0.0")
    data.setdefault("slug", "")
    data.setdefault("type", "")
    return data


def read_current_version(filepath: Path) -> str:
    """Read version from frontmatter. Defaults to 1.0 if not found."""
    fm = read_frontmatter(filepath)
    v = str(fm.get("version", "0.0"))
    return v if v != "0.0" else "1.0"


def bump_version(version: str) -> str:
    """Increment the minor component of an ``X.Y`` version string.

    Tolerates versions that are not exactly ``major.minor``: a single
    component (``"2"``) is treated as ``2.0`` and bumped to ``2.1``; extra
    or non-numeric components (``"1.0.0"``, ``"1.0-beta"``) fall back to
    bumping the first numeric-looking minor, or to ``<version>.1`` when no
    numeric minor is present. Never raises on a malformed frontmatter or
    LLM-emitted version.
    """
    parts = str(version).split(".")
    major = parts[0] if parts and parts[0] else "1"
    minor_raw = parts[1] if len(parts) > 1 else "0"
    try:
        minor = int("".join(c for c in minor_raw if c.isdigit()) or "0")
    except ValueError:
        minor = 0
    return f"{major}.{minor + 1}"
