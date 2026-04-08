from datetime import date

from pm_agent_system.models import BRDOutput


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        clean = [str(c).replace("\n", " ").replace("|", "\\|") for c in row]
        lines.append("| " + " | ".join(clean) + " |")
    return lines


def render_brd_to_markdown(output: BRDOutput, slug: str = "") -> str:
    """Convert a structured BRDOutput to a human-readable markdown BRD.

    Adds YAML frontmatter as the source of truth for version metadata.
    """
    latest = output.version_history[-1] if output.version_history else None
    version = latest.version if latest else "1.0"
    author = latest.author if latest else "Agent 3"
    last_updated = latest.date if latest else date.today().isoformat()
    created = output.version_history[0].date if output.version_history else last_updated

    lines: list[str] = [
        "---",
        "type: brd",
        f'slug: "{slug}"',
        f'version: "{version}"',
        f'created: "{created}"',
        f'last_updated: "{last_updated}"',
        f'author: "{author}"',
        "---",
        "",
        "# Business Requirements Document",
        "",
    ]

    lines += ["## 1. Executive Summary", "", output.executive_summary, ""]
    lines += ["## 2. Problem Statement", "", output.problem_statement, ""]
    lines += ["## 3. Proposed Solution Overview", "", output.proposed_solution_overview, ""]

    lines += ["## 4. User Stories", ""]
    rows = [
        [us.id, us.persona, us.action, us.outcome, us.priority, us.source]
        for us in output.user_stories
    ]
    lines += _table(["ID", "Persona", "Action", "Outcome", "Priority", "Source"], rows)
    lines.append("")

    lines += ["## 5. Functional Requirements", ""]
    for fr in output.functional_requirements:
        lines.append(f"### {fr.id}: {fr.description}")
        lines.append("")
        lines.append(f"**Rationale:** {fr.rationale}")
        lines.append("")
        lines.append(f"**Related user stories:** {', '.join(fr.related_user_stories)}")
        lines.append("")
        lines.append("**Acceptance criteria:**")
        for ac in fr.acceptance_criteria:
            lines.append(f"- {ac}")
        lines.append("")
        for sample in fr.code_samples:
            lines.append(f"**{sample.description}**")
            lines.append("")
            lines.append(f"```{sample.language}")
            lines.append(sample.code)
            lines.append("```")
            lines.append("")

    lines += ["## 6. Non-Functional Requirements", ""]
    nfr_rows = [
        [nfr.id, nfr.category, nfr.description, "; ".join(nfr.acceptance_criteria)]
        for nfr in output.non_functional_requirements
    ]
    lines += _table(["ID", "Category", "Description", "Acceptance Criteria"], nfr_rows)
    lines.append("")

    lines += [
        "## 7. Technical Context and Dependencies",
        "",
        output.technical_context_and_dependencies,
        "",
    ]

    lines += ["## 8. Cost Flags", ""]
    if output.cost_flags:
        cf_rows = [
            [cf.decision, cf.why_it_matters, cf.tradeoff, cf.reference_url]
            for cf in output.cost_flags
        ]
        lines += _table(["Decision", "Why It Matters", "Tradeoff", "Reference"], cf_rows)
    else:
        lines.append("No cost flags identified.")
    lines.append("")

    lines += ["## 9. Risks", ""]
    risk_rows = [[r.description, r.likelihood, r.impact, r.mitigation] for r in output.risks]
    lines += _table(["Description", "Likelihood", "Impact", "Mitigation"], risk_rows)
    lines.append("")

    lines += ["## 10. Success Metrics", ""]
    sm_rows = [
        [sm.metric, sm.target_value, sm.measurement_method, sm.timeline]
        for sm in output.success_metrics
    ]
    lines += _table(["Metric", "Target", "Measurement", "Timeline"], sm_rows)
    lines.append("")

    lines += ["## 11. Timeline and Milestones", "", output.timeline_and_milestones, ""]

    lines += ["## 12. Version History", ""]
    vh_rows = [[v.version, v.date, v.author, v.changes] for v in output.version_history]
    lines += _table(["Version", "Date", "Author", "Changes"], vh_rows)
    lines.append("")

    return "\n".join(lines)
