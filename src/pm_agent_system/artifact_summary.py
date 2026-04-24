"""Artifact summary utility: short summaries of each pipeline artifact.

The feedback classifier needs short summaries of the current state of
each artifact (research brief, PRFAQ, design brief, BRD, build spec)
so it can decide which sections a feedback item affects.

Wave 2 Day 1 ships the cheap version: read the latest versioned markdown
file for each artifact and return its first ~500 tokens. If Option A
(header-based extraction) falls short in practice, we can swap in a
one-shot summarizer LLM call (Option C) without changing the call site.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from pm_agent_system.models.feedback_item import ArtifactType

# Maps an artifact type to the filename prefix we scan for in output/
_PREFIX_MAP: dict[ArtifactType, str] = {
    "research_brief": "research_brief_",
    "prfaq": "prfaq_",
    "design_brief": "design_brief_",
    "brd": "brd_",
    "build_spec": "build_spec_",
}

# Maximum characters to include in a summary. 500 tokens is roughly
# 2000 characters of English prose. Keeping the cap in characters lets
# us avoid a tokenizer dependency for Wave 2 Day 1.
_MAX_CHARS = 2000

_VERSION_RE = re.compile(r"_v(\d+)\.(\d+)\.md$")


def _output_dir() -> Path:
    return Path(os.getenv("OUTPUT_DIR", "./output")).expanduser().resolve()


def latest_artifact_path(artifact: ArtifactType) -> Path | None:
    """Return the path to the latest versioned file for a given artifact type.

    Scans output/ for files matching `{prefix}{label}_v{major}.{minor}.md`
    and returns the one with the highest (major, minor) version. Returns
    None if no file matches.
    """
    prefix = _PREFIX_MAP.get(artifact)
    if prefix is None:
        return None

    out = _output_dir()
    if not out.is_dir():
        return None

    candidates = []
    for md_path in out.glob(f"{prefix}*.md"):
        match = _VERSION_RE.search(md_path.name)
        if match:
            major = int(match.group(1))
            minor = int(match.group(2))
            candidates.append(((major, minor), md_path))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][1]


def _strip_frontmatter(content: str) -> str:
    """Remove a leading YAML frontmatter block (if any) from markdown content."""
    if not content.startswith("---"):
        return content
    end = content.find("\n---\n", 3)
    if end == -1:
        return content
    return content[end + 5:].lstrip("\n")


def read_artifact_summary(artifact: ArtifactType) -> str:
    """Return a short summary of the latest version of the given artifact.

    The summary is the first _MAX_CHARS characters of the body (after
    stripping frontmatter). Section headers are preserved so the classifier
    can see the artifact's structure. If no file exists, returns an empty
    string; the classifier should treat that as 'artifact does not exist
    yet' and skip it.
    """
    path = latest_artifact_path(artifact)
    if path is None:
        return ""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    body = _strip_frontmatter(content)

    if len(body) <= _MAX_CHARS:
        return body

    truncated = body[:_MAX_CHARS]
    # Try to cut at a sensible boundary (end of line) near the cap.
    last_newline = truncated.rfind("\n")
    if last_newline > _MAX_CHARS - 200:
        truncated = truncated[:last_newline]
    return truncated + "\n\n[... truncated for classifier summary ...]\n"


def read_all_summaries() -> dict[ArtifactType, str]:
    """Return a dict of artifact_type -> summary for all five artifacts.

    Artifacts that do not yet exist on disk map to the empty string.
    """
    artifacts: list[ArtifactType] = [
        "research_brief",
        "prfaq",
        "design_brief",
        "brd",
        "build_spec",
    ]
    return {a: read_artifact_summary(a) for a in artifacts}
