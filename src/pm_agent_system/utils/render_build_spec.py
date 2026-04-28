import re
from datetime import date

from pm_agent_system.models import CodingPromptOutput, RACIRow
from pm_agent_system.models.brd_output import BRDOutput, DataHandlingSection
from pm_agent_system.models.compliance_primitives import (
    _DATA_CLASS_ORDER,
    DataClassification,
    DataElement,
    GateOwner,
    PrivacyConsiderations,
)
from pm_agent_system.output_inspector import find_defaulted_empty_fields, format_warning_block

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
    empty_fields = find_defaulted_empty_fields(output)
    warning = format_warning_block(empty_fields)

    lines: list[str] = [
        "---",
        "type: build_spec",
        f'slug: "{slug}"',
        f'version: "{version}"',
        f'target_tool: "{output.target_tool}"',
        f'created: "{today}"',
        "---",
        "",
    ]

    if warning:
        lines.append(warning)
        lines.append("")

    lines += [
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


def _stride_triggers(brd_output: BRDOutput) -> bool:
    """Return True when STRIDE and related compliance scaffolds should render."""
    confidential_rank = _DATA_CLASS_ORDER[DataClassification.CONFIDENTIAL]
    elements = brd_output.data_handling_section.elements
    has_sensitive_element = any(
        _DATA_CLASS_ORDER[e.classification] >= confidential_rank for e in elements
    )
    design_review_flag = brd_output.privacy_considerations.design_review_flag
    has_vendor_scenario = len(brd_output.vendor_scenarios_applied) >= 1
    return has_sensitive_element or design_review_flag or has_vendor_scenario


def render_stride_stub(brd_output: BRDOutput) -> str:
    """Return a deterministic STRIDE stub block, or empty string when no trigger condition is met."""
    if not _stride_triggers(brd_output):
        return ""

    sections = [
        "**Spoofing.** Consider identity spoofing against the API. Mitigate with Cognito-issued tokens and API Gateway authorizer enforcement.",
        "**Tampering.** Consider payload tampering in transit and at rest. Mitigate with TLS 1.2 or higher and KMS-managed encryption for S3 and DynamoDB.",
        "**Repudiation.** Consider repudiation of user actions. Mitigate with CloudWatch Logs capturing request-level audit records.",
        "**Information disclosure.** Consider unintended exposure of Confidential data. Mitigate with least-privilege IAM, field-level access controls, and retention limits.",
        "**Denial of service.** Consider DoS against the API. Mitigate with API Gateway throttling and CloudFront edge caching.",
        "**Elevation of privilege.** Consider privilege escalation via token misuse. Mitigate with short-lived tokens, role separation, and scoped IAM policies.",
    ]

    return "## Threat Model (STRIDE Stub)\n\n" + "\n\n".join(sections)


def render_raci_matrix(brd_output: BRDOutput) -> list[RACIRow]:
    """Return a deterministic RACI matrix, or empty list when no trigger condition is met."""
    has_vendor_scenario = len(brd_output.vendor_scenarios_applied) >= 1
    design_review_flag = brd_output.privacy_considerations.design_review_flag

    if not (has_vendor_scenario or design_review_flag):
        return []

    stride_renders = _stride_triggers(brd_output)

    rows: list[RACIRow] = []
    for owner in GateOwner:
        row = RACIRow(role=owner.value)
        if owner is GateOwner.PM:
            row.accountable = True
        elif owner is GateOwner.TECH_LEAD:
            row.responsible = True
        elif owner is GateOwner.ENGINEER:
            row.responsible = True
        elif owner is GateOwner.LEGAL:
            if has_vendor_scenario:
                row.consulted = True
        elif owner is GateOwner.SECURITY:
            if stride_renders:
                row.consulted = True
        elif owner is GateOwner.PRIVACY:
            if design_review_flag:
                row.consulted = True

        if not (row.responsible or row.accountable or row.consulted):
            row.informed = True

        rows.append(row)

    return rows


def render_raci_matrix_markdown(rows: list[RACIRow]) -> str:
    """Return a markdown table of the RACI matrix, or empty string when rows is empty."""
    if not rows:
        return ""

    lines = [
        "## RACI Matrix",
        "",
        "| Role | Responsible | Accountable | Consulted | Informed |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        r = "x" if row.responsible else ""
        a = "x" if row.accountable else ""
        c = "x" if row.consulted else ""
        i = "x" if row.informed else ""
        lines.append(f"| {row.role} | {r} | {a} | {c} | {i} |")

    return "\n".join(lines)


# --- Narrow BRD markdown parser and build-spec augmentation helper ---


_CLASSIFICATION_BY_VALUE = {c.value: c for c in DataClassification}
# Pattern for "| name | classification | purpose |" rows in section 13.
_ELEMENT_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$")
_SCENARIOS_RE = re.compile(r"^Scenarios applied:\s*(.+?)\s*\.?\s*$", re.IGNORECASE)
_DESIGN_REVIEW_RE = re.compile(
    r"^\*\*Design review flag:\*\*\s*(true|false)\s*$", re.IGNORECASE
)


def _slice_section(markdown: str, heading: str, stop_prefix: str = "## ") -> str:
    """Return the lines under a specific ``## N. Title`` heading up to the next section.

    Returns an empty string when the heading is not present in the markdown.
    """
    lines = markdown.splitlines()
    start = -1
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i + 1
            break
    if start == -1:
        return ""
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith(stop_prefix):
            end = j
            break
    return "\n".join(lines[start:end])


def _parse_data_handling_elements(section_body: str) -> list[DataElement]:
    """Parse the section 13 elements table into DataElement instances.

    Silently skips rows with invalid or unknown classifications. Returns an
    empty list when the elements table is absent (for example, gap-flag case).
    """
    elements: list[DataElement] = []
    in_table = False
    for raw in section_body.splitlines():
        line = raw.rstrip()
        if not line:
            if in_table:
                break
            continue
        if not in_table:
            if line.startswith("| Element ") and "Classification" in line:
                in_table = True
                continue
            continue
        # Skip the header separator row (| --- | --- | --- |).
        if set(line.replace("|", "").replace(" ", "")) <= {"-"}:
            continue
        match = _ELEMENT_ROW_RE.match(line)
        if not match:
            break
        name, classification_value, purpose = match.groups()
        classification = _CLASSIFICATION_BY_VALUE.get(classification_value.strip())
        if classification is None:
            continue
        elements.append(
            DataElement(
                name=name.strip(),
                classification=classification,
                purpose=purpose.strip(),
            )
        )
    return elements


def _parse_vendor_scenarios(section_body: str) -> list[str]:
    """Extract the comma-separated ``Scenarios applied:`` list from section 14."""
    for raw in section_body.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _SCENARIOS_RE.match(line)
        if match:
            return [s.strip() for s in match.group(1).split(",") if s.strip()]
    return []


def _parse_design_review_flag(section_body: str) -> bool:
    """Extract the ``**Design review flag:** true|false`` value from section 15."""
    for raw in section_body.splitlines():
        match = _DESIGN_REVIEW_RE.match(raw.strip())
        if match:
            return match.group(1).lower() == "true"
    return False


def extract_brd_trigger_state(brd_markdown: str) -> BRDOutput:
    """Reconstruct a BRDOutput carrying only the three STRIDE and RACI trigger signals.

    The returned BRDOutput populates three fields read by the deterministic
    renderers:

    - ``data_handling_section.elements`` (classifications drive the STRIDE trigger)
    - ``privacy_considerations.design_review_flag`` (STRIDE and RACI trigger)
    - ``vendor_scenarios_applied`` (STRIDE and RACI trigger)

    The model is built via ``model_construct`` so the required fields on
    ``BRDOutput`` are not populated. The resulting instance is suitable ONLY
    for ``render_stride_stub`` and ``render_raci_matrix``. Do not pass it to
    ``render_brd_to_markdown`` or any other downstream consumer.

    Pre-feature BRD markdown that lacks sections 13 through 15 produces a
    BRDOutput with empty trigger fields, which naturally yields empty
    renderer output.
    """
    section_13 = _slice_section(brd_markdown, "## 13. Data Handling")
    section_14 = _slice_section(brd_markdown, "## 14. Vendor Considerations")
    section_15 = _slice_section(brd_markdown, "## 15. Privacy Considerations")

    elements = _parse_data_handling_elements(section_13) if section_13 else []
    vendor_scenarios = _parse_vendor_scenarios(section_14) if section_14 else []
    design_review_flag = (
        _parse_design_review_flag(section_15) if section_15 else False
    )

    return BRDOutput.model_construct(
        data_handling_section=DataHandlingSection(elements=elements),
        vendor_scenarios_applied=vendor_scenarios,
        privacy_considerations=PrivacyConsiderations(
            design_review_flag=design_review_flag
        ),
    )


def _augment_spec_with_stride_raci(
    spec: CodingPromptOutput, brd_output: BRDOutput
) -> None:
    """Populate stride_stub and raci_matrix deterministically, then append to
    spec.formatted_spec in a fixed order (STRIDE before RACI, both after the
    main body). Mutates spec in place. No-op when neither renderer produces
    content.
    """
    stride_md = render_stride_stub(brd_output)
    raci_rows = render_raci_matrix(brd_output)
    raci_md = render_raci_matrix_markdown(raci_rows)

    spec.stride_stub = stride_md
    spec.raci_matrix = raci_rows

    if stride_md:
        spec.formatted_spec = (
            spec.formatted_spec.rstrip() + "\n\n" + stride_md
        ).strip()
    if raci_md:
        spec.formatted_spec = (
            spec.formatted_spec.rstrip() + "\n\n" + raci_md
        ).strip()
