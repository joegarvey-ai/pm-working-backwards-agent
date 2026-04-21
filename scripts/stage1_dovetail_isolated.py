"""Stage 1: isolated Dovetail-only CrewAI test.

Minimal crew validating:
  1. Bedrock LLM provider works end-to-end through CrewAI
  2. Agent reliably calls a single tool (Dovetail) when that is its only job
  3. Output schema validates with real Vega/CAPE content

If this produces a populated customer_evidence list with real quotes,
we have proof that the three-sub-task architecture (Option A in the
planning doc) will work. If it fails, we surface the problem in a
1-agent, 1-tool, 1-task test case instead of a 10-tool monster.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

log_path = Path("output/dovetail_calls.log")
if log_path.exists():
    log_path.unlink()

from crewai import Agent, Crew, Process, Task
from pydantic import BaseModel, Field

from pm_agent_system.crew import _llm, _MODEL, _LLM_PROVIDER
from pm_agent_system.tools import DovetailSearchTool


print(f"Provider: {_LLM_PROVIDER}")
print(f"Model:    {_MODEL}")
print()


class CustomerQuote(BaseModel):
    quote: str
    source: str = Field(description="Which insight or project the quote is from")
    theme: str = Field(description="Topic the quote relates to")


class CustomerEvidenceOutput(BaseModel):
    customer_evidence: list[CustomerQuote] = Field(
        default_factory=list,
        description="Direct quotes and findings from Dovetail workspace",
    )
    dovetail_gaps: list[str] = Field(
        default_factory=list,
        description="Topics the Dovetail search could not cover",
    )


dovetail_only_agent = Agent(
    role="Amazon Customer Research Analyst",
    goal="Extract direct customer quotes and research findings from the "
         "Dovetail workspace that relate to a given topic. Return structured "
         "evidence with attribution.",
    backstory=(
        "You are an Amazon researcher who reads Dovetail workspace data every "
        "day. You know that the only way to get real customer content is to "
        "call the dovetail_research tool with action='deep_search'. You do "
        "not speculate or invent quotes. If Dovetail returns nothing useful, "
        "you say so in dovetail_gaps. Your only tool is dovetail_research."
    ),
    tools=[DovetailSearchTool()],
    llm=_llm(max_tokens=8192),
    verbose=True,
    allow_delegation=False,
)

dovetail_task = Task(
    description=(
        "Topic: technical documentation pain points experienced by Amazon "
        "developers working with Vega, Fire TV, and other device SDKs.\n\n"
        "Your job:\n"
        "1. Call dovetail_research with action='deep_search' and a query "
        "   like 'developer documentation pain points' or 'Vega documentation'.\n"
        "2. Extract direct customer quotes and quantified findings from the "
        "   insight content that comes back.\n"
        "3. Return a CustomerEvidenceOutput with at least 3 customer quotes "
        "   if Dovetail returns real insights. If insights are missing or "
        "   empty, note that in dovetail_gaps instead of fabricating quotes.\n\n"
        "Do not add Tavily data. Do not speculate. Just extract what Dovetail "
        "returns."
    ),
    expected_output=(
        "A CustomerEvidenceOutput JSON object with customer_evidence populated "
        "from real Dovetail insight content, or an explanation in dovetail_gaps "
        "if Dovetail had no relevant content."
    ),
    agent=dovetail_only_agent,
    output_pydantic=CustomerEvidenceOutput,
)

crew = Crew(
    agents=[dovetail_only_agent],
    tasks=[dovetail_task],
    process=Process.sequential,
    verbose=True,
)

print("Kicking off Stage 1 isolated Dovetail test...\n")

try:
    result = crew.kickoff(inputs={})
except Exception as e:
    print(f"\nERROR: {type(e).__name__}: {e}")
    sys.exit(1)

output = None
if hasattr(result, "pydantic") and isinstance(result.pydantic, CustomerEvidenceOutput):
    output = result.pydantic
elif hasattr(result, "tasks_output"):
    for to in result.tasks_output:
        if hasattr(to, "pydantic") and isinstance(to.pydantic, CustomerEvidenceOutput):
            output = to.pydantic
            break

print()
print("=" * 60)
print("  STAGE 1 RESULTS")
print("=" * 60)

if output is None:
    print("FAIL: could not extract CustomerEvidenceOutput from crew result.")
    print("Raw result:", result)
    sys.exit(1)

print(f"customer_evidence items: {len(output.customer_evidence)}")
print(f"dovetail_gaps items:     {len(output.dovetail_gaps)}")
print()

if output.customer_evidence:
    print("Customer Evidence:")
    for i, quote in enumerate(output.customer_evidence[:5], 1):
        print(f"  {i}. [{quote.theme}] \"{quote.quote[:150]}...\"")
        print(f"     source: {quote.source}")
    print()

if output.dovetail_gaps:
    print("Dovetail Gaps:")
    for gap in output.dovetail_gaps:
        print(f"  - {gap}")
    print()

print("Dovetail call log:")
if log_path.exists():
    lines = log_path.read_text().strip().split("\n")
    print(f"  {len(lines)} log entries")
    for line in lines:
        import json
        try:
            rec = json.loads(line)
            action = rec.get("action", "?")
            event = rec.get("event", "?")
            chars = rec.get("response_chars", "")
            char_str = f" ({chars} chars)" if chars else ""
            print(f"    {rec.get('ts', '?')} {event}:{action}{char_str}")
        except Exception:
            print(f"    {line[:100]}")
else:
    print("  NO LOG ENTRIES. The agent never called the Dovetail tool.")
    print("  This would confirm a deeper CrewAI or Bedrock integration issue.")

print()
if output.customer_evidence and log_path.exists():
    print("SUCCESS: Stage 1 validated. Proceeding to Stage 2 is safe.")
elif not log_path.exists():
    print("FAIL: tool was not called. Architecture pattern needs different approach.")
else:
    print("PARTIAL: tool was called but no evidence extracted. Check verbose logs.")
