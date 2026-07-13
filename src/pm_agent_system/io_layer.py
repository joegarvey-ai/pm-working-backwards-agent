"""Filesystem output layer: OUTPUT_DIR resolution, retention, and artifact writes.

Extracted from ``main.py`` (audit item #16). Everything here is concerned with
turning rendered markdown into files under ``OUTPUT_DIR`` (plus their HTML
siblings and Jira/Linear exports), archiving stale output, and appending the
usage log. No CLI parsing, no crew orchestration, no vault logic.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from pm_agent_system.html_export import markdown_to_html
from pm_agent_system.models import BRDOutput
from pm_agent_system.utils import (
    export_jira_csv,
    export_linear_markdown,
    formatted_spec_extension,
)

logger = logging.getLogger(__name__)


def _slugify(text: str, max_len: int = 50) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text[:max_len]).strip("_")


def _output_dir() -> Path:
    output_dir = Path(os.getenv("OUTPUT_DIR", "./output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _archive_dir(output_dir: Path) -> Path:
    archive = output_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    return archive


def enforce_retention_policy(output_dir: Path, archive_after_days: int = 30) -> int:
    """Move files in output_dir older than N days into output_dir/archive/.

    Skips the archive subdirectory itself. Returns the number of files moved.
    Silent on individual file errors so this never blocks a real run.
    """
    if archive_after_days <= 0 or not output_dir.exists():
        return 0

    cutoff = time.time() - (archive_after_days * 86400)
    archive = _archive_dir(output_dir)
    moved = 0
    for entry in output_dir.iterdir():
        if entry.is_dir():
            continue
        try:
            if entry.stat().st_mtime >= cutoff:
                continue
            target = archive / entry.name
            if target.exists():
                stem, suffix = target.stem, target.suffix
                target = archive / f"{stem}_{int(entry.stat().st_mtime)}{suffix}"
            entry.rename(target)
            moved += 1
        except Exception as exc:
            logger.warning("Failed to archive %s: %s", entry.name, exc)
            continue
    return moved


def _retention_days() -> int:
    try:
        return int(os.getenv("OUTPUT_RETENTION_DAYS", "30"))
    except ValueError:
        return 30


def _append_usage_log(entry: dict, log_path: Path, max_bytes: int = 5 * 1024 * 1024) -> None:
    """Append one JSON line to the usage log, rotating at max_bytes.

    Size-based rotation keeps a single backup (usage_log.jsonl.1). The log is
    write-only (nothing reads it back), so rotation never drops history a
    report needs. Non-blocking: logging must never fail a real run.
    """
    try:
        if log_path.exists() and log_path.stat().st_size >= max_bytes:
            backup = log_path.with_name(log_path.name + ".1")
            if backup.exists():
                backup.unlink()
            log_path.rename(backup)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # Non-blocking; don't fail the command over logging


def save_markdown_brief(markdown: str) -> Path:
    """Write the rendered research brief to OUTPUT_DIR with a timestamped name."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _output_dir() / f"research_brief_{timestamp}.md"
    path.write_text(markdown, encoding="utf-8")
    html_path = path.with_suffix(".html")
    html_path.write_text(markdown_to_html(markdown, title="Research Brief"), encoding="utf-8")
    return path


def save_prfaq(markdown: str, feature_summary: str, version: str) -> Path:
    """Write a PRFAQ markdown file with the version-aware filename convention."""
    slug = _slugify(feature_summary) or "prfaq"
    path = _output_dir() / f"prfaq_{slug}_v{version}.md"
    path.write_text(markdown, encoding="utf-8")
    html_path = path.with_suffix(".html")
    html_path.write_text(markdown_to_html(markdown, title="PRFAQ"), encoding="utf-8")
    return path


def publish_output(source_file: Path, destination_dir: Path, label: str) -> Path:
    """Copy an approved file to the publish destination with a timestamped name."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(label)
    dest_path = destination_dir / f"{timestamp}_{slug}{source_file.suffix}"
    shutil.copy2(source_file, dest_path)
    return dest_path


def save_design_brief(markdown: str, label: str, version: str = "1.0") -> Path:
    """Write a design brief markdown file to OUTPUT_DIR."""
    slug = _slugify(label) or "design_brief"
    path = _output_dir() / f"design_brief_{slug}_v{version}.md"
    path.write_text(markdown, encoding="utf-8")
    html_path = path.with_suffix(".html")
    html_path.write_text(markdown_to_html(markdown, title="Design Brief"), encoding="utf-8")
    return path


def save_brd(markdown: str, label: str, version: str) -> Path:
    slug = _slugify(label) or "brd"
    path = _output_dir() / f"brd_{slug}_v{version}.md"
    path.write_text(markdown, encoding="utf-8")
    html_path = path.with_suffix(".html")
    html_path.write_text(markdown_to_html(markdown, title="Business Requirements Document"), encoding="utf-8")
    return path


def save_build_spec(reference_md: str, formatted: str, label: str, target_tool: str) -> tuple[Path, Path]:
    """Write the human-readable wrapper and the tool-ready formatted_spec file.

    Returns (reference_path, formatted_spec_path).
    """
    slug = _slugify(label) or "build_spec"
    out = _output_dir()
    reference_path = out / f"build_spec_{slug}_{target_tool}.md"
    spec_path = out / f"build_spec_{slug}_{target_tool}_formatted{formatted_spec_extension(target_tool)}"
    reference_path.write_text(reference_md, encoding="utf-8")
    spec_path.write_text(formatted, encoding="utf-8")
    return reference_path, spec_path


def save_brd_exports(brd: BRDOutput, label: str) -> None:
    """Write Jira CSV and Linear markdown exports alongside the BRD."""
    slug = _slugify(label) or "brd"
    out = _output_dir()
    jira_path = out / f"brd_{slug}_jira_import.csv"
    linear_path = out / f"brd_{slug}_linear_import.md"
    jira_path.write_text(export_jira_csv(brd), encoding="utf-8")
    linear_path.write_text(export_linear_markdown(brd), encoding="utf-8")
    print(f"Jira import CSV: {jira_path}")
    print(f"Linear import MD: {linear_path}")
