from pm_agent_system.models import ResearchOutput
from pm_agent_system.output_inspector import find_defaulted_empty_fields, format_warning_block


def render_research_to_markdown(output: ResearchOutput) -> str:
    """Convert a structured ResearchOutput to the human-readable markdown brief.

    Produces the same 6-section format the agent currently writes, built from
    typed fields instead of raw LLM text.
    """
    lines: list[str] = []

    empty_fields = find_defaulted_empty_fields(output)
    warning = format_warning_block(empty_fields)
    if warning:
        lines.append(warning)
        lines.append("")

    lines.append("# Research Brief")
    lines.append("")

    lines.append("## 1. Context")
    lines.append(output.context)
    lines.append("")

    lines.append("## 2. Executive Summary")
    lines.append(output.executive_summary)
    lines.append("")

    lines.append("## 3. Detailed Findings")
    lines.append("")

    lines.append("### 3a. Market Sizing")
    lines.append(output.market_sizing.summary)
    lines.append("")
    for point in output.market_sizing.data_points:
        lines.append(f"- {point}")
    lines.append("")

    lines.append("### 3b. Competitive Landscape")
    lines.append("")
    for comp in output.competitors:
        lines.append(f"**{comp.name}**")
        lines.append("")
        lines.append(comp.description)
        lines.append("")
        if comp.review_data:
            lines.append("**Review Ratings:**")
            for rd in comp.review_data:
                count_str = f" ({rd.review_count})" if rd.review_count else ""
                lines.append(f"- {rd.platform}: {rd.rating}{count_str}")
            lines.append("")
        if comp.strengths:
            lines.append("Strengths:")
            for s in comp.strengths:
                lines.append(f"- {s}")
            lines.append("")
        if comp.weaknesses:
            lines.append("Weaknesses:")
            for w in comp.weaknesses:
                lines.append(f"- {w}")
            lines.append("")
        if comp.top_pros:
            lines.append("**User Review Highlights — Pros:**")
            for pro in comp.top_pros:
                lines.append(f"- {pro}")
            lines.append("")
        if comp.top_cons:
            lines.append("**User Review Highlights — Cons:**")
            for con in comp.top_cons:
                lines.append(f"- {con}")
            lines.append("")
        if comp.reviewer_roles:
            lines.append(f"**Common Reviewer Roles:** {', '.join(comp.reviewer_roles)}")
            lines.append("")
        if comp.pricing_summary:
            lines.append(f"**Pricing:** {comp.pricing_summary}")
            lines.append("")
        lines.append(f"Relevance: {comp.relevance}")
        lines.append("")

    lines.append("### 3c. Customer Evidence")
    lines.append("")
    if output.customer_evidence:
        for q in output.customer_evidence:
            attribution = f" — {q.attribution}" if q.attribution else ""
            lines.append(f'> "{q.quote}"')
            lines.append(f"> ({q.source}{attribution}, theme: {q.theme})")
            lines.append("")
    else:
        lines.append("No customer evidence available.")
        lines.append("")

    lines.append("### 3d. Pain Point Summary")
    lines.append("")
    for pp in output.pain_points:
        lines.append(f"**{pp.description}**")
        lines.append(f"Severity: {pp.severity} (evidence count: {pp.evidence_count})")
        if pp.sources:
            lines.append(f"Sources: {', '.join(pp.sources)}")
        lines.append("")

    lines.append("### 3e. Internal State Assessment")
    if output.internal_state:
        lines.append(output.internal_state.current_architecture_summary)
        lines.append("")
        if output.internal_state.dependencies:
            lines.append("Dependencies:")
            for d in output.internal_state.dependencies:
                lines.append(f"- {d}")
            lines.append("")
        if output.internal_state.what_needs_to_change:
            lines.append("What needs to change:")
            for c in output.internal_state.what_needs_to_change:
                lines.append(f"- {c}")
            lines.append("")
        if output.internal_state.sources:
            lines.append(f"Sources: {', '.join(output.internal_state.sources)}")
            lines.append("")
    else:
        lines.append("No internal context was provided for this request.")
        lines.append("")

    lines.append("## 4. Strategic Implications")
    lines.append(output.strategic_implications)
    lines.append("")

    lines.append("## 5. Gaps and Limitations")
    for gap in output.gaps_and_limitations:
        lines.append(f"- {gap}")
    lines.append("")

    lines.append("## 6. Sources")
    for src in output.sources:
        lines.append(f"- {src}")
    lines.append("")

    return "\n".join(lines)
