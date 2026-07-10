"""Feedback inbox: read and write FeedbackItem files in output/feedback/.

Each feedback item lives as a markdown file with YAML frontmatter:

    ---
    id: fb-2026-04-24-001
    source: "VP Engineering (Sam Chen)"
    received: 2026-04-24T15:30:00Z
    status: open
    affects: []
    research_gaps: []
    contradictions: []
    incorporated_in: []
    summary: "VP wants tighter differentiation vs Swimm and Readme."
    ---

    # Feedback body

    Free-form markdown from the stakeholder. Meeting notes, interview
    transcripts, quoted emails, observations from a prototype demo.

Filenames follow the pattern `{id}.md`, e.g. `fb-2026-04-24-001.md`.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from pm_agent_system.models.feedback_item import FeedbackItem

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# ---------- Directory resolution ----------


def _output_dir() -> Path:
    """Resolve the output directory from OUTPUT_DIR env var (default ./output)."""
    return Path(os.getenv("OUTPUT_DIR", "./output")).expanduser().resolve()


def get_inbox_dir() -> Path:
    """Return the path to the feedback inbox directory, creating it if needed."""
    inbox = _output_dir() / "feedback"
    inbox.mkdir(parents=True, exist_ok=True)
    return inbox


# ---------- Parse ----------


def parse_feedback_file(path: Path) -> FeedbackItem | None:
    """Parse a feedback markdown file into a FeedbackItem.

    Returns None if the file is missing, has no frontmatter, or fails
    validation. Logs a warning in each failure case; never raises.
    """
    if not path.exists() or not path.is_file():
        logger.warning("Feedback file does not exist: %s", path)
        return None

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read feedback file %s: %s", path, exc)
        return None

    match = _FRONTMATTER_RE.match(content)
    if match is None:
        logger.warning("Feedback file %s has no YAML frontmatter block", path)
        return None

    fm_text = match.group(1)
    body = content[match.end():].lstrip("\n")

    try:
        fm_data = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        logger.warning("Feedback file %s has invalid YAML frontmatter: %s", path, exc)
        return None

    if not isinstance(fm_data, dict):
        logger.warning("Feedback file %s frontmatter is not a mapping", path)
        return None

    # Populate raw_text from the markdown body
    fm_data["raw_text"] = body

    # Auto-fill summary from the first non-empty line of the body if blank
    if not fm_data.get("summary"):
        for line in body.splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped:
                fm_data["summary"] = stripped[:200]
                break

    try:
        return FeedbackItem.model_validate(fm_data)
    except Exception as exc:
        logger.warning("Feedback file %s failed model validation: %s", path, exc)
        return None


def load_all_feedback() -> list[FeedbackItem]:
    """Load every valid feedback item from the inbox directory.

    Items are returned sorted by received timestamp (oldest first).
    """
    inbox = get_inbox_dir()
    items: list[FeedbackItem] = []
    for md_path in sorted(inbox.glob("*.md")):
        item = parse_feedback_file(md_path)
        if item is not None:
            items.append(item)
    # Normalize to tz-aware UTC before sorting: PyYAML parses "...Z" as
    # tz-aware and a space-form timestamp as naive, and Python refuses to
    # compare the two. Assume UTC when a timestamp carries no offset.
    def _received_key(it: FeedbackItem):
        received = it.received
        if received.tzinfo is None:
            return received.replace(tzinfo=timezone.utc)
        return received.astimezone(timezone.utc)

    items.sort(key=_received_key)
    return items


def load_feedback_by_id(fb_id: str) -> FeedbackItem | None:
    """Load a single feedback item by its ID."""
    path = get_inbox_dir() / f"{fb_id}.md"
    return parse_feedback_file(path)


# ---------- Write ----------


def write_feedback_item(item: FeedbackItem) -> Path:
    """Write a FeedbackItem back to its markdown file in the inbox.

    Preserves raw_text as the body below the frontmatter. Overwrites the
    existing file for the given id.
    """
    inbox = get_inbox_dir()
    path = inbox / f"{item.id}.md"

    fm_data = item.frontmatter_dict()
    fm_yaml = yaml.dump(
        fm_data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    content = f"---\n{fm_yaml}---\n\n{item.raw_text}"
    path.write_text(content, encoding="utf-8")
    return path


# ---------- ID generation ----------


def next_feedback_id(today: datetime | None = None) -> str:
    """Generate the next feedback ID for today's date.

    Format: fb-YYYY-MM-DD-NNN where NNN is the zero-padded sequence
    number for existing items received today.
    """
    today = today or datetime.now(timezone.utc)
    date_prefix = f"fb-{today.strftime('%Y-%m-%d')}"
    existing = [p.stem for p in get_inbox_dir().glob(f"{date_prefix}-*.md")]
    max_seq = 0
    for stem in existing:
        suffix = stem.replace(f"{date_prefix}-", "")
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))
    return f"{date_prefix}-{max_seq + 1:03d}"
