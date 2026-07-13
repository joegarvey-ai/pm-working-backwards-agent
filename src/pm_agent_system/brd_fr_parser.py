"""Parse functional requirements out of a rendered BRD markdown file.

The pipeline persists the BRD only as markdown (plus Jira/Linear exports) —
no structured ``BRDOutput`` JSON is written to disk. So ``seed-taskei`` must
recover the functional requirements by parsing the rendered markdown.

The BRD renderer (``utils/render_brd.py``) emits a stable, deterministic
"Functional Requirements" section:

    ## 5. Functional Requirements

    ### FR-001: The system shall do X
    **Rationale:** ...
    **Origin:** ...
    **Traceability:** ...
    **Related user stories:** US-001, US-002
    **Acceptance criteria:**
    - given/when/then ...
    - ...

This module parses exactly that shape into lightweight ``ParsedFR`` records.
It is intentionally tolerant: unknown fields are ignored, and a missing
sub-field yields an empty value rather than an error. It never raises on
malformed input — it returns whatever it could parse (possibly an empty list).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedFR:
    """One functional requirement recovered from rendered BRD markdown."""

    id: str
    description: str
    rationale: str = ""
    origin: str = ""
    traceability: str = ""
    related_user_stories: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)


# "## 5. Functional Requirements" — the section header the renderer emits.
# Tolerant to the leading number changing, so we anchor on the phrase.
_FR_SECTION_RE = re.compile(
    r"^#{1,6}\s*(?:\d+\.\s*)?Functional Requirements\s*$",
    re.IGNORECASE,
)
# The next top-level section (## 6. ...) ends the FR block. Any level-2
# heading after the FR header that is NOT an FR entry (### FR-...) ends it.
_NEXT_H2_RE = re.compile(r"^##\s+", )
# "### FR-001: The system shall ..." — one requirement entry.
_FR_ENTRY_RE = re.compile(r"^#{3,6}\s*(FR-\d+)\s*[:.\-]?\s*(.*)$")
# "**Rationale:** ..." style labelled fields.
_FIELD_RE = re.compile(r"^\*\*(?P<label>[^:*]+):\*\*\s*(?P<value>.*)$")
# "- bullet" acceptance-criteria lines.
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")


def _isolate_fr_section(text: str) -> list[str]:
    """Return the lines belonging to the Functional Requirements section.

    Starts after the FR section header and stops at the next level-2 heading
    that is not an FR sub-entry. Returns an empty list if no FR section is
    present.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if _FR_SECTION_RE.match(line.strip()):
            start = i + 1
            break
    if start is None:
        return []

    collected: list[str] = []
    for line in lines[start:]:
        # A new level-2 section (## 6. Non-Functional Requirements) ends the
        # FR block. FR entries are level-3 (### FR-001), so they are kept.
        if _NEXT_H2_RE.match(line):
            break
        collected.append(line)
    return collected


def parse_functional_requirements(text: str) -> list[ParsedFR]:
    """Parse every FR entry from rendered BRD markdown *text*.

    Returns the requirements in document order. Never raises; malformed or
    absent sections yield an empty list.
    """
    section = _isolate_fr_section(text)
    if not section:
        return []

    frs: list[ParsedFR] = []
    current: ParsedFR | None = None
    in_acceptance = False

    for raw in section:
        line = raw.rstrip()
        stripped = line.strip()

        entry = _FR_ENTRY_RE.match(stripped)
        if entry:
            if current is not None:
                frs.append(current)
            current = ParsedFR(id=entry.group(1), description=entry.group(2).strip())
            in_acceptance = False
            continue

        if current is None:
            continue

        field_match = _FIELD_RE.match(stripped)
        if field_match:
            label = field_match.group("label").strip().lower()
            value = field_match.group("value").strip()
            if label.startswith("rationale"):
                current.rationale = value
                in_acceptance = False
            elif label.startswith("origin"):
                current.origin = value
                in_acceptance = False
            elif label.startswith("traceability"):
                current.traceability = value
                in_acceptance = False
            elif label.startswith("related user stor"):
                current.related_user_stories = [
                    us.strip() for us in value.split(",") if us.strip()
                ]
                in_acceptance = False
            elif label.startswith("acceptance criteria"):
                in_acceptance = True
            else:
                in_acceptance = False
            continue

        bullet = _BULLET_RE.match(stripped)
        if bullet and in_acceptance:
            current.acceptance_criteria.append(bullet.group(1).strip())
            continue

        # Any other non-blank, non-bullet line ends an acceptance-criteria run
        # (e.g. a code-sample heading the renderer appends after the criteria).
        if stripped and not bullet:
            in_acceptance = False

    if current is not None:
        frs.append(current)
    return frs


def parse_brd_file(path: str | Path) -> list[ParsedFR]:
    """Read a BRD markdown file and parse its functional requirements.

    Returns an empty list if the file is missing or unreadable (never raises).
    """
    p = Path(path).expanduser()
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return parse_functional_requirements(text)
