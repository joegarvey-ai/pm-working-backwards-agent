"""Direct test of Dovetail's actual search_workspace tool with a real query."""
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
    print(f"\n=== {name}({args}) ===")
    print(f"status={r.status_code}")
    body = r.text
    print(body[:2000])


# List all projects first to prove workspace access
call("get_dovetail_projects", {"limit": 5})

# Try a free-text search across the whole workspace
call("search_workspace", {"query": "developer documentation", "limit": 5})
call("search_workspace", {"query": "documentation stale", "limit": 5})
call("search_workspace", {"query": "API reference", "limit": 5})

# And list channels (a channel is an automated feedback pipeline)
call("list_channels", {"limit": 5})
