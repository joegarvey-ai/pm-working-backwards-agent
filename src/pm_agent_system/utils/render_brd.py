from datetime import date

from pm_agent_system.models import BRDOutput
from pm_agent_system.models.brd_output import DataHandlingSection
from pm_agent_system.models.compliance_primitives import (
    ComplianceGate,
    LaunchReadinessItem,
    PrivacyConsiderations,
)
from pm_agent_system.output_inspector import find_defaulted_empty_fields, format_warning_block

_GAP_NOTICE_BLOCKQUOTE = (
    "> Data handling section flagged as a gap. Upstream PRFAQ did not "
    "include enough detail to enumerate data elements. See PRFAQ "
    "appendix_gaps."
)


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        clean = [str(c).replace("\n", " ").replace("|", "\\|") for c in row]
        lines.append("| " + " | ".join(clean) + " |")
    return lines


def _render_data_handling_section(section: DataHandlingSection) -> list[str]:
    """Render BRD section 13 (Data Handling) including gap notice or elements table."""
    lines: list[str] = ["## 13. Data Handling", ""]
    if section.gap_flag:
        lines.append(_GAP_NOTICE_BLOCKQUOTE)
        lines.append("")
        return lines
    classification_value = (
        section.dataset_classification.value
        if section.dataset_classification is not None
        else "Not specified"
    )
    lines.append(f"**Dataset Classification:** {classification_value}")
    lines.append("")
    if section.elements:
        rows = [
            [el.name, el.classification.value, el.purpose]
            for el in section.elements
        ]
        lines += _table(["Element", "Classification", "Purpose"], rows)
        lines.append("")
    return lines


def _render_vendor_considerations(
    vendor_considerations: str, scenarios_applied: list[str]
) -> list[str]:
    """Render BRD section 14 (Vendor Considerations) with explicit no-third-party fallback."""
    lines: list[str] = ["## 14. Vendor Considerations", ""]
    if scenarios_applied:
        lines.append(f"Scenarios applied: {', '.join(scenarios_applied)}.")
        lines.append("")
        lines.append(vendor_considerations)
    else:
        lines.append(
            "No third party is involved in this product. Vendor review, "
            "contract review, and procurement review are not required."
        )
    lines.append("")
    return lines


def _render_privacy_considerations(privacy: PrivacyConsiderations) -> list[str]:
    """Render BRD section 15 (Privacy Considerations) with risks, mitigations, and flag."""
    lines: list[str] = ["## 15. Privacy Considerations", ""]
    lines.append(f"**Design review flag:** {str(privacy.design_review_flag).lower()}")
    lines.append("")
    lines.append("Risks:")
    if privacy.risks:
        for risk in privacy.risks:
            lines.append(f"- {risk}")
    else:
        lines.append("- None recorded.")
    lines.append("")
    lines.append("Mitigations:")
    if privacy.mitigations:
        for mitigation in privacy.mitigations:
            lines.append(f"- {mitigation}")
    else:
        lines.append("- None recorded.")
    lines.append("")
    return lines


def _render_compliance_gates(gates: list[ComplianceGate]) -> list[str]:
    """Render BRD section 16 (Compliance Gates) as a bulleted list or a fallback line."""
    lines: list[str] = ["## 16. Compliance Gates", ""]
    if not gates:
        lines.append("No compliance gates recorded.")
    else:
        for gate in gates:
            lines.append(f"- {gate.name}. {gate.note} Owner: {gate.owner.value}.")
    lines.append("")
    return lines


def _render_launch_readiness_checklist(items: list[LaunchReadinessItem]) -> list[str]:
    """Render BRD section 17 (Launch Readiness Checklist) as a markdown table or fallback."""
    lines: list[str] = ["## 17. Launch Readiness Checklist", ""]
    if not items:
        lines.append("No launch readiness items recorded.")
        lines.append("")
        return lines
    rows = [
        [
            item.item,
            item.applies_to,
            item.gate_owner.value,
            item.evidence_reference if item.evidence_reference else " ",
        ]
        for item in items
    ]
    lines += _table(
        ["Item", "Applies To", "Gate Owner", "Evidence Reference"], rows
    )
    lines.append("")
    return lines


def _render_post_launch_maintenance(text: str) -> list[str]:
    """Render BRD section 18 (Post-Launch Maintenance) verbatim or with a fallback line."""
    lines: list[str] = ["## 18. Post-Launch Maintenance", ""]
    if text:
        lines.append(text)
    else:
        lines.append("No post-launch maintenance guidance recorded.")
    lines.append("")
    return lines


