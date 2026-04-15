"""Export BRD user stories and requirements to project tracker formats.

Produces:
- Jira-importable CSV (compatible with Jira's CSV import wizard)
- Linear-compatible markdown (paste into Linear's bulk issue creator)

Column mappings and field labels are read from `config/jira_import_schema.yaml`
and `config/linear_import_schema.yaml`. Every Jira/Linear instance is different,
so PMs can edit those files to match their workspace before importing.
"""

import csv
import io
from pathlib import Path

import yaml

from pm_agent_system.models import BRDOutput

# Fallback defaults used when the config file is missing or malformed.
# These mirror the shipped config/jira_import_schema.yaml and
# config/linear_import_schema.yaml so the exports still work out of the box.

DEFAULT_JIRA_SCHEMA = {
    "columns": {
        "summary": "Summary",
        "description": "Description",
        "issue_type": "Issue Type",
        "priority": "Priority",
        "labels": "Labels",
        "acceptance_criteria": "Acceptance Criteria",
    },
    "user_story_issue_type": "Story",
    "functional_requirement_issue_type": "Task",
    "priority_map": {
        "P0": "Highest",
        "P1": "High",
        "P2": "Medium",
        "P3": "Low",
        "P4": "Lowest",
    },
}

DEFAULT_LINEAR_SCHEMA = {
    "labels": {
        "priority": "Priority",
        "persona": "Persona",
        "outcome": "Outcome",
        "origin": "Origin",
        "rationale": "Rationale",
        "acceptance_criteria": "Acceptance Criteria",
    },
}


def _load_schema(filename: str, defaults: dict) -> dict:
    """Load a YAML schema from ./config/ with a safe fallback to defaults."""
    # Resolve relative to CWD (matches the style_guide_loader convention).
    path = Path.cwd() / "config" / filename
    if not path.exists() or not path.is_file():
        return defaults
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return defaults
    # Shallow-merge so a partial config still works.
    merged = {**defaults, **loaded}
    if "columns" in defaults and isinstance(loaded.get("columns"), dict):
        merged["columns"] = {**defaults["columns"], **loaded["columns"]}
    if "priority_map" in defaults and isinstance(loaded.get("priority_map"), dict):
        merged["priority_map"] = {**defaults["priority_map"], **loaded["priority_map"]}
    if "labels" in defaults and isinstance(loaded.get("labels"), dict):
        merged["labels"] = {**defaults["labels"], **loaded["labels"]}
    return merged


def export_jira_csv(output: BRDOutput) -> str:
    """Export user stories and functional requirements as Jira-importable CSV.

    Column names and priority mapping are read from
    `config/jira_import_schema.yaml`. Edit that file to match your Jira
    instance's field names before importing.
    """
    schema = _load_schema("jira_import_schema.yaml", DEFAULT_JIRA_SCHEMA)
    cols = schema["columns"]
    priority_map = schema["priority_map"]
    story_type = schema["user_story_issue_type"]
    fr_type = schema["functional_requirement_issue_type"]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        cols["summary"], cols["description"], cols["issue_type"],
        cols["priority"], cols["labels"], cols["acceptance_criteria"],
    ])

    for us in output.user_stories:
        summary = f"[{us.id}] As a {us.persona}, I want to {us.action}"
        description = (
            f"So that {us.outcome}\n\n"
            f"Origin: {us.origin}\n"
            f"Traceability: {us.traceability}"
        )
        writer.writerow([
            summary, description, story_type,
            priority_map.get(us.priority, "Medium"),
            us.origin, "",
        ])

    for fr in output.functional_requirements:
        ac_text = "\n".join(f"- {ac}" for ac in fr.acceptance_criteria)
        description = (
            f"{fr.description}\n\n"
            f"Rationale: {fr.rationale}\n"
            f"Origin: {fr.origin}\n"
            f"Traceability: {fr.traceability}\n"
            f"Related stories: {', '.join(fr.related_user_stories)}"
        )
        writer.writerow([
            f"[{fr.id}] {fr.description[:80]}",
            description, fr_type,
            priority_map.get("P0", "Medium"),
            fr.origin, ac_text,
        ])

    return buf.getvalue()


def export_linear_markdown(output: BRDOutput) -> str:
    """Export user stories and functional requirements as Linear-compatible markdown.

    Field labels are read from `config/linear_import_schema.yaml`. Edit that
    file to match your team's Linear naming conventions.
    """
    schema = _load_schema("linear_import_schema.yaml", DEFAULT_LINEAR_SCHEMA)
    lbl = schema["labels"]

    lines: list[str] = []

    for us in output.user_stories:
        lines.append(f"## [{us.id}] {us.action}")
        lines.append(f"**{lbl['priority']}:** {us.priority}")
        lines.append(f"**{lbl['persona']}:** {us.persona}")
        lines.append(f"**{lbl['outcome']}:** {us.outcome}")
        lines.append(f"**{lbl['origin']}:** {us.origin}")
        lines.append("")

    for fr in output.functional_requirements:
        lines.append(f"## [{fr.id}] {fr.description[:80]}")
        lines.append(f"**{lbl['rationale']}:** {fr.rationale}")
        lines.append("")
        lines.append(f"**{lbl['acceptance_criteria']}:**")
        for ac in fr.acceptance_criteria:
            lines.append(f"- {ac}")
        lines.append("")

    return "\n".join(lines)
