from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from pm_agent_system.models import (
    BRDOutput,
    CodingPromptOutput,
    CustomerEvidenceOutput,
    DesignBriefOutput,
    ExternalResearchOutput,
    FeedbackClassification,
    PRFAQOutput,
    ResearchOutput,
)
from pm_agent_system.models.build_spec_intermediate import (
    BuildSpecStructureOutput,
    FormattedSpecOutput,
)
from pm_agent_system.models.brd_intermediate import (
    BRDComplianceOutput,
    BRDCostRiskOutput,
    BRDStructureOutput,
)
from pm_agent_system.tools import (
    AWSDocsReadTool,
    AWSDocsSearchTool,
    AWSPricingTool,
    BuilderMCPTool,
    CompetitiveIntelTool,
    DovetailSearchTool,
    FileReaderTool,
    ObsidianReadTool,
    ObsidianSearchTool,
    OutlookMCPTool,
    PriorArtSearchTool,
    RequirementsReaderTool,
    StyleGuideLoaderTool,
    TavilySearchTool,
)
import logging
import os
from pathlib import Path

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


def _llm(max_tokens: int = _DEFAULT_MAX_TOKENS, agent_key: str = ""):
    """Return an LLM instance based on the configured provider.

    When MODEL_ROUTING_ENABLED=true and agent_key is provided, routes
    to the appropriate model tier (opus/sonnet/haiku) via the
    orchestration module. Otherwise returns the default Sonnet model.

    Bedrock uses the AWS_BEARER_TOKEN_BEDROCK env var picked up by boto3's
    standard credential chain. Anthropic uses ANTHROPIC_API_KEY.
    """
    from pm_agent_system.orchestration import is_routing_enabled, routed_llm

    if agent_key and is_routing_enabled():
        return routed_llm(agent_key, max_tokens=max_tokens)

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


logger = logging.getLogger(__name__)


def _builder_mcp_enabled() -> bool:
    """True when builder-mcp auth material is present."""
    if os.getenv("BUILDER_MCP_TOKEN", "").strip():
        return True
    cookie_path = os.getenv("MIDWAY_COOKIE_PATH", "").strip()
    if cookie_path and Path(cookie_path).exists():
        return True
    return False