def render_brd_to_markdown(output: BRDOutput, slug: str = "") -> str:
    """Convert a structured BRDOutput to a human-readable markdown BRD.

    Adds YAML frontmatter as the source of truth for version metadata.
    """
    latest = output.version_history[-1] if output.version_history else None
    version = latest.version if latest else "1.0"
    author = latest.author if latest else "Agent 4"
    last_updated = latest.date if latest else date.today().isoformat()
    created = output.version_history[0].date if output.version_history else last_updated

    # Check for incomplete output
    empty_fields = find_defaulted_empty_fields(output)
    warning = format_warning_block(empty_fields)

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
    ]

    if warning:
        lines.append(warning)
        lines.append("")

    lines += [
        "# Business Requirements Document",
        "",
    ]

    lines += ["## 1. Executive Summary", "", output.executive_summary, ""]
    lines += ["## 2. Problem Statement", "", output.problem_statement, ""]
    lines += ["## 3. Proposed Solution Overview", "", output.proposed_solution_overview, ""]

    lines += ["## 4. User Stories", ""]
    rows = [
        [us.id, us.persona, us.action, us.outcome, us.priority, us.origin]
        for us in output.user_stories
    ]
    lines += _table(["ID", "Persona", "Action", "Outcome", "Priority", "Origin"], rows)
    lines.append("")

    lines += ["## 5. Functional Requirements", ""]
    for fr in output.functional_requirements:
        lines.append(f"### {fr.id}: {fr.description}")
        lines.append("")
        lines.append(f"**Rationale:** {fr.rationale}")
        lines.append("")
        lines.append(f"**Origin:** {fr.origin}")
        lines.append("")
        lines.append(f"**Traceability:** {fr.traceability}")
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
    if output.non_functional_requirements:
        nfr_rows = [
            [nfr.id, nfr.category, nfr.description, "; ".join(nfr.acceptance_criteria)]
            for nfr in output.non_functional_requirements
        ]
        lines += _table(["ID", "Category", "Description", "Acceptance Criteria"], nfr_rows)
    else:
        lines.append("_Not generated in this run._")
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
        lines.append("")

        # Append pricing data as collapsible reference blocks.
        pricing_flags = [cf for cf in output.cost_flags if cf.pricing_data]
        if pricing_flags:
            lines.append("### Pricing Reference Data")
            lines.append("")
            for cf in pricing_flags:
                lines.append(f"<details>")
                lines.append(f"<summary>{cf.decision} — AWS Pricing Details</summary>")
                lines.append("")
                lines.append("```")
                lines.append(cf.pricing_data)
                lines.append("```")
                lines.append("")
                lines.append("</details>")
                lines.append("")
    else:
        lines.append("No cost flags identified.")
    lines.append("")

    lines += ["## 9. Risks", ""]
    if output.risks:
        risk_rows = [[r.description, r.likelihood, r.impact, r.mitigation] for r in output.risks]
        lines += _table(["Description", "Likelihood", "Impact", "Mitigation"], risk_rows)
    else:
        lines.append("_Not generated in this run._")
    lines.append("")

    lines += ["## 10. Success Metrics", ""]
    sm_rows = [
        [sm.metric, sm.target_value, sm.measurement_method, sm.timeline]
        for sm in output.success_metrics
    ]
    lines += _table(["Metric", "Target", "Measurement", "Timeline"], sm_rows)
    lines.append("")

    lines += ["## 11. Timeline and Milestones", ""]
    if output.timeline_and_milestones:
        lines.append(output.timeline_and_milestones)
    else:
        lines.append("_Not generated in this run._")
    lines.append("")

    lines += ["## 12. Version History", ""]
    vh_rows = [[v.version, v.date, v.author, v.changes] for v in output.version_history]
    lines += _table(["Version", "Date", "Author", "Changes"], vh_rows)
    lines.append("")

    lines += _render_data_handling_section(output.data_handling_section)
    lines += _render_vendor_considerations(
        output.vendor_considerations, output.vendor_scenarios_applied
    )
    lines += _render_privacy_considerations(output.privacy_considerations)
    lines += _render_compliance_gates(output.compliance_gates)
    lines += _render_launch_readiness_checklist(output.launch_readiness_checklist)
    lines += _render_post_launch_maintenance(output.post_launch_maintenance)

    return "\n".join(lines)
