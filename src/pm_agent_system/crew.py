from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from pm_agent_system.models import BRDOutput, CodingPromptOutput, PRFAQOutput, ResearchOutput
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
from crewai.llms.providers.anthropic.completion import AnthropicCompletion

# Claude Sonnet 4 defaults to 4096 max output tokens in CrewAI's
# Anthropic provider.  The BRD (12 sections + code samples + Mermaid
# diagrams) and build spec (formatted_spec alone can be 3-5K tokens)
# regularly exceed that limit, causing truncated JSON and Pydantic
# validation failures.  We bump to 16384 for agents that produce
# large structured outputs.
_MODEL = "claude-sonnet-4-20250514"
_DEFAULT_MAX_TOKENS = 8192
_LARGE_MAX_TOKENS = 16384


def _llm(max_tokens: int = _DEFAULT_MAX_TOKENS) -> AnthropicCompletion:
    return AnthropicCompletion(model=_MODEL, max_tokens=max_tokens)


@CrewBase
class PmAgentSystem:
    """PM Agent System crew.

    Three agents are scaffolded:
      - Agent 1: Research Agent (research_task)
      - Agent 2: PRFAQ Agent (generate_prfaq, revise_prfaq)
      - Agent 3: BRD + Build Spec Agent (generate_brd, revise_brd, generate_build_spec)

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
            llm=_llm(_DEFAULT_MAX_TOKENS),
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
        )

    @task
    def research_task(self) -> Task:
        return Task(
            config=self.tasks_config["research_task"],  # type: ignore[index]
            output_pydantic=ResearchOutput,
        )

    @task
    def generate_prfaq(self) -> Task:
        return Task(
            config=self.tasks_config["generate_prfaq"],  # type: ignore[index]
            output_pydantic=PRFAQOutput,
            context=[self.research_task()],
        )

    @task
    def revise_prfaq(self) -> Task:
        return Task(
            config=self.tasks_config["revise_prfaq"],  # type: ignore[index]
            output_pydantic=PRFAQOutput,
        )

    @task
    def generate_brd_chained(self) -> Task:
        return Task(
            config=self.tasks_config["generate_brd_chained"],  # type: ignore[index]
            output_pydantic=BRDOutput,
            context=[self.research_task(), self.generate_prfaq()],
        )

    @task
    def generate_brd_standalone(self) -> Task:
        return Task(
            config=self.tasks_config["generate_brd_standalone"],  # type: ignore[index]
            output_pydantic=BRDOutput,
        )

    @task
    def revise_brd(self) -> Task:
        return Task(
            config=self.tasks_config["revise_brd"],  # type: ignore[index]
            output_pydantic=BRDOutput,
        )

    @task
    def generate_build_spec_chained(self) -> Task:
        return Task(
            config=self.tasks_config["generate_build_spec_chained"],  # type: ignore[index]
            output_pydantic=CodingPromptOutput,
            context=[self.generate_brd_chained()],
        )

    @task
    def generate_build_spec_standalone(self) -> Task:
        return Task(
            config=self.tasks_config["generate_build_spec_standalone"],  # type: ignore[index]
            output_pydantic=CodingPromptOutput,
        )

    # ---------- Crews ----------

    def _research_tasks(self, skip_validation: bool = False) -> list[Task]:
        """Build the research task list, optionally prepending validate_input."""
        if skip_validation:
            return [self.research_task()]
        validation = self.validate_input()
        research = Task(
            config=self.tasks_config["research_task"],  # type: ignore[index]
            output_pydantic=ResearchOutput,
            context=[validation],
        )
        return [validation, research]

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

    def full_pipeline_crew(self, skip_validation: bool = False) -> Crew:
        """Agent 1 → Agent 2 → Agent 3 (research → PRFAQ → BRD → build spec)."""
        tasks = self._research_tasks(skip_validation)
        research = tasks[-1]
        prfaq_task = Task(
            config=self.tasks_config["generate_prfaq"],  # type: ignore[index]
            output_pydantic=PRFAQOutput,
            context=[research],
        )
        brd_task = Task(
            config=self.tasks_config["generate_brd_chained"],  # type: ignore[index]
            output_pydantic=BRDOutput,
            context=[research, prfaq_task],
        )
        spec_task = Task(
            config=self.tasks_config["generate_build_spec_chained"],  # type: ignore[index]
            output_pydantic=CodingPromptOutput,
            context=[brd_task],
        )
        tasks.extend([prfaq_task, brd_task, spec_task])
        return Crew(
            agents=[self.research_agent(), self.prfaq_agent(), self.brd_agent()],
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

    def brd_from_prfaq_crew(self) -> Crew:
        """Agent 3 only — generate BRD then build spec from approved PRFAQ on disk.

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

    def revise_brd_crew(self) -> Crew:
        """Agent 3 only (BRD revision Mode 2)."""
        return Crew(
            agents=[self.brd_agent()],
            tasks=[self.revise_brd()],
            process=Process.sequential,
            verbose=True,
        )

    def regenerate_build_spec_crew(self) -> Crew:
        """Agent 3 only — regenerate build spec from approved BRD on disk (Mode 3)."""
        return Crew(
            agents=[self.brd_agent()],
            tasks=[self.generate_build_spec_standalone()],
            process=Process.sequential,
            verbose=True,
        )