def _outlook_mcp_enabled() -> bool:
    """True when outlook-mcp auth material is present."""
    if os.getenv("OUTLOOK_MCP_TOKEN", "").strip():
        return True
    cookie_path = os.getenv("MIDWAY_COOKIE_PATH", "").strip()
    if cookie_path and Path(cookie_path).exists():
        return True
    return False


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

    def __init__(self, *args, **kwargs):
        # Note: do not call super().__init__() here. CrewBaseMeta's
        # __call__ handles instance initialization. Calling super()
        # triggers a TypeError in CrewAI 1.14+ because the metaclass
        # changes the class hierarchy.
        _dovetail = "enabled" if os.getenv("DOVETAIL_API_TOKEN", "").strip() else "disabled"
        _builder = "enabled" if _builder_mcp_enabled() else "disabled"
        _outlook = "enabled" if _outlook_mcp_enabled() else "disabled"
        logger.info(
            "Optional integrations: builder_mcp=%s, outlook_mcp=%s, dovetail=%s",
            _builder,
            _outlook,
            _dovetail,
        )

    # ---------- Agents ----------

    @agent
    def research_agent(self) -> Agent:
        """Synthesis agent: merges external research and customer evidence.

        This agent has no tools by design because the research_synthesis_task
        operates only on prior-task outputs passed via context, and the task
        description explicitly tells the agent it has no tools. The legacy
        name is preserved for backward compatibility with callers that
        reference it.
        """
        return Agent(
            config=self.agents_config["research_agent"],  # type: ignore[index]
            tools=[],
            llm=_llm(_LARGE_MAX_TOKENS, agent_key="research_agent"),
            verbose=True,
        )

    @agent
    def external_research_agent(self) -> Agent:
        """External market research agent (Tavily + CompetitiveIntel only).

        Isolated from other research agents so that async_execution=True
        does not interleave tool-use/tool-result messages across agents.
        """
        tools: list = [
            TavilySearchTool(),
            CompetitiveIntelTool(),
            FileReaderTool(),
            PriorArtSearchTool(),
            ObsidianSearchTool(),
            ObsidianReadTool(),
        ]
        if _builder_mcp_enabled():
            tools.append(BuilderMCPTool())
        return Agent(
            config=self.agents_config["external_research_agent"],  # type: ignore[index]
            tools=tools,
            llm=_llm(_LARGE_MAX_TOKENS, agent_key="external_research_agent"),
            verbose=True,
        )

    @agent
    def customer_evidence_agent(self) -> Agent:
        """Customer evidence research agent (Dovetail only).

        Isolated from other research agents so that async_execution=True
        does not interleave tool-use/tool-result messages across agents.
        """
        return Agent(
            config=self.agents_config["customer_evidence_agent"],  # type: ignore[index]
            tools=[
                DovetailSearchTool(),
            ],
            llm=_llm(_LARGE_MAX_TOKENS, agent_key="customer_evidence_agent"),
            verbose=True,
        )

    @agent
    def prfaq_agent(self) -> Agent:
        tools: list = [
            FileReaderTool(),
            StyleGuideLoaderTool(),
            ObsidianSearchTool(),
            ObsidianReadTool(),
        ]
        if _outlook_mcp_enabled():
            tools.append(OutlookMCPTool())
        return Agent(
            config=self.agents_config["prfaq_agent"],  # type: ignore[index]
            tools=tools,
            llm=_llm(_LARGE_MAX_TOKENS, agent_key="prfaq_agent"),
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
            llm=_llm(_LARGE_MAX_TOKENS, agent_key="design_brief_agent"),
            verbose=True,
        )

    @agent
    def brd_agent(self) -> Agent:
        tools: list = [
            TavilySearchTool(),
            AWSPricingTool(),
            AWSDocsSearchTool(),
            AWSDocsReadTool(),
            FileReaderTool(),
            RequirementsReaderTool(),
            StyleGuideLoaderTool(),
            ObsidianSearchTool(),
            ObsidianReadTool(),
        ]
        if _builder_mcp_enabled():
            tools.append(BuilderMCPTool())
        if _outlook_mcp_enabled():
            tools.append(OutlookMCPTool())
        return Agent(
            config=self.agents_config["brd_agent"],  # type: ignore[index]
            tools=tools,
            llm=_llm(_LARGE_MAX_TOKENS, agent_key="brd_agent"),
            verbose=True,
        )

    @agent
    def brd_cost_risk_agent(self) -> Agent:
        """Cost and risk specialist for the split BRD pipeline.

        Runs in parallel with brd_agent on the structure task. Isolated
        tool set and conversation state so that concurrent tool-use /
        tool-result messages do not conflict (same pattern as 4A).

        Tool set is narrow: Tavily and AWS pricing for cost lookups,
        AWS docs for service reference, file_reader to read PRFAQ and
        research from disk (since this task runs in parallel with
        structure, it cannot reach them via task context).
        """
        return Agent(
            config=self.agents_config["brd_cost_risk_agent"],  # type: ignore[index]
            tools=[
                TavilySearchTool(),
                AWSPricingTool(),
                AWSDocsSearchTool(),
                AWSDocsReadTool(),
                FileReaderTool(),
            ],
            llm=_llm(_LARGE_MAX_TOKENS, agent_key="brd_cost_risk_agent"),
            verbose=True,
        )

    @agent
    def brd_compliance_agent(self) -> Agent:
        """Compliance specialist for the split BRD pipeline.

        Runs as a third async sibling alongside brd_agent (structure)
        and brd_cost_risk_agent (cost_risk). Isolated tool set and
        conversation state so that concurrent tool-use / tool-result
        messages do not conflict under async_execution.

        Tool set is narrow: FileReaderTool is required for reading the
        PRFAQ and research from disk, since this task runs in parallel
        with structure and cannot reach them via task context.
        TavilySearchTool is used for privacy-regulation lookups and is
        only attached when TAVILY_API_KEY is present in the environment;
        any skipped lookups are recorded as gaps. This agent does not
        use Dovetail, AWS pricing, or AWS docs.
        """
        tools: list = [FileReaderTool()]
        if os.getenv("TAVILY_API_KEY"):
            tools.append(TavilySearchTool())
        return Agent(
            config=self.agents_config["brd_compliance_agent"],  # type: ignore[index]
            tools=tools,
            llm=_llm(_LARGE_MAX_TOKENS, agent_key="brd_compliance_agent"),
            verbose=True,
        )

    @agent
    def brd_assembly_agent(self) -> Agent:
        """No-tools assembly specialist for the split BRD pipeline.

        Merges three typed intermediates (structure, cost-risk,
        compliance) into a single BRDOutput. This agent carries an
        empty tool list on purpose, mirroring the research_agent
        synthesis pattern: the three intermediates arrive via task
        context, so no tool call is needed to produce the merged
        output. A dedicated no-tools agent keeps conversation state
        minimal, avoids reusing the tool-bearing brd_agent for a pure
        merge, and protects latency as intermediate sizes grow.
        """
        return Agent(
            config=self.agents_config["brd_assembly_agent"],  # type: ignore[index]
            tools=[],
            llm=_llm(_LARGE_MAX_TOKENS, agent_key="brd_assembly_agent"),
            verbose=True,
        )

    @agent
    def feedback_classifier_agent(self) -> Agent:
        """Stakeholder feedback routing specialist (Wave 2).

        Reads a single feedback item plus short summaries of each
        current artifact, returns a FeedbackClassification with affected
        artifacts, contradictions, and research gaps. Does not revise
        content; only classifies.

        Narrow tool set: file_reader only. No Tavily, Dovetail, or
        style guide loader. The summaries are pre-computed by the
        caller and passed in via task inputs, so the classifier does
        not need to fetch anything.
        """
        # Smaller max_tokens because classifier output is a compact JSON
        # blob (rarely more than a few hundred tokens).
        return Agent(
            config=self.agents_config["feedback_classifier_agent"],  # type: ignore[index]
            tools=[
                FileReaderTool(),
            ],
            llm=_llm(_DEFAULT_MAX_TOKENS, agent_key="feedback_classifier_agent"),
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
        # async_execution=True: runs in parallel with customer_evidence_task.
        # Assigned to a dedicated agent (external_research_agent) so that
        # concurrent tool-use/tool-result messages do not conflict with
        # the customer_evidence_agent's conversation state.
        external_task = Task(
            config=self.tasks_config["external_research_task"],  # type: ignore[index]
            output_pydantic=ExternalResearchOutput,
            context=tasks[-1:] if tasks else [],  # context from validation if present
            name="external_research_task",
            agent=self.external_research_agent(),
            async_execution=True,
        )
        tasks.append(external_task)

        # Task 2: Customer evidence (Dovetail only)
        # async_execution=True: runs in parallel with external_research_task.
        evidence_task = Task(
            config=self.tasks_config["customer_evidence_task"],  # type: ignore[index]
            output_pydantic=CustomerEvidenceOutput,
            name="customer_evidence_task",
            agent=self.customer_evidence_agent(),
            async_execution=True,
        )
        tasks.append(evidence_task)

        # Task 3: Synthesis (no tools, merges both into ResearchOutput)
        # CrewAI auto-joins: this task waits for both async predecessors.
        synthesis_task = Task(
            config=self.tasks_config["research_synthesis_task"],  # type: ignore[index]
            output_pydantic=ResearchOutput,
            context=[external_task, evidence_task],
            name="research_synthesis_task",
            agent=self.research_agent(),
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
            agents=[
                self.external_research_agent(),
                self.customer_evidence_agent(),
                self.research_agent(),
            ],
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
            name="generate_prfaq",
        )
        tasks.append(prfaq_task)
        return Crew(
            agents=[
                self.external_research_agent(),
                self.customer_evidence_agent(),
                self.research_agent(),
                self.prfaq_agent(),
            ],
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
        self,
        skip_validation: bool = False,
        skip_design: bool = False,
        sequential_brd: bool = False,
    ) -> Crew:
        """Agent 1 → Agent 2 → Agent 3 (optional) → Agent 4 split.

        When ``skip_design`` is True, Agent 3 is omitted and the pipeline
        matches the original three-agent behavior exactly.

        When ``sequential_brd`` is True, BRD structure/cost_risk/compliance
        run sequentially instead of in parallel. Slower (~2min extra) but
        eliminates the Bedrock toolResult interleaving race condition.

        BRD uses the split topology (structure + cost_risk in parallel,
        then assembly) to shave wall-clock time off the biggest stage.
        """
        tasks = self._research_tasks(skip_validation)
        research = tasks[-1]
        prfaq_task = Task(
            config=self.tasks_config["generate_prfaq"],  # type: ignore[index]
            output_pydantic=PRFAQOutput,
            context=[research],
            name="generate_prfaq",
        )

        design_task: Task | None = None
        if not skip_design:
            design_task = Task(
                config=self.tasks_config["generate_design_brief"],  # type: ignore[index]
                output_pydantic=DesignBriefOutput,
                context=[research, prfaq_task],
                name="generate_design_brief",
            )

        # Split BRD: structure + cost_risk in parallel, then assembly.
        # Structure needs research + prfaq (+ optional design) via context.
        # Cost_risk needs research + prfaq via context (so it can run in
        # parallel without waiting for structure). Dedicated agents per
        # task prevent Bedrock tool-use/tool-result interleaving.
        brd_structure_context = [research, prfaq_task]
        if design_task is not None:
            brd_structure_context.append(design_task)
        brd_async = not sequential_brd
        brd_structure_task = Task(
            config=self.tasks_config["brd_structure_task"],  # type: ignore[index]
            output_pydantic=BRDStructureOutput,
            context=brd_structure_context,
            name="brd_structure_task",
            agent=self.brd_agent(),
            async_execution=brd_async,
        )
        brd_cost_risk_task = Task(
            config=self.tasks_config["brd_cost_risk_task"],  # type: ignore[index]
            output_pydantic=BRDCostRiskOutput,
            context=[research, prfaq_task],
            name="brd_cost_risk_task",
            agent=self.brd_cost_risk_agent(),
            async_execution=brd_async,
        )
        brd_compliance_task = Task(
            config=self.tasks_config["brd_compliance_task"],  # type: ignore[index]
            output_pydantic=BRDComplianceOutput,
            context=[research, prfaq_task],
            name="brd_compliance_task",
            agent=self.brd_compliance_agent(),
            async_execution=brd_async,
        )
        brd_assembly_task = Task(
            config=self.tasks_config["brd_assembly_task"],  # type: ignore[index]
            output_pydantic=BRDOutput,
            context=[brd_structure_task, brd_cost_risk_task, brd_compliance_task],
            name="brd_assembly_task",
            agent=self.brd_assembly_agent(),
        )

        spec_task = Task(
            config=self.tasks_config["generate_build_spec_chained"],  # type: ignore[index]
            output_pydantic=CodingPromptOutput,
            context=[brd_assembly_task],
            name="generate_build_spec_chained",
        )

        tasks.append(prfaq_task)
        agents_list = [
            self.external_research_agent(),
            self.customer_evidence_agent(),
            self.research_agent(),
            self.prfaq_agent(),
        ]
        if design_task is not None:
            tasks.append(design_task)
            agents_list.append(self.design_brief_agent())
        tasks.extend([brd_structure_task, brd_cost_risk_task, brd_compliance_task, brd_assembly_task, spec_task])
        agents_list.append(self.brd_agent())
        agents_list.append(self.brd_cost_risk_agent())
        agents_list.append(self.brd_compliance_agent())
        agents_list.append(self.brd_assembly_agent())

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
            name="generate_build_spec_chained",
        )
        return Crew(
            agents=[self.brd_agent()],
            tasks=[brd_task, spec_task],
            process=Process.sequential,
            verbose=True,
        )

    def split_brd_crew(self) -> Crew:
        """Agent 4 only — three-task split BRD from approved PRFAQ on disk.

        Task 1 (structure) and Task 2 (cost_risk) run in PARALLEL via
        async_execution=True. Each has its own dedicated agent to
        avoid Bedrock tool-use/tool-result interleaving (same pattern
        as 4A). Task 3 (assembly) waits on both and merges into the
        final BRDOutput.

        Task 1: BRDStructureOutput (prose, user stories, requirements).
        Task 2: BRDCostRiskOutput (cost flags, risks, metrics, timeline).
        Task 3: merge both into final BRDOutput.
        """
        structure_task = Task(
            config=self.tasks_config["brd_structure_task"],  # type: ignore[index]
            output_pydantic=BRDStructureOutput,
            name="brd_structure_task",
            agent=self.brd_agent(),
            async_execution=True,
        )
        cost_risk_task = Task(
            config=self.tasks_config["brd_cost_risk_task"],  # type: ignore[index]
            output_pydantic=BRDCostRiskOutput,
            # No context=[structure_task]: cost_risk now reads PRFAQ and
            # research from disk directly so it can run in parallel.
            name="brd_cost_risk_task",
            agent=self.brd_cost_risk_agent(),
            async_execution=True,
        )
        compliance_task = Task(
            config=self.tasks_config["brd_compliance_task"],  # type: ignore[index]
            output_pydantic=BRDComplianceOutput,
            # No context=[...]: compliance reads PRFAQ and research from
            # disk via FileReaderTool so it can run in parallel.
            name="brd_compliance_task",
            agent=self.brd_compliance_agent(),
            async_execution=True,
        )
        assembly_task = Task(
            config=self.tasks_config["brd_assembly_task"],  # type: ignore[index]
            output_pydantic=BRDOutput,
            context=[structure_task, cost_risk_task, compliance_task],
            name="brd_assembly_task",
            agent=self.brd_assembly_agent(),
        )
        return Crew(
            agents=[
                self.brd_agent(),
                self.brd_cost_risk_agent(),
                self.brd_compliance_agent(),
                self.brd_assembly_agent(),
            ],
            tasks=[structure_task, cost_risk_task, compliance_task, assembly_task],
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

    def feedback_classify_crew(self) -> Crew:
        """Single-task crew that classifies one feedback item (Wave 2).

        Inputs provided via kickoff(inputs=...) must include:
            feedback_id, feedback_source, feedback_body,
            research_brief_summary, prfaq_summary, design_brief_summary,
            brd_summary, build_spec_summary, other_feedback_summaries

        Returns a CrewOutput whose tasks_output[0].pydantic is a
        FeedbackClassification instance.
        """
        classify_task = Task(
            config=self.tasks_config["feedback_classify_task"],  # type: ignore[index]
            output_pydantic=FeedbackClassification,
            name="feedback_classify_task",
            agent=self.feedback_classifier_agent(),
        )
        return Crew(
            agents=[self.feedback_classifier_agent()],
            tasks=[classify_task],
            process=Process.sequential,
            verbose=True,
        )
