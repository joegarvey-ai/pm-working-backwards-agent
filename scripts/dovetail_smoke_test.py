"""Dovetail MCP smoke test.

Hits the Dovetail MCP endpoint with the configured token using three
actions (search, highlights, insights) and prints the outcome of each.
Does not reveal the token.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from pm_agent_system.tools.dovetail_research import DovetailSearchTool, DOVETAIL_MCP_BASE  # noqa: E402

token = os.getenv("DOVETAIL_API_TOKEN")
print(f"DOVETAIL_MCP_BASE = {DOVETAIL_MCP_BASE}")
print(f"DOVETAIL_API_TOKEN: {'SET (len=' + str(len(token)) + ')' if token else 'NOT SET'}")

if not token:
    print("No token configured. Cannot test.")
    sys.exit(1)

tool = DovetailSearchTool()

queries = [
    ("search", "developer documentation"),
    ("highlights", "documentation pain points"),
    ("insights", "developer onboarding"),
]

for action, query in queries:
    print(f"\n--- action={action!r} query={query!r} ---")
    try:
        out = tool._run(query=query, action=action)
        preview = out[:600] if isinstance(out, str) else str(out)[:600]
        print(preview)
    except Exception as e:
        print(f"EXCEPTION: {type(e).__name__}: {e}")
