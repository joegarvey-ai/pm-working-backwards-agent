"""Minimal research crew run with verbose logging to see tool calls."""
import logging
import os
import sys

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

from dotenv import load_dotenv
load_dotenv()

# Force UTF-8 for Windows
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from pm_agent_system.crew import PmAgentSystem
from pm_agent_system.models import ResearchOutput

inputs = {
    "feature_summary": "AI-powered documentation drift detection tool",
    "goals": "Detect stale documentation within 72 hours",
    "timing": "Q2 2026 POC",
    "user_summary": "11 technical writers managing 5000+ pages",
    "success_metrics": "72-hour detection target",
    "known_constraints": "AWS only, no Supabase or Firebase",
    "internal_context": "Not provided.",
    "business_context": "88% DevAssistant failure rate, partner churn",
}

print("Building crew...")
crew = PmAgentSystem().research_crew(skip_validation=True)

print(f"Agent tools: {[t.name for t in crew.agents[0].tools]}")
print("Starting kickoff...")

try:
    result = crew.kickoff(inputs=inputs)
    print(f"\nResult type: {type(result)}")
    if hasattr(result, "tasks_output"):
        for to in result.tasks_output:
            if hasattr(to, "pydantic") and to.pydantic:
                obj = to.pydantic
                if isinstance(obj, ResearchOutput):
                    ce = obj.customer_evidence
                    print(f"customer_evidence count: {len(ce)}")
                    for q in ce[:3]:
                        print(f"  quote: {q.quote[:100]}...")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
