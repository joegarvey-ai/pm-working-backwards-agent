"""Export BRD user stories and requirements to project tracker formats.

Produces:
- Jira-importable CSV (compatible with Jira's CSV import wizard)
- Linear-compatible markdown (paste into Linear's bulk issue creator)
"""

import csv
import io

from pm_agent_system.models import BRDOutput


def export_jira_csv(output: BRDOutput) -> str:
    """Export user stories and functional requirements as Jira-importable CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Summary", "Description", "Issue Type", "Priority",
        "Labels", "Acceptance Criteria",
    ])

    priority_map = {"P0": "Highest", "P1": "High", "P2": "Medium"}

    for us in output.user_stories:
        summary = f"[{us.id}] As a {us.persona}, I want to {us.action}"
        description = (
            f"So that {us.outcome}\n\n"
            f"Origin: {us.origin}\n"
            f"Traceability: {us.traceability}"
        )
        writer.writerow([
            summary, description, "Story",
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
            description, "Task",
            priority_map.get("P0", "Medium"),
            fr.origin, ac_text,
        ])

    return buf.getvalue()


def export_linear_markdown(output: BRDOutput) -> str:
    """Export user stories and functional requirements as Linear-compatible markdown."""
    lines: list[str] = []

    for us in output.user_stories:
        lines.append(f"## [{us.id}] {us.action}")
        lines.append(f"**Priority:** {us.priority}")
        lines.append(f"**Persona:** {us.persona}")
        lines.append(f"**Outcome:** {us.outcome}")
        lines.append(f"**Origin:** {us.origin}")
        lines.append("")

    for fr in output.functional_requirements:
        lines.append(f"## [{fr.id}] {fr.description[:80]}")
        lines.append(f"**Rationale:** {fr.rationale}")
        lines.append("")
        lines.append("**Acceptance Criteria:**")
        for ac in fr.acceptance_criteria:
            lines.append(f"- {ac}")
        lines.append("")

    return "\n".join(lines)
