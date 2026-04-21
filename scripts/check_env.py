"""Quick env check. Confirms required keys are set without revealing values."""
import os
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

for k in KEYS:
    v = os.getenv(k)
    if v:
        print(f"{k}: SET (len={len(v)})")
    else:
        print(f"{k}: NOT SET")
