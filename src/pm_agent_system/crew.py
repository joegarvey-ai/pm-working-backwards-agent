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
    DovetailCorpusTool,
    DovetailSearchTool,
    FileReaderTool,
    ObsidianReadTool,
    ObsidianSearchTool,
    OutlookMCPTool,
    PippinReadTool,
    PriorArtSearchTool,
    QuickSightTool,
    RequirementsReaderTool,
    SoftwareCatalogTool,
    StyleGuideLoaderTool,
    TavilySearchTool,
    VirtualPMCritiqueTool,
    WorkingBackwardsAICritiqueTool,
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
#   BEDROCK_MODEL_ID          inference profile ID (e.g. us.anthropic.claude-opus-4-8)
#
# The default model is Opus 4.8. Override it on the direct Anthropic path
# with ANTHROPIC_MODEL_ID (e.g. set it to "claude-fable-5" for Fable), and
# on the Bedrock path with BEDROCK_MODEL_ID.
#
# Claude on Bedrock requires the US cross-region inference profile,
# prefixed with "us." or "global.". If the user sets a plain model ID
# without the prefix, we auto-prepend "us." so on-demand invocation works.
_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()

_MODEL_ANTHROPIC = os.getenv("ANTHROPIC_MODEL_ID", "claude-opus-4-8").strip()
_MODEL_BEDROCK = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-opus-4-8").strip()
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
    orchestration module. Otherwise returns the default model (Opus 4.8,
    or ANTHROPIC_MODEL_ID / BEDROCK_MODEL_ID if set).

    Bedrock uses the AWS_BEARER_TOKEN_BEDROCK env var picked up by boto3's
    standard credential chain. Anthropic uses ANTHROPIC_API_KEY.

    Prompt caching note: the largest reusable prefixes (style guide,
    research context) flow through CrewAI's system-prompt assembly, and
    crewai's AnthropicCompletion/BedrockCompletion expose no public hook to
    attach ``cache_control`` to that prefix. Adding caching would require
    patching crewai internals, which is fragile across upgrades, so it is
    intentionally deferred until crewai supports it natively. The
    verification and judge prompts (raw Anthropic/Bedrock calls we do
    control) sit below the cache minimum, so caching them is a no-op today.
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
    """True when the canonical ``builder-mcp`` binary is on PATH.

    Auth (Midway cookie) is handled by the binary itself, so the only
    gate at this layer is whether the binary is installed and reachable.
    Outside Amazon (or before ``mcp-registry install builder-mcp``), the
    binary is absent and the tool stays unregistered.
    """
    import shutil
    return shutil.which("builder-mcp") is not None


def _outlook_mcp_enabled() -> bool:
    """True when the canonical ``aws-outlook-mcp`` binary is on PATH.

    Like builder_mcp, the tool now speaks stdio to the binary, which
    handles Midway auth itself, so the only gate here is whether the
    binary is installed and reachable. Outside Amazon it is absent and the
    tool stays unregistered.
    """
    import shutil
    return shutil.which("aws-outlook-mcp") is not None


def _wb_ai_enabled() -> bool:
    """True when the Working Backwards AI MCP client binary is on PATH.

    The critique tool speaks stdio to the internal Working Backwards AI
    service via an MCP Gateway client binary (default ``wb-ai-mcp``,
    override with ``WB_AI_MCP_BINARY``), which handles Midway auth itself.
    Absent outside Amazon, so the tool stays unregistered there.
    """
    import shutil
    binary = os.getenv("WB_AI_MCP_BINARY", "wb-ai-mcp").strip() or "wb-ai-mcp"
    return shutil.which(binary) is not None


def _software_catalog_enabled() -> bool:
    """True when the ``software-catalog-mcp`` binary is on PATH.

    The read tool speaks stdio to the internal SoftwareCatalog knowledge-graph
    server via an MCP Gateway client binary (default ``software-catalog-mcp``,
    override with ``SOFTWARE_CATALOG_MCP_BINARY``), which handles Midway auth
    itself. Absent outside Amazon, so the tool stays unregistered there.
    """
    import shutil
    binary = os.getenv("SOFTWARE_CATALOG_MCP_BINARY", "software-catalog-mcp").strip() or "software-catalog-mcp"
    return shutil.which(binary) is not None


