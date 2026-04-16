from datetime import date

from pm_agent_system.models import PRFAQOutput
from pm_agent_system.output_inspector import find_defaulted_empty_fields, format_warning_block


def render_prfaq_to_markdown(output: PRFAQOutput, slug: str = "") -> str:
    """Convert a structured PRFAQOutput to a human-readable markdown PRFAQ.

    Adds YAML frontmatter as the source of truth for version metadata. The
    version history table in the body is preserved for human readers but
    is no longer authoritative.
    """
    latest = output.version_history[-1] if output.version_history else None
    version = latest.version if latest else "1.0"
    author = latest.author if latest else "Agent 2"
    last_updated = latest.date if latest else date.today().isoformat()
    created = output.version_history[0].date if output.version_history else last_updated

    empty_fields = find_defaulted_empty_fields(output)
    warning = format_warning_block(empty_fields)

    lines: list[str] = [
        "---",
        "type: prfaq",
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

    lines.append("# PRFAQ")
    lines.append("")

    lines.append("## Press Release")
    lines.append("")
    lines.append(output.press_release)
    lines.append("")

    lines.append("## External FAQs")
    lines.append("")
    for faq in output.external_faqs:
        lines.append(f"**Q: {faq.question}**")
        lines.append("")
        lines.append(faq.answer)
        lines.append("")

    lines.append("## Internal FAQs")
    lines.append("")
    for faq in output.internal_faqs:
        lines.append(f"**Q: {faq.question}**")
        lines.append("")
        lines.append(faq.answer)
        lines.append("")

    lines.append("## Customer Experience Narrative")
    lines.append("")
    lines.append(output.customer_experience_narrative)
    lines.append("")

    lines.append("## Appendices")
    lines.append("")

    lines.append("### A. Data Points")
    lines.append("")
    for dp in output.appendix_data_points:
        lines.append(f"- {dp}")
    lines.append("")

    lines.append("### B. Competitor Comparison")
    lines.append("")
    if output.appendix_competitor_table:
        # Determine base headers from the competitor table dicts.
        base_headers = list(output.appendix_competitor_table[0].keys())

        # Add G2 and Capterra rating columns if review data is available
        # in the research output (carried through as extra keys by Agent 2).
        rating_headers = []
        for h in ("G2 Rating", "Capterra Rating"):
            if h not in base_headers:
                # Check if any row has the key (Agent 2 may have added it).
                if any(h in row for row in output.appendix_competitor_table):
                    rating_headers.append(h)
        headers = base_headers + rating_headers

        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in output.appendix_competitor_table:
            values = [str(row.get(h, "")).replace("\n", " ") for h in headers]
            lines.append("| " + " | ".join(values) + " |")
        lines.append("")
    else:
        lines.append("No competitor data available.")
        lines.append("")

    lines.append("### C. Customer Quotes")
    lines.append("")
    if output.appendix_customer_quotes:
        for q in output.appendix_customer_quotes:
            attribution = f" — {q.attribution}" if q.attribution else ""
            lines.append(f'> "{q.quote}"')
            lines.append(f"> ({q.source}{attribution}, theme: {q.theme})")
            lines.append("")
    else:
        lines.append("No customer quotes available.")
        lines.append("")

    lines.append("### D. Open Gaps and Assumptions")
    lines.append("")
    for gap in output.appendix_gaps:
        lines.append(f"- {gap}")
    lines.append("")

    lines.append("## Version History")
    lines.append("")
    lines.append("| Version | Date | Author | Changes |")
    lines.append("| --- | --- | --- | --- |")
    for v in output.version_history:
        changes = v.changes.replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {v.version} | {v.date} | {v.author} | {changes} |")
    lines.append("")

    return "\n".join(lines)
