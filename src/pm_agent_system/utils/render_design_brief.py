from datetime import date

from pm_agent_system.models import DesignBriefOutput
from pm_agent_system.output_inspector import find_defaulted_empty_fields, format_warning_block


def render_design_brief_to_markdown(output: DesignBriefOutput, slug: str = "") -> str:
    """Convert a structured DesignBriefOutput to a human-readable markdown brief.

    Adds YAML frontmatter as the source of truth for version metadata.
    """
    version = "1.0"
    author = "Agent 3"
    last_updated = date.today().isoformat()
    created = last_updated

    empty_fields = find_defaulted_empty_fields(output)
    warning = format_warning_block(empty_fields)

    lines: list[str] = [
        "---",
        "type: design_brief",
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

    lines.append("# Design Brief")
    lines.append("")

    lines.append("## Product Overview")
    lines.append("")
    lines.append(output.product_overview)
    lines.append("")

    lines.append("## Screen Inventory")
    lines.append("")
    lines.append("| Screen | Purpose | Primary User Flow | Source |")
    lines.append("| --- | --- | --- | --- |")
    for s in output.screen_inventory:
        row = [s.name, s.purpose, s.primary_flow, s.source_section]
        clean = [c.replace("\n", " ").replace("|", "\\|") for c in row]
        lines.append("| " + " | ".join(clean) + " |")
    lines.append("")

    lines.append("## User Flows")
    lines.append("")
    for flow in output.user_flows:
        lines.append(f"### {flow.name} ({flow.priority})")
        lines.append("")
        for step in flow.steps:
            lines.append(
                f"{step.step_number}. **{step.user_action}** → "
                f"{step.system_response} (on {step.screen})"
            )
        lines.append("")
        if flow.related_screens:
            lines.append(f"Related screens: {', '.join(flow.related_screens)}")
            lines.append("")

    lines.append("## Design Principles")
    lines.append("")
    for i, principle in enumerate(output.design_principles, 1):
        lines.append(f"{i}. {principle}")
    lines.append("")

    lines.append("## Competitive UI Patterns")
    lines.append("")
    lines.append(output.competitive_ui_patterns)
    lines.append("")

    lines.append("## Brand / Style Context")
    lines.append("")
    if output.style_guide_used:
        lines.append(output.brand_style_context)
    else:
        lines.append(output.brand_style_context or "No visual style guide was provided.")
    lines.append("")

    lines.append("## Accessibility")
    lines.append("")
    lines.append(output.accessibility_considerations or "_Not specified._")
    lines.append("")

    lines.append("## Platform Targets")
    lines.append("")
    if output.platform_targets:
        lines.append(", ".join(output.platform_targets))
    else:
        lines.append("_Not specified._")
    lines.append("")

    return "\n".join(lines)