def _quicksight_enabled() -> bool:
    """True when the ``quicksight-mcp`` binary is on PATH.

    The read tool speaks stdio to the internal QuickSight reader server via an
    MCP Gateway client binary (default ``quicksight-mcp``, override with
    ``QUICKSIGHT_MCP_BINARY``), which handles Midway auth itself. Absent outside
    Amazon, so the tool stays unregistered there.
    """
    import shutil
    binary = os.getenv("QUICKSIGHT_MCP_BINARY", "quicksight-mcp").strip() or "quicksight-mcp"
    return shutil.which(binary) is not None


def _pippin_enabled() -> bool:
    """True when the ``python-pippin-mcp`` binary is on PATH.

    The read tool speaks stdio to the internal Pippin server via an MCP Gateway
    client binary (default ``python-pippin-mcp``, override with
    ``PIPPIN_MCP_BINARY``), which handles Midway auth itself. Absent outside
    Amazon, so the tool stays unregistered there.
    """
    import shutil
    binary = os.getenv("PIPPIN_MCP_BINARY", "python-pippin-mcp").strip() or "python-pippin-mcp"
    return shutil.which(binary) is not None


def _virtual_pm_enabled() -> bool:
    """True when the ``virtual-pm-mcp`` binary is on PATH.

    The critique tool speaks stdio to the internal Virtual PM service via an MCP
    Gateway client binary (default ``virtual-pm-mcp``, override with
    ``VIRTUAL_PM_MCP_BINARY``), which handles Midway auth itself. A second
    critique lens alongside Working Backwards AI. Absent outside Amazon, so the
    tool stays unregistered there.
    """
    import shutil
    binary = os.getenv("VIRTUAL_PM_MCP_BINARY", "virtual-pm-mcp").strip() or "virtual-pm-mcp"
    return shutil.which(binary) is not None


