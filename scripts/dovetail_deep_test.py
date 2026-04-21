"""Deep Dovetail content test.

Tests whether we get actual usable content (quotes, transcripts, findings)
or just titles and metadata. Exercises the full chain:
1. search_workspace -> find notes and project IDs
2. get_project_highlights -> get customer quotes from a project
3. list_project_insights -> get published insights from a project
4. get_insight_content -> get full markdown of a specific insight
5. get_data_content -> get full content of a research data entry (transcript)
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
    r = httpx.post(base, json=payload, headers=headers, timeout=30)
    return r.json()


def show(label, data, max_chars=1500):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    text = json.dumps(data, indent=2)
    print(text[:max_chars])
    if len(text) > max_chars:
        print(f"\n... ({len(text) - max_chars} more chars)")


# Step 1: Search for developer documentation content
print("STEP 1: search_workspace for 'developer documentation'")
search_result = call("search_workspace", {"query": "developer documentation", "limit": 3})
show("search_workspace results", search_result)

# Extract project_id and note_id from search results
content = search_result.get("result", {}).get("content", [])
parsed = {}
if content:
    try:
        parsed = json.loads(content[0].get("text", "{}"))
    except Exception:
        pass

notes = parsed.get("data", {}).get("notes", [])
project_id = notes[0]["project_id"] if notes else None
note_id = notes[0]["id"] if notes else None

print(f"\nExtracted project_id: {project_id}")
print(f"Extracted first note_id: {note_id}")

# Step 2: Get highlights (customer quotes) from that project
if project_id:
    print(f"\nSTEP 2: get_project_highlights for project {project_id}")
    highlights = call("get_project_highlights", {"project_id": project_id, "limit": 5})
    show("get_project_highlights results", highlights)

# Step 3: List insights from that project
if project_id:
    print(f"\nSTEP 3: list_project_insights for project {project_id}")
    insights = call("list_project_insights", {"project_id": project_id, "limit": 3})
    show("list_project_insights results", insights)

    # Extract first insight_id
    insights_content = insights.get("result", {}).get("content", [])
    insights_parsed = {}
    if insights_content:
        try:
            insights_parsed = json.loads(insights_content[0].get("text", "{}"))
        except Exception:
            pass
    insight_list = insights_parsed.get("data", [])
    insight_id = insight_list[0]["id"] if insight_list else None

    # Step 4: Get full content of that insight
    if insight_id:
        print(f"\nSTEP 4: get_insight_content for insight {insight_id}")
        insight_content = call("get_insight_content", {"insight_id": insight_id})
        show("get_insight_content results", insight_content)

# Step 5: Get full content of the first note (data entry / transcript)
if note_id:
    print(f"\nSTEP 5: get_data_content for note {note_id}")
    data_content = call("get_data_content", {"data_id": note_id})
    show("get_data_content results", data_content)

print("\n\nDONE. Check above for actual content vs metadata-only responses.")
