from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from pm_agent_system.models import (
    BRDOutput,
    CodingPromptOutput,
    CustomerEvidenceOutput,
    DesignBriefOutput,
    ExternalResearchOutput,
    PRFAQOutput,
    ResearchOutput,
)
from pm_agent_system.models.build_spec_intermediate import (
    BuildSpecStructureOutput,
    FormattedSpecOutput,
)
from pm_agent_system.models.brd_intermediate import (
    BRDCostRiskOutput,
    BRDStructureOutput,
)
from pm_agent_system.tools import (
    AWSDocsReadTool,
    AWSDocsSearchTool,
    AWSPricingTool,
    CompetitiveIntelTool,
    DovetailSearchTool,
    FileReaderTool,
    ObsidianReadTool,
    ObsidianSearchTool,
    PriorArtSearchTool,
    RequirementsReaderTool,
    StyleGuideLoaderTool,
    TavilySearchTool,
)
import os

from crewai.llms.providers.anthropic.completion import AnthropicCompletion

# ---------- LLM provider selection ----------
#
# Set LLM_PROVIDER=bedrock in .env to route LLM calls through AWS Bedrock
# using the AWS_BEARER_TOKEN_BEDROCK env var. Leave unset (or set to
# "anthropic") to use the direct Anthropic API with ANTHROPIC_API_KEY.
#
# Bedrock-specific env vars:
#   AWS_BEARER_TOKEN_BEDROCK  the Bedrock API key (bearer token)
#   AWS_BEDROCK_REGION        region where Bedrock is enabled (e.g. us-east-2)
#   BEDROCK_MODEL_ID          inference profile ID (e.g. us.anthropic.claude-sonnet-4-6)
#
# Claude Sonnet 4.6 on Bedrock requires the US cross-region inference
# profile, prefixed with "us." or "global.". If the user sets a plain
# model ID without the prefix, we auto-prepend "us." so on-demand
# invocation works.
_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()

_MODEL_ANTHROPIC = "claude-sonnet-4-20250514"
_MODEL_BEDROCK = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6").strip()
if _MODEL_BEDROCK and not _MODEL_BEDROCK.startswith(("us.", "global.", "eu.", "apac.")):
    _MODEL_BEDROCK = f"us.{_MODEL_BEDROCK}"

# _MODEL is the canonical identifier used by checkpoint and pricing code.
_MODEL = _MODEL_BEDROCK if _LLM_PROVIDER == "bedrock" else _MODEL_ANTHROPIC

_DEFAULT_MAX_TOKENS = 8192
_LARGE_MAX_TOKENS = 32768


def _llm(max_tokens: int = _DEFAULT_MAX_TOKENS):
    """Return an LLM instance based on the configured provider.

    Bedrock uses the AWS_BEARER_TOKEN_BEDROCK env var picked up by boto3's
    standard credential chain. Anthropic uses ANTHROPIC_API_KEY.
    """
    if _LLM_PROVIDER == "bedrock":
        from crewai.llms.providers.bedrock.completion import BedrockCompletion
        return BedrockCompletion(
            model=_MODEL_BEDROCK,
            max_tokens=max_tokens,
            region_name=os.getenv("AWS_BEDROCK_REGION")
                        or os.getenv("AWS_REGION", "us-east-2"),
            stream=False,
        )
    return AnthropicCompletion(model=_MODEL_ANTHROPIC, max_tokens=max_tokens)


