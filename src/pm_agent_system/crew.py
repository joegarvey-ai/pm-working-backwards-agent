from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from pm_agent_system.models import BRDOutput, CodingPromptOutput, PRFAQOutput, ResearchOutput
from pm_agent_system.tools import (
    DovetailSearchTool,
    FileReaderTool,
    ObsidianReadTool,
    ObsidianSearchTool,
    StyleGuideLoaderTool,
    TavilySearchTool,
)


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
                DovetailSearchTool(),
                FileReaderTool(),
                ObsidianSearchTool(),
                ObsidianReadTool(),
            ],
            llm="anthropic/claude-sonnet-4-20250514",
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
            llm="anthropic/claude-sonnet-4-20250514",
            verbose=True,
        )

    @agent
    def brd_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["brd_agent"],  # type: ignore[index]
            tools=[
                TavilySearchTool(),
                FileReaderTool(),
                StyleGuideLoaderTool(),
                ObsidianSearchTool(),
                ObsidianReadTool(),
            ],
            llm="anthropic/claude-sonnet-4-20250514",
            verbose=True,
        )

    # ---------- Tasks ----------

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

    @crew
    def crew(self) -> Crew:
        """Default research-only crew (Agent 1). Preserves Phase 2 behavior."""
        return Crew(
            agents=[self.research_agent()],
            tasks=[self.research_task()],
            process=Process.sequential,
            verbose=True,
        )

    def research_and_generate_crew(self) -> Crew:
        """Agent 1 → Agent 2 generate (PRFAQ Mode 1)."""
        return Crew(
            agents=[self.research_agent(), self.prfaq_agent()],
            tasks=[self.research_task(), self.generate_prfaq()],
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

    def full_pipeline_crew(self) -> Crew:
        """Agent 1 → Agent 2 → Agent 3 (research → PRFAQ → BRD → build spec)."""
        return Crew(
            agents=[self.research_agent(), self.prfaq_agent(), self.brd_agent()],
            tasks=[
                self.research_task(),
                self.generate_prfaq(),
                self.generate_brd_chained(),
                self.generate_build_spec_chained(),
            ],
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
