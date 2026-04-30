from typing import Optional

from pydantic import BaseModel, Field


class ReviewData(BaseModel):
    platform: str = Field(description="G2, Capterra, or TrustRadius")
    rating: str = Field(description="e.g., 4.7/5")
    review_count: str = Field(default="", description="e.g., 5,200+")
    source_url: str = Field(default="", description="Link to the review page if available")


class CompetitorAnalysis(BaseModel):
    name: str
    description: str
    strengths: list[str]
    weaknesses: list[str]
    relevance: str = Field(description="Why this competitor matters to the PM's problem")
    review_data: list[ReviewData] = Field(
        default_factory=list,
        description="Ratings from G2, Capterra, TrustRadius",
    )
    top_pros: list[str] = Field(
        default_factory=list,
        description="Recurring positive themes from user reviews",
    )
    top_cons: list[str] = Field(
        default_factory=list,
        description="Recurring negative themes / complaints from user reviews",
    )
    reviewer_roles: list[str] = Field(
        default_factory=list,
        description="Common roles of reviewers (e.g., Product Manager, Software Engineer)",
    )
    pricing_summary: str = Field(
        default="",
        description="Pricing tier info if available from review platforms",
    )


class CustomerQuote(BaseModel):
    quote: str
    source: str = Field(description="e.g., Dovetail, G2 Review, Reddit, analyst report")
    theme: str = Field(description="Which pain point or topic this relates to")
    attribution: Optional[str] = Field(default=None, description="Person/role if available")


class PainPoint(BaseModel):
    description: str
    severity: str = Field(
        description="High, medium, or low — described in context (e.g., 'high — mentioned in 8 of 12 transcripts')"
    )
    evidence_count: int = Field(description="Number of sources supporting this pain point")
    sources: list[str]


class MarketSizing(BaseModel):
    summary: str
    data_points: list[str] = Field(description="Each a specific stat with source attribution")
    sources: list[str]


class InternalStateAssessment(BaseModel):
    current_architecture_summary: str
    dependencies: list[str]
    what_needs_to_change: list[str]
    sources: list[str]


class ResearchOutput(BaseModel):
    """Structured research brief output from Agent 1.

    Consumed by Agent 2 (Narrative) directly via task context — no markdown
    parsing required. Also rendered to markdown for human review and
    publishing.
    """

    context: str = Field(description="1-3 sentences restating the problem as understood")

    executive_summary: str = Field(
        description="Top-line findings: what was validated, challenged, or surprising"
    )

    market_sizing: MarketSizing

    competitors: list[CompetitorAnalysis] = Field(
        default_factory=list,
        min_length=3, description="Minimum 3 competitors"
    )

    customer_evidence: list[CustomerQuote] = Field(default_factory=list)

    pain_points: list[PainPoint] = Field(default_factory=list)

    internal_state: Optional[InternalStateAssessment] = Field(
        default=None,
        description="Only present if internal context was provided in the input",
    )

    strategic_implications: str = Field(
        description="Factual summary of what data suggests, not recommendations"
    )

    gaps_and_limitations: list[str] = Field(
        default_factory=list,
        description="What couldn't be found or remains unvalidated"
    )

    sources: list[str] = Field(default_factory=list, description="All sources cited, for reference index")

    internal_sources: list[str] = Field(
        default_factory=list,
        description="Sources retrieved from internal MCP, separate from public sources",
    )
