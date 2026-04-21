"""Find the correct inference profile ID for Claude Sonnet 4.6."""
import os
import sys

import boto3
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()

region = os.getenv("AWS_BEDROCK_REGION", "us-east-2")

# First: list available inference profiles so we can see the exact ID
print("Listing available inference profiles in", region, "...")
bedrock_ctl = boto3.client("bedrock", region_name=region)
try:
    resp = bedrock_ctl.list_inference_profiles(maxResults=50)
    for p in resp.get("inferenceProfileSummaries", []):
        name = p.get("inferenceProfileName", "")
        pid = p.get("inferenceProfileId", "")
        if "sonnet" in name.lower() or "sonnet" in pid.lower():
            print(f"  MATCH: name='{name}' id='{pid}'")
        else:
            print(f"    {name} -> {pid}")
except Exception as e:
    print(f"Could not list profiles: {type(e).__name__}: {e}")

# Now try common inference profile ID patterns
runtime = boto3.client(
    "bedrock-runtime",
    region_name=region,
    config=Config(read_timeout=60, connect_timeout=10),
)

candidates = [
    "us.anthropic.claude-sonnet-4-6",
    "us.anthropic.claude-sonnet-4-6-v1:0",
    "us.anthropic.claude-sonnet-4-6-20260217-v1:0",
]

print("\nTrying candidate model IDs:")
for mid in candidates:
    print(f"\n--- {mid} ---")
    try:
        r = runtime.converse(
            modelId=mid,
            messages=[{"role": "user", "content": [{"text": "Say hello in 5 words."}]}],
            inferenceConfig={"maxTokens": 50, "temperature": 0.2},
        )
        out = r["output"]["message"]["content"][0]["text"]
        usage = r.get("usage", {})
        print(f"SUCCESS: {out}")
        print(f"Tokens in/out: {usage.get('inputTokens')}/{usage.get('outputTokens')}")
        print(f"\nWORKING MODEL ID: {mid}")
        print("Update BEDROCK_MODEL_ID in .env to this value.")
        sys.exit(0)
    except Exception as e:
        print(f"FAIL ({type(e).__name__}): {str(e)[:200]}")

print("\nNone of the candidate IDs worked. Check the list above for the correct profile ID.")
