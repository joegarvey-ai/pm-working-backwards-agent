from pm_agent_system.models import ResearchOutput


def render_research_to_markdown(output: ResearchOutput) -> str:
    """Convert a structured ResearchOutput to the human-readable markdown brief.

    Produces the same 6-section format the agent currently writes, built from
    typed fields instead of raw LLM text.
    """
    lines: list[str] = []

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
