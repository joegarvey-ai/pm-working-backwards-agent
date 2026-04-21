"""List the actual tool names the Dovetail MCP server exposes."""
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

# tools/list is the standard MCP discovery call
payload = {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1}
print(f"POST {base} method=tools/list")
try:
    r = httpx.post(base, json=payload, headers=headers, timeout=30)
    print(f"status={r.status_code}")
    data = r.json()
    tools = data.get("result", {}).get("tools", [])
    print(f"\nFound {len(tools)} tools:\n")
    for t in tools:
        print(f"  - {t['name']}")
        required = t.get("inputSchema", {}).get("required", [])
        props = list(t.get("inputSchema", {}).get("properties", {}).keys())
        print(f"      required args: {required}")
        print(f"      all args:      {props}")
        desc = (t.get("description", "") or "").strip().replace("\n", " ")
        print(f"      desc: {desc[:140]}...")
        print()
except Exception as e:
    print(f"EXCEPTION: {type(e).__name__}: {e}")
