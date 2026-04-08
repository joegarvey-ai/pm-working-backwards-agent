from datetime import date

from pm_agent_system.models import CodingPromptOutput

# File extension per target tool. Lovable gets .txt for natural-language pasting;
# everything else stays markdown for now.
TOOL_EXTENSIONS = {
    "kiro": ".md",
    "claude_code": ".md",
    "cursor": ".md",
    "lovable": ".txt",
}


def formatted_spec_extension(target_tool: str) -> str:
    return TOOL_EXTENSIONS.get(target_tool, ".md")


def render_build_spec_to_markdown(
    output: CodingPromptOutput, slug: str = "", version: str = "1.0"
) -> str:
    """Convert a CodingPromptOutput to a structured markdown reference doc.

    This is the human-readable wrapper that surrounds the formatted_spec.
    The formatted_spec itself is written separately as the tool-ready file.
    """
    today = date.today().isoformat()
    lines: list[str] = [
        "---",
        "type: build_spec",
        f'slug: "{slug}"',
        f'version: "{version}"',
        f'target_tool: "{output.target_tool}"',
        f'created: "{today}"',
        "---",
        "",
        "# Build Spec",
        "",
        f"**Target tool:** {output.target_tool}",
        "",
    ]

    lines += ["## Build Summary", "", output.build_summary, ""]

    lines += ["## User Flows", ""]
    for flow in output.user_flows:
        lines.append(f"### {flow.name}")
        lines.append("")
        if flow.related_requirements:
            lines.append(f"_Related requirements: {', '.join(flow.related_requirements)}_")
            lines.append("")
        for i, step in enumerate(flow.steps, 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    lines += ["## Feature Specs", ""]
    for feat in output.feature_specs:
        lines.append(f"### {feat.name} ({feat.priority})")
        lines.append("")
        lines.append(feat.description)
        lines.append("")
        lines.append("**Acceptance criteria:**")
        for ac in feat.acceptance_criteria:
            lines.append(f"- {ac}")
        lines.append("")
        for sample in feat.code_samples:
            lines.append(f"**{sample.description}**")
            lines.append("")
            lines.append(f"```{sample.language}")
            lines.append(sample.code)
            lines.append("```")
            lines.append("")

    lines += ["## Technical Constraints", ""]
    for tc in output.technical_constraints:
        lines.append(f"- {tc}")
    lines.append("")

    lines += ["## Architecture Reference", "", output.architecture_reference, ""]
    lines += ["## Current State Context", "", output.current_state_context, ""]

    lines += ["## Out of Scope", ""]
    for item in output.out_of_scope:
        lines.append(f"- {item}")
    lines.append("")

    lines += [
        "## Formatted Spec (paste this into the target tool)",
        "",
        f"_Target tool: **{output.target_tool}**_",
        "",
        "---",
        "",
        output.formatted_spec,
        "",
    ]

    return "\n".join(lines)