@CrewBase
class PmAgentSystem:
    """PM Agent System crew.

    Four agents are scaffolded:
      - Agent 1: Research Agent (research_task)
      - Agent 2: PRFAQ Agent (generate_prfaq, revise_prfaq)
      - Agent 3: Design Brief + Wireframe Agent (generate_design_brief,
        revise_design_brief). SVG wireframe generation is stubbed.
      - Agent 4: BRD + Build Spec Agent (generate_brd, revise_brd,
        generate_build_spec)

    Multiple crew builders compose subsets of agents/tasks for the
    different operating modes (research-only, full pipeline, BRD-only,
    revisions, etc.).
    """

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    # ---------- Agents ----------

    @agent
    def research_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["research_agent"],  # type: ignore[index]
            tools=[
                TavilySearchTool(),
                CompetitiveIntelTool(),
                DovetailSearchTool(),
                FileReaderTool(),
                PriorArtSearchTool(),
                ObsidianSearchTool(),
                ObsidianReadTool(),
            ],
            llm=_llm(_LARGE_MAX_TOKENS),
            verbose=True,
        )

    @agent
    def prfaq_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["prfaq_agent"],  # type: ignore[index]
            tools=[
                FileReaderTool(),
                StyleGuideLoaderTool(),
                ObsidianSearchTool(),
                ObsidianReadTool(),
            ],
            llm=_llm(_LARGE_MAX_TOKENS),
            verbose=True,
        )

    @agent
    def design_brief_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["design_brief_agent"],  # type: ignore[index]
            tools=[
                FileReaderTool(),
                ObsidianSearchTool(),
                ObsidianReadTool(),
            ],
            llm=_llm(_LARGE_MAX_TOKENS),
            verbose=True,
        )

    @agent
    def brd_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["brd_agent"],  # type: ignore[index]
            tools=[
                TavilySearchTool(),
                AWSPricingTool(),
                AWSDocsSearchTool(),
                AWSDocsReadTool(),
                FileReaderTool(),
                RequirementsReaderTool(),
                StyleGuideLoaderTool(),
                ObsidianSearchTool(),
                ObsidianReadTool(),
            ],
            llm=_llm(_LARGE_MAX_TOKENS),
            verbose=True,
        )

    # ---------- Tasks ----------

    @task
    def validate_input(self) -> Task:
        return Task(
            config=self.tasks_config["validate_input"],  # type: ignore[index]
            name="validate_input",
        )

    @task
    def research_task(self) -> Task:
        return Task(
            config=self.tasks_config["research_task"],  # type: ignore[index]
            output_pydantic=ResearchOutput,
            name="research_task",
        )

    @task
    def generate_prfaq(self) -> Task:
        return Task(
            config=self.tasks_config["generate_prfaq"],  # type: ignore[index]
            output_pydantic=PRFAQOutput,
            context=[self.research_task()],
            name="generate_prfaq",
        )

    @task
    def revise_prfaq(self) -> Task:
        return Task(
            config=self.tasks_config["revise_prfaq"],  # type: ignore[index]
            output_pydantic=PRFAQOutput,
            name="revise_prfaq",
        )

    @task
    def generate_design_brief(self) -> Task:
        return Task(
            config=self.tasks_config["generate_design_brief"],  # type: ignore[index]
            output_pydantic=DesignBriefOutput,
            name="generate_design_brief",
        )

    @task
    def revise_design_brief(self) -> Task:
        return Task(
            config=self.tasks_config["revise_design_brief"],  # type: ignore[index]
            output_pydantic=DesignBriefOutput,
            name="revise_design_brief",
        )

    @task
    def generate_brd_chained(self) -> Task:
        return Task(
            config=self.tasks_config["generate_brd_chained"],  # type: ignore[index]
            output_pydantic=BRDOutput,
            context=[self.research_task(), self.generate_prfaq()],
            name="generate_brd_chained",
        )

    @task
    def generate_brd_standalone(self) -> Task:
        return Task(
            config=self.tasks_config["generate_brd_standalone"],  # type: ignore[index]
            output_pydantic=BRDOutput,
            name="generate_brd_standalone",
        )

    @task
    def revise_brd(self) -> Task:
        return Task(
            config=self.tasks_config["revise_brd"],  # type: ignore[index]
            output_pydantic=BRDOutput,
            name="revise_brd",
        )

    @task
    def generate_build_spec_chained(self) -> Task:
        return Task(
            config=self.tasks_config["generate_build_spec_chained"],  # type: ignore[index]
            output_pydantic=CodingPromptOutput,
            context=[self.generate_brd_chained()],
            name="generate_build_spec_chained",
        )

    @task
    def generate_build_spec_standalone(self) -> Task:
        return Task(
            config=self.tasks_config["generate_build_spec_standalone"],  # type: ignore[index]
            output_pydantic=CodingPromptOutput,
            name="generate_build_spec_standalone",
        )

    # ---------- Crews ----------

    def _research_tasks(self, skip_validation: bool = False) -> list[Task]:
        """Build the research task list, optionally prepending validate_input.

        Uses the split three-task architecture by default: external research
        (Tavily + CompetitiveIntel), customer evidence (Dovetail only), then
        synthesis (no tools, merges both into ResearchOutput).
        """
        tasks: list[Task] = []

        if not skip_validation:
            tasks.append(self.validate_input())

        # Task 1: External research (Tavily + CompetitiveIntel only)
        external_task = Task(
            config=self.tasks_config["external_research_task"],  # type: ignore[index]
            output_pydantic=ExternalResearchOutput,
            context=tasks[-1:] if tasks else [],  # context from validation if present
            name="external_research_task",
        )
        tasks.append(external_task)

        # Task 2: Customer evidence (Dovetail only)
        evidence_task = Task(
            config=self.tasks_config["customer_evidence_task"],  # type: ignore[index]
            output_pydantic=CustomerEvidenceOutput,
            name="customer_evidence_task",
        )
        tasks.append(evidence_task)

        # Task 3: Synthesis (no tools, merges both into ResearchOutput)
        synthesis_task = Task(
            config=self.tasks_config["research_synthesis_task"],  # type: ignore[index]
            output_pydantic=ResearchOutput,
            context=[external_task, evidence_task],
            name="research_synthesis_task",
        )
        tasks.append(synthesis_task)

        return tasks

    @crew
    def crew(self) -> Crew:
        """Default research-only crew (Agent 1). Preserves Phase 2 behavior."""
        return Crew(
            agents=[self.research_agent()],
            tasks=[self.research_task()],
            process=Process.sequential,
            verbose=True,
        )

    def research_crew(self, skip_validation: bool = False) -> Crew:
        """Research-only crew with optional validation step."""
        tasks = self._research_tasks(skip_validation)
        return Crew(
            agents=[self.research_agent()],
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

    def research_and_generate_crew(self, skip_validation: bool = False) -> Crew:
        """Agent 1 → Agent 2 generate (PRFAQ Mode 1)."""
        tasks = self._research_tasks(skip_validation)
        prfaq_task = Task(
            config=self.tasks_config["generate_prfaq"],  # type: ignore[index]
            output_pydantic=PRFAQOutput,
            context=[tasks[-1]],  # research_task is always last
        )
        tasks.append(prfaq_task)
        return Crew(
            agents=[self.research_agent(), self.prfaq_agent()],
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

    def revise_prfaq_crew(self) -> Crew:
        """Agent 2 only (PRFAQ Mode 2)."""
        return Crew(
            agents=[self.prfaq_agent()],
            tasks=[self.revise_prfaq()],
            process=Process.sequential,
            verbose=True,
        )

    def design_brief_crew(self) -> Crew:
        """Agent 3 only — generate a design brief from an approved PRFAQ on disk."""
        return Crew(
            agents=[self.design_brief_agent()],
            tasks=[self.generate_design_brief()],
            process=Process.sequential,
            verbose=True,
        )

    def revise_design_brief_crew(self) -> Crew:
        """Agent 3 only — revise an existing design brief."""
        return Crew(
            agents=[self.design_brief_agent()],
            tasks=[self.revise_design_brief()],
            process=Process.sequential,
            verbose=True,
        )

    def full_pipeline_crew(
        self, skip_validation: bool = False, skip_design: bool = False
    ) -> Crew:
        """Agent 1 → Agent 2 → Agent 3 (optional) → Agent 4.

        When ``skip_design`` is True, Agent 3 is omitted and the pipeline
        matches the original three-agent behavior exactly.
        """
        tasks = self._research_tasks(skip_validation)
        research = tasks[-1]
        prfaq_task = Task(
            config=self.tasks_config["generate_prfaq"],  # type: ignore[index]
            output_pydantic=PRFAQOutput,
            context=[research],
        )

        design_task: Task | None = None
        if not skip_design:
            design_task = Task(
                config=self.tasks_config["generate_design_brief"],  # type: ignore[index]
                output_pydantic=DesignBriefOutput,
                context=[research, prfaq_task],
            )

        brd_context = [research, prfaq_task]
        if design_task is not None:
            brd_context.append(design_task)
        brd_task = Task(
            config=self.tasks_config["generate_brd_chained"],  # type: ignore[index]
            output_pydantic=BRDOutput,
            context=brd_context,
        )
        spec_task = Task(
            config=self.tasks_config["generate_build_spec_chained"],  # type: ignore[index]
            output_pydantic=CodingPromptOutput,
            context=[brd_task],
        )

        tasks.append(prfaq_task)
        agents_list = [self.research_agent(), self.prfaq_agent()]
        if design_task is not None:
            tasks.append(design_task)
            agents_list.append(self.design_brief_agent())
        tasks.extend([brd_task, spec_task])
        agents_list.append(self.brd_agent())

        return Crew(
            agents=agents_list,
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

    def brd_from_prfaq_crew(self) -> Crew:
        """Agent 4 only — generate BRD then build spec from approved PRFAQ on disk.

        Both tasks are constructed without prior-task context; the agent
        reads the PRFAQ and research from disk via file_reader using the
        paths passed in via inputs.
        """
        brd_task = self.generate_brd_standalone()
        spec_task = Task(
            config=self.tasks_config["generate_build_spec_chained"],  # type: ignore[index]
            output_pydantic=CodingPromptOutput,
            context=[brd_task],
        )
        return Crew(
            agents=[self.brd_agent()],
            tasks=[brd_task, spec_task],
            process=Process.sequential,
            verbose=True,
        )

    def split_brd_crew(self) -> Crew:
        """Agent 4 only — three-task split BRD from approved PRFAQ on disk.

        Task 1: produce BRDStructureOutput (prose, user stories, requirements).
        Task 2: produce BRDCostRiskOutput (cost flags, risks, metrics).
        Task 3: merge both into final BRDOutput.
        Avoids Bedrock read timeouts by keeping each task under 16K tokens.
        """
        structure_task = Task(
            config=self.tasks_config["brd_structure_task"],  # type: ignore[index]
            output_pydantic=BRDStructureOutput,
            name="brd_structure_task",
        )
        cost_risk_task = Task(
            config=self.tasks_config["brd_cost_risk_task"],  # type: ignore[index]
            output_pydantic=BRDCostRiskOutput,
            context=[structure_task],
            name="brd_cost_risk_task",
        )
        assembly_task = Task(
            config=self.tasks_config["brd_assembly_task"],  # type: ignore[index]
            output_pydantic=BRDOutput,
            context=[structure_task, cost_risk_task],
            name="brd_assembly_task",
        )
        return Crew(
            agents=[self.brd_agent()],
            tasks=[structure_task, cost_risk_task, assembly_task],
            process=Process.sequential,
            verbose=True,
        )

    def revise_brd_crew(self) -> Crew:
        """Agent 4 only (BRD revision Mode 2)."""
        return Crew(
            agents=[self.brd_agent()],
            tasks=[self.revise_brd()],
            process=Process.sequential,
            verbose=True,
        )

    def regenerate_build_spec_crew(self) -> Crew:
        """Agent 4 only — regenerate build spec from approved BRD on disk (Mode 3)."""
        return Crew(
            agents=[self.brd_agent()],
            tasks=[self.generate_build_spec_standalone()],
            process=Process.sequential,
            verbose=True,
        )

    def split_build_spec_crew(self) -> Crew:
        """Agent 4 only — two-task split build spec from approved BRD on disk.

        Task 1: produce BuildSpecStructureOutput (everything except formatted_spec).
        Task 2: produce FormattedSpecOutput (just the formatted_spec string).
        Avoids Bedrock read timeouts by keeping each task under 16K tokens.
        """
        structure_task = Task(
            config=self.tasks_config["build_spec_structure_standalone"],  # type: ignore[index]
            output_pydantic=BuildSpecStructureOutput,
            name="build_spec_structure_task",
        )
        format_task = Task(
            config=self.tasks_config["format_spec_standalone"],  # type: ignore[index]
            output_pydantic=FormattedSpecOutput,
            context=[structure_task],
            name="format_spec_task",
        )
        return Crew(
            agents=[self.brd_agent()],
            tasks=[structure_task, format_task],
            process=Process.sequential,
            verbose=True,
        )
