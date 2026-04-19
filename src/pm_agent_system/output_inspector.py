"""Detect silently incomplete artifacts from defaulted empty fields.

When Pydantic model fields have ``default_factory=list`` or ``default=""``,
a truncated LLM response can produce a technically valid model with empty
sections. This module detects that pattern and provides human-readable
warnings for renderers.
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic.fields import FieldInfo


# Map internal field names to human-readable section names.
# Keep this close to the model definitions for maintainability.
FIELD_DISPLAY_NAMES: dict[str, str] = {
    # ResearchOutput
    "competitors": "Competitive Landscape",
    "customer_evidence": "Customer Evidence",
    "pain_points": "Pain Points",
    "gaps_and_limitations": "Gaps and Limitations",
    "sources": "Sources",
    # PRFAQOutput
    "external_faqs": "External FAQs",
    "internal_faqs": "Internal FAQs",
    "appendix_data_points": "Appendix Data Points",
    "appendix_competitor_table": "Appendix Competitor Table",
    "appendix_customer_quotes": "Appendix Customer Quotes",
    "appendix_gaps": "Appendix Gaps",
    "version_history": "Version History",
    # BRDOutput
    "user_stories": "User Stories",
    "functional_requirements": "Functional Requirements",
    "non_functional_requirements": "Non-Functional Requirements (NFRs)",
    "cost_flags": "Cost Flags",
    "risks": "Risks",
    "success_metrics": "Success Metrics",
    "timeline_and_milestones": "Timeline & Milestones",
    "technical_context_and_dependencies": "Technical Context & Dependencies",
    # DesignBriefOutput
    "accessibility_considerations": "Accessibility",
    "platform_targets": "Platform Targets",
    # CodingPromptOutput
    "user_flows": "User Flows",
    "feature_specs": "Feature Specs",
    "technical_constraints": "Technical Constraints",
    "architecture_reference": "Architecture Reference",
    "current_state_context": "Current State Context",
    "out_of_scope": "Out of Scope",
    "formatted_spec": "Formatted Spec",
}


def _has_default(field_info: FieldInfo) -> bool:
    """Check if a field was declared with a default or default_factory."""
    if field_info.default is not None and field_info.default != ...:
        return True
    if field_info.default_factory is not None:
        return True
    return False


def _is_empty(value) -> bool:
    """Check if a value is empty ([], "", or None)."""
    if value is None:
        return True
    if isinstance(value, str) and value == "":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False


def find_defaulted_empty_fields(model_instance: BaseModel) -> list[str]:
    """Return field names that are both declared with a default and currently empty.

    Used to detect silently incomplete artifacts where the LLM response was
    truncated and Pydantic filled in defaults.
    """
    empty_fields = []
    for field_name, field_info in type(model_instance).model_fields.items():
        if _has_default(field_info):
            value = getattr(model_instance, field_name, None)
            if _is_empty(value):
                empty_fields.append(field_name)
    return empty_fields


def format_warning_block(empty_fields: list[str]) -> str:
    """Format a markdown warning block for empty defaulted fields.

    Returns an empty string if there are no empty fields.
    """
    if not empty_fields:
        return ""

    display_names = [
        FIELD_DISPLAY_NAMES.get(f, f.replace("_", " ").title())
        for f in empty_fields
    ]
    names_str = ", ".join(f"**{n}**" for n in display_names)

    return (
        f"> **\u26a0 Incomplete output detected.** The following sections were not "
        f"generated and may require a re-run or manual completion: {names_str}.\n"
        f">\n"
        f"> This usually means the model response was truncated. Consider re-running "
        f"this agent, or see `docs/troubleshooting.md`.\n"
    )
