from typing import Any

from pydantic import BaseModel, Field

from pm_agent_system.models.compliance_primitives import DataClassification
from pm_agent_system.models.research_output import CustomerQuote


class FAQ(BaseModel):
    question: str
    answer: str
    audience: str = Field(description='"external" or "internal"')


class VersionEntry(BaseModel):
    version: str = Field(description='Semantic version like "1.0", "1.1"')
    date: str
    author: str = Field(description='"Agent 2" or PM name')
    changes: str


class PRFAQDataElement(BaseModel):
    """A data element referenced in the PRFAQ data handling summary."""

    name: str
    classification: DataClassification
    purpose: str = ""


class PRFAQDataHandling(BaseModel):
    """Data handling summary surfaced in the PRFAQ with optional gap flagging."""

    elements: list[PRFAQDataElement] = Field(default_factory=list)
    gap_flag: bool = False
    gap_notes: list[str] = Field(default_factory=list)


class PRFAQOutput(BaseModel):
    press_release: str = Field(
        description="Future-state announcement, 300-500 words, written as if "
        "the product has already launched. Includes a fictional customer quote "
        "grounded in real evidence."
    )
    external_faqs: list[FAQ] = Field(default_factory=list, min_length=3)
    internal_faqs: list[FAQ] = Field(
        default_factory=list,
        min_length=5,
        description="Stakeholder-facing FAQs. MUST include a strategy question "
        "answered using the diagnosis / guiding policy / coherent actions "
        "framework, and MUST address risks honestly when the source research "
        "had gaps.",
    )
    customer_experience_narrative: str = Field(
        description="1-2 page end-to-end user experience story. Present tense, "
        "third person. Specific enough that a designer could sketch from it."
    )
    appendix_data_points: list[str] = Field(
        default_factory=list,
        description="Key facts and metrics from the research, each with an "
        "inline [source](url) citation."
    )
    appendix_competitor_table: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Competitor comparison rows. Each dict should include at "
        "minimum: name, positioning, key_features, pricing (if known), source."
    )
    appendix_customer_quotes: list[CustomerQuote] = Field(default_factory=list)
    appendix_gaps: list[str] = Field(
        default_factory=list,
        description="Open questions and unvalidated assumptions carried over "
        "from research, plus any new gaps surfaced while drafting."
    )
    version_history: list[VersionEntry] = Field(
        default_factory=list,
        description='Version history entries. Each should include version, date, author, and changes.'
    )
    data_handling: PRFAQDataHandling = Field(default_factory=PRFAQDataHandling)
