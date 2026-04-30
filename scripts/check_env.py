"""Quick env check. Confirms required keys are set without revealing values."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

KEYS = [
    "ANTHROPIC_API_KEY",
    "TAVILY_API_KEY",
    "DOVETAIL_API_TOKEN",
    "OBSIDIAN_VAULT_PATH",
    "AWS_PRICING_REGION",
    "DEFAULT_TARGET_TOOL",
    "STYLE_GUIDE_PATH",
    "OUTPUT_DIR",
    "OUTPUT_RETENTION_DAYS",
]

# Internal Amazon MCP integration variables
MCP_KEYS = [
    "BUILDER_MCP_TOKEN",
    "BUILDER_MCP_ENDPOINT",
    "OUTLOOK_MCP_TOKEN",
    "OUTLOOK_MCP_ENDPOINT",
]

for k in KEYS:
    v = os.getenv(k)
    if v:
        print(f"{k}: SET (len={len(v)})")
    else:
        print(f"{k}: NOT SET")

print()
print("-- Internal MCP integrations --")

for k in MCP_KEYS:
    v = os.getenv(k)
    if v:
        print(f"{k}: SET (len={len(v)})")
    else:
        print(f"{k}: NOT SET")

# MIDWAY_COOKIE_PATH has three states: unset, set-and-present, set-but-missing
cookie_path = os.getenv("MIDWAY_COOKIE_PATH")
if not cookie_path:
    print("MIDWAY_COOKIE_PATH: NOT SET")
elif Path(cookie_path).exists():
    print(f"MIDWAY_COOKIE_PATH: SET (len={len(cookie_path)})")
else:
    print(f"MIDWAY_COOKIE_PATH: MISCONFIGURED (set but file missing, len={len(cookie_path)})")
