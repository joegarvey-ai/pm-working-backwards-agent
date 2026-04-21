"""Measure actual Dovetail content volumes.

For each insight in the CAPE project, fetches full content and reports:
- Character count and estimated token count
- Whether it's a file-link stub or real content
- Total aggregate volume the agent would receive

Also tests what deep_search returns for typical research queries
and measures the total payload size.
"""
import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

base = os.getenv("DOVETAIL_MCP_BASE_URL", "https://dovetail.com/api/mcp")
token = os.getenv("DOVETAIL_API_TOKEN")
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def call(name, args):
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": name, "arguments": args},
        "id": 1,
    }
    r = httpx.post(base, json=payload, headers=headers, timeout=60)
    return r.json()


def est_tokens(text):
    """Rough token estimate: ~4 chars per token for English."""
    return len(text) // 4


# 1. Get ALL projects to understand workspace scope
print("=" * 60)
print("STEP 1: List all projects")
print("=" * 60)
projects = call("get_dovetail_projects", {"limit": 100})
content = projects.get("result", {}).get("content", [])
if content:
    parsed = json.loads(content[0]["text"])
    proj_list = parsed.get("data", [])
    print(f"Total projects: {len(proj_list)}")
    for p in proj_list:
        print(f"  - {p['title'] or '(untitled)'} | ID: {p['id']}")
else:
    proj_list = []
    print("No projects found")

# 2. For the CAPE project, get ALL insights and measure each
CAPE_ID = "3wf8VQS4Pa99qsJzFGLS4A"
print(f"\n{'=' * 60}")
print(f"STEP 2: All insights in CAPE project ({CAPE_ID})")
print("=" * 60)

insights_resp = call("list_project_insights", {"project_id": CAPE_ID, "limit": 100})
content = insights_resp.get("result", {}).get("content", [])
if content:
    parsed = json.loads(content[0]["text"])
    insight_list = parsed.get("data", [])
    page_info = parsed.get("page", {})
    print(f"Insights returned: {len(insight_list)}")
    print(f"Total count: {page_info.get('total_count', '?')}")
    print(f"Has more: {page_info.get('has_more', '?')}")
else:
    insight_list = []

total_chars = 0
total_tokens = 0
for ins in insight_list:
    iid = ins["id"]
    title = ins.get("title", "(untitled)")
    resp = call("get_insight_content", {"insight_id": iid})
    ic = resp.get("result", {}).get("content", [])
    if ic:
        ip = json.loads(ic[0]["text"])
        md = ip.get("data", {}).get("content_markdown", "")
    else:
        md = ""
    chars = len(md)
    toks = est_tokens(md)
    total_chars += chars
    total_tokens += toks
    is_stub = chars < 100
    print(f"  [{toks:>5} tok | {chars:>6} chars] {'STUB' if is_stub else 'REAL'} | {title}")

print(f"\nTotal insight content: {total_chars:,} chars / ~{total_tokens:,} tokens")


# 3. Get data entries and measure a sample
print(f"\n{'=' * 60}")
print(f"STEP 3: Data entries in CAPE project (sample of 10)")
print("=" * 60)

data_resp = call("list_project_data", {"project_id": CAPE_ID, "limit": 10})
content = data_resp.get("result", {}).get("content", [])
if content:
    parsed = json.loads(content[0]["text"])
    data_list = parsed.get("data", [])
    page_info = parsed.get("page", {})
    print(f"Data entries returned: {len(data_list)}")
    print(f"Total count: {page_info.get('total_count', '?')}")
else:
    data_list = []

data_total_chars = 0
for d in data_list[:10]:
    did = d["id"]
    title = d.get("title", "(untitled)")
    resp = call("get_data_content", {"data_id": did})
    dc = resp.get("result", {}).get("content", [])
    if dc:
        dp = json.loads(dc[0]["text"])
        md = dp.get("data", {}).get("content_markdown", "")
    else:
        md = ""
    chars = len(md)
    toks = est_tokens(md)
    data_total_chars += chars
    is_stub = "click to see in Dovetail" in md or chars < 100
    print(f"  [{toks:>5} tok | {chars:>6} chars] {'STUB' if is_stub else 'REAL'} | {title[:60]}")

print(f"\nSample data content: {data_total_chars:,} chars / ~{data_total_chars // 4:,} tokens")

# 4. Test deep_search output volume
print(f"\n{'=' * 60}")
print("STEP 4: deep_search output volume for typical queries")
print("=" * 60)

from pm_agent_system.tools.dovetail_research import DovetailSearchTool
tool = DovetailSearchTool()

queries = [
    "developer documentation pain points",
    "documentation staleness drift detection",
    "technical writing workflow",
]
for q in queries:
    result = tool._run(query=q, action="deep_search", limit=5)
    chars = len(result)
    toks = est_tokens(result)
    print(f"  [{toks:>5} tok | {chars:>6} chars] query: {q}")

print("\nDONE.")
