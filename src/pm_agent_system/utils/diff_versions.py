"""Simple section-level diff between two markdown documents.

Compares two versioned documents (PRFAQs or BRDs) and produces a
human-readable summary of what changed between versions.
"""

import re
from pathlib import Path


def diff_markdown_versions(old_path: str, new_path: str) -> str:
    """Compare two markdown files and return a section-level diff summary."""
    old_text = Path(old_path).read_text(encoding="utf-8")
    new_text = Path(new_path).read_text(encoding="utf-8")

    old_sections = _split_sections(old_text)
    new_sections = _split_sections(new_text)

    all_headings = list(dict.fromkeys(
        list(old_sections.keys()) + list(new_sections.keys())
    ))

    changes: list[str] = []
    for heading in all_headings:
        old_content = old_sections.get(heading, "")
        new_content = new_sections.get(heading, "")

        if heading not in old_sections:
            changes.append(f"**ADDED:** {heading}")
        elif heading not in new_sections:
            changes.append(f"**REMOVED:** {heading}")
        elif old_content.strip() != new_content.strip():
            old_words = len(old_content.split())
            new_words = len(new_content.split())
            delta = new_words - old_words
            direction = f"+{delta}" if delta > 0 else str(delta)
            changes.append(f"**CHANGED:** {heading} ({direction} words)")

    if not changes:
        return "No differences found between the two versions."

    return "## Changes between versions\n\n" + "\n".join(
        f"- {c}" for c in changes
    )


def _split_sections(text: str) -> dict[str, str]:
    """Split markdown into sections by ## headings."""
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)

    sections: dict[str, str] = {}
    current_heading = "(preamble)"
    current_lines: list[str] = []

    for line in text.split("\n"):
        match = re.match(r"^(#{1,3})\s+(.+)", line)
        if match:
            if current_lines:
                sections[current_heading] = "\n".join(current_lines)
            current_heading = match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections[current_heading] = "\n".join(current_lines)

    return sections