def _dovetail_corpus_enabled() -> bool:
    """True when the Dovetail S3 export corpus is configured.

    The corpus tool reads the curated Dovetail-to-S3 export from
    ``DOVETAIL_S3_BUCKET`` via boto3 (standard credential chain). The only gate
    at this layer is whether the bucket env var is set; missing credentials are
    handled fail-soft by the tool itself at call time. Unset outside Amazon (or
    when the export is not configured), so the tool stays unregistered there.
    Complementary to the live ``DovetailSearchTool`` (``DOVETAIL_API_TOKEN``).
    """
    return bool(os.getenv("DOVETAIL_S3_BUCKET", "").strip())


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
        _dovetail_corpus = "enabled" if _dovetail_corpus_enabled() else "disabled"
        _builder = "enabled" if _builder_mcp_enabled() else "disabled"
        _outlook = "enabled" if _outlook_mcp_enabled() else "disabled"
        _wb_ai = "enabled" if _wb_ai_enabled() else "disabled"
        _software_catalog = "enabled" if _software_catalog_enabled() else "disabled"
        _quicksight = "enabled" if _quicksight_enabled() else "disabled"
        _pippin = "enabled" if _pippin_enabled() else "disabled"
        _virtual_pm = "enabled" if _virtual_pm_enabled() else "disabled"
        logger.info(
            "Optional integrations: builder_mcp=%s, outlook_mcp=%s, "
            "working_backwards_ai=%s, software_catalog=%s, quicksight=%s, "
            "pippin=%s, virtual_pm=%s, dovetail=%s, dovetail_corpus=%s",
            _builder,
            _outlook,
            _wb_ai,
            _software_catalog,
            _quicksight,
            _pippin,
            _virtual_pm,
            _dovetail,
            _dovetail_corpus,
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
        # Prior-art + technical grounding read tools. Each gated on its binary
        # so the OSS pipeline is unchanged when the binaries are absent.
        if _pippin_enabled():
            tools.append(PippinReadTool())
        if _software_catalog_enabled():
            tools.append(SoftwareCatalogTool())
        # Curated Dovetail S3 export corpus (metadata-filtered customer research),
        # attached when DOVETAIL_S3_BUCKET is set. Complementary to the live
        # Dovetail tool on customer_evidence_agent.
        if _dovetail_corpus_enabled():
            tools.append(DovetailCorpusTool())
        return Agent(
            config=self.agents_config["external_research_agent"],  # type: ignore[index]
            tools=tools,
            llm=_llm(_LARGE_MAX_TOKENS, agent_key="external_research_agent"),
            verbose=True,
        )

    @agent
    def customer_evidence_agent(self) -> Agent:
        """Customer evidence research agent (Dovetail).

        Isolated from other research agents so that async_execution=True
        does not interleave tool-use/tool-result messages across agents.

        Carries the live Dovetail MCP tool always; the curated Dovetail S3
        export corpus is attached in addition when DOVETAIL_S3_BUCKET is set
        (the two are complementary: live/real-time vs curated/metadata-filtered).
        """
        tools: list = [DovetailSearchTool()]
        if _dovetail_corpus_enabled():
            tools.append(DovetailCorpusTool())
        return Agent(
            config=self.agents_config["customer_evidence_agent"],  # type: ignore[index]
            tools=tools,
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
        if _wb_ai_enabled():
            tools.append(WorkingBackwardsAICritiqueTool())
        # Second critique lens alongside Working Backwards AI, gated on its
        # binary so the OSS pipeline is unchanged when absent.
        if _virtual_pm_enabled():
            tools.append(VirtualPMCritiqueTool())
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
        # Grounding read tools: QuickSight for real success-metric numbers,
        # software-catalog for technical context. brd_agent owns the structure
        # task (a dedicated async sibling), so attaching read tools here mirrors
        # the existing BuilderMCPTool attachment and respects async isolation
        # (each sibling has its own agent). Each gated on its binary.
        if _quicksight_enabled():
            tools.append(QuickSightTool())
        if _software_catalog_enabled():
            tools.append(SoftwareCatalogTool())
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

    def generate_from_research_crew(self) -> Crew:
        """Agent 2 only — produce a PRFAQ from an existing research brief on disk.

        Reuses the generate_prfaq task body verbatim (single source of truth
        for the PRFAQ structure) but reads the ResearchOutput from
        ``{research_path}`` via file_reader instead of from prior-task
        context. Lets a PM who already has a research brief skip Agent 1.
        """
        cfg = dict(self.tasks_config["generate_prfaq"])  # type: ignore[index]
        preamble = (
            "Before anything else, read the approved research brief from the "
            "file at {research_path} using the file_reader tool. Treat its "
            "contents as the ResearchOutput this task refers to below: it is "
            "the single source of truth for facts, competitors, customer "
            "quotes, and gaps. Wherever the steps below say 'read the "
            "ResearchOutput from prior task context', use the file you just "
            "read instead.\n\n"
        )
        cfg["description"] = preamble + cfg["description"]
        prfaq_task = Task(
            config=cfg,
            output_pydantic=PRFAQOutput,
            name="generate_prfaq",
        )
        return Crew(
            agents=[self.prfaq_agent()],
            tasks=[prfaq_task],
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

    def _build_brd_task_group(
        self,
        sequential_brd: bool = False,
        structure_context: list[Task] | None = None,
        cost_risk_context: list[Task] | None = None,
        compliance_context: list[Task] | None = None,
    ) -> list[Task]:
        """Build the four split-BRD tasks (structure, cost_risk, compliance, assembly).

        Single definition shared by ``full_pipeline_crew`` and ``split_brd_crew``
        so the topology cannot silently diverge between them. The two callers
        differ only in context wiring: in the full pipeline the three siblings
        take in-memory ``context`` from the upstream research/PRFAQ/design tasks;
        in the standalone split each sibling reads the PRFAQ and research from
        disk via FileReaderTool and takes no context, so it can run in parallel.

        Each sibling has a dedicated agent to prevent Bedrock tool-use/tool-result
        interleaving. ``sequential_brd`` runs the three siblings sequentially
        (async_execution=False) to eliminate that race entirely; the CLI
        auto-enables it on Bedrock. Returns
        ``[structure, cost_risk, compliance, assembly]``.
        """
        brd_async = not sequential_brd

        def _ctx(context: list[Task] | None) -> dict:
            # Omit the ``context`` kwarg entirely when None so the Task keeps
            # CrewAI's NOT_SPECIFIED default (as split_brd_crew relied on);
            # passing context=[] would be a different, explicit "no context".
            return {"context": context} if context is not None else {}

        structure_task = Task(
            config=self.tasks_config["brd_structure_task"],  # type: ignore[index]
            output_pydantic=BRDStructureOutput,
            name="brd_structure_task",
            agent=self.brd_agent(),
            async_execution=brd_async,
            **_ctx(structure_context),
        )
        cost_risk_task = Task(
            config=self.tasks_config["brd_cost_risk_task"],  # type: ignore[index]
            output_pydantic=BRDCostRiskOutput,
            name="brd_cost_risk_task",
            agent=self.brd_cost_risk_agent(),
            async_execution=brd_async,
            **_ctx(cost_risk_context),
        )
        compliance_task = Task(
            config=self.tasks_config["brd_compliance_task"],  # type: ignore[index]
            output_pydantic=BRDComplianceOutput,
            name="brd_compliance_task",
            agent=self.brd_compliance_agent(),
            async_execution=brd_async,
            **_ctx(compliance_context),
        )
        assembly_task = Task(
            config=self.tasks_config["brd_assembly_task"],  # type: ignore[index]
            output_pydantic=BRDOutput,
            context=[structure_task, cost_risk_task, compliance_task],
            name="brd_assembly_task",
            agent=self.brd_assembly_agent(),
        )
        return [structure_task, cost_risk_task, compliance_task, assembly_task]

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

        # Split BRD: structure + cost_risk (+ compliance) in parallel, then
        # assembly. In the full pipeline the three siblings take in-memory
        # context from the upstream research/PRFAQ (+ optional design) tasks.
        brd_structure_context = [research, prfaq_task]
        if design_task is not None:
            brd_structure_context.append(design_task)
        brd_structure_task, brd_cost_risk_task, brd_compliance_task, brd_assembly_task = (
            self._build_brd_task_group(
                sequential_brd=sequential_brd,
                structure_context=brd_structure_context,
                cost_risk_context=[research, prfaq_task],
                compliance_context=[research, prfaq_task],
            )
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

    def split_brd_crew(self, sequential_brd: bool = False) -> Crew:
        """Agent 4 only — three-task split BRD from approved PRFAQ on disk.

        Task 1 (structure), Task 2 (cost_risk), and Task 3 (compliance)
        run in PARALLEL via async_execution=True. Each has its own
        dedicated agent to avoid Bedrock tool-use/tool-result
        interleaving (same pattern as 4A). Task 4 (assembly) waits on all
        three and merges into the final BRDOutput.

        When ``sequential_brd`` is True the three siblings run
        sequentially instead of in parallel. Slower, but eliminates the
        Bedrock toolResult interleaving race; the CLI auto-enables this
        when LLM_PROVIDER=bedrock.

        Task 1: BRDStructureOutput (prose, user stories, requirements).
        Task 2: BRDCostRiskOutput (cost flags, risks, metrics, timeline).
        Task 3: BRDComplianceOutput (data handling, gates, readiness).
        Task 4: merge all three into final BRDOutput.
        """
        # No sibling context: each reads the PRFAQ and research from disk via
        # FileReaderTool so the three can run in parallel. Shares the task
        # topology with full_pipeline_crew via _build_brd_task_group.
        structure_task, cost_risk_task, compliance_task, assembly_task = (
            self._build_brd_task_group(sequential_brd=sequential_brd)
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
