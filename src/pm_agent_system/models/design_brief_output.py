from pydantic import BaseModel, Field


class ScreenEntry(BaseModel):
    name: str
    purpose: str
    primary_flow: str
    source_section: str = Field(
        description="PRFAQ section reference for traceability (e.g. 'Customer Experience Narrative, onboarding paragraph')."
    )


class DesignFlowStep(BaseModel):
    step_number: int
    user_action: str
    system_response: str
    screen: str = Field(description="Which screen from the screen inventory this step occurs on")


class DesignUserFlow(BaseModel):
    name: str
    priority: str = Field(description="core | onboarding | secondary")
    steps: list[DesignFlowStep] = Field(min_length=1)
    related_screens: list[str] = Field(default_factory=list)


class DesignBriefOutput(BaseModel):
    product_overview: str
    screen_inventory: list[ScreenEntry] = Field(min_length=2)
    user_flows: list[DesignUserFlow] = Field(min_length=1)
    design_principles: list[str] = Field(min_length=3, max_length=5)
    competitive_ui_patterns: str
    brand_style_context: str
    accessibility_considerations: str = Field(default="")
    platform_targets: list[str] = Field(
        default_factory=list,
        description='Platform targets like ["web", "mobile", "tablet"].',
    )
    style_guide_used: bool = Field(
        default=False,
        description="True if a visual style guide was loaded and applied while drafting.",
    )
