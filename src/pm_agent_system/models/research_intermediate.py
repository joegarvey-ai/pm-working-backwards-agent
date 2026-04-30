"""Intermediate output models for the split research pipeline.

When the research phase is decomposed into three sequential tasks
(external research, customer evidence, synthesis), each task produces
a focused output that the synthesis task merges into the final
ResearchOutput.
"""

from pydantic import BaseModel, Field

from pm_agent_system.models.research_output import (
    CompetitorAnalysis,
    CustomerQuote,
    MarketSizing,
)


class ExternalResearchOutput(BaseModel):
    """Output from the external research task (Tavily + CompetitiveIntel).

    Contains market sizing and competitive landscape data. No customer
    evidence or internal context; those come from separate tasks.
    """

    market_sizing: MarketSizing
    competitors: list[CompetitorAnalysis] = Field(
        default_factory=list,
        description="3-5 competitors with review data, pros, cons, pricing",
    )
    external_sources: list[str] = Field(
        default_factory=list,
        description="All external sources cited in this output",
    )
    external_gaps: list[str] = Field(
        default_factory=list,
        description="Topics where external research found no data",
    )
    internal_findings: list[str] = Field(
        default_factory=list,
        description="Findings from internal Amazon systems (wiki, code search, Taskei, Quip)",
    )


class CustomerEvidenceOutput(BaseModel):
    """Output from the customer evidence task (Dovetail only).

    Contains direct customer quotes and findings from the Dovetail
    workspace. Gaps note topics where Dovetail had no relevant content.
    """

    customer_evidence: list[CustomerQuote] = Field(
        default_factory=list,
        description="Direct quotes and findings from Dovetail workspace",
    )
    dovetail_sources: list[str] = Field(
        default_factory=list,
        description="Dovetail projects and insights referenced",
    )
    dovetail_gaps: list[str] = Field(
        default_factory=list,
        description="Topics the Dovetail search could not cover",
    )
