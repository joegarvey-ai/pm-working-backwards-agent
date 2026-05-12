"""Minimal Bedrock smoke test.

Sends one short completion request to Claude on Bedrock using the
AWS_BEARER_TOKEN_BEDROCK env var for auth. Prints the response or the
error details for debugging.

Usage: uv run python scripts/bedrock_smoke_test.py
"""
import os
import sys


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()

    region = os.getenv("AWS_BEDROCK_REGION") or os.getenv("AWS_REGION", "us-east-2")
    model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-6")
    token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")

    print(f"Region:    {region}")
    print(f"Model ID:  {model_id}")
    print(f"Token set: {bool(token)} (len={len(token) if token else 0})")
    print()

    if not token:
        print("ERROR: AWS_BEARER_TOKEN_BEDROCK not set in .env")
        sys.exit(1)

    import boto3
    from botocore.config import Config

    try:
        client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=Config(read_timeout=60, connect_timeout=10),
        )
    except Exception as e:
        print(f"ERROR creating Bedrock client: {type(e).__name__}: {e}")
        sys.exit(1)

    print(f"Calling converse() on {model_id}...")
    print()

    try:
        response = client.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": "Say hello in 5 words."}],
                }
            ],
            inferenceConfig={"maxTokens": 50, "temperature": 0.2},
        )
        output = response["output"]["message"]["content"][0]["text"]
        usage = response.get("usage", {})
        print("SUCCESS")
        print(f"  Response: {output}")
        print(f"  Input tokens:  {usage.get('inputTokens', '?')}")
        print(f"  Output tokens: {usage.get('outputTokens', '?')}")
        print()
        print("Bedrock is working. You can now wire this into CrewAI.")
    except Exception as e:
        err_type = type(e).__name__
        print(f"ERROR: {err_type}: {e}")
        print()
        if "AccessDenied" in err_type or "403" in str(e):
            print("Hint: Model access not granted. Go to Bedrock console and")
            print("      check Model access for Claude Sonnet 4.6, then click Request access.")
        elif "ValidationException" in err_type:
            print("Hint: Model ID might be wrong for this region, or format")
            print("      requires a region prefix like 'us.anthropic...'")
        elif "UnrecognizedClientException" in err_type or "InvalidSignature" in err_type:
            print("Hint: Bearer token auth issue. The token might be malformed,")
            print("      expired, or not valid for this region.")
        sys.exit(1)


if __name__ == "__main__":
    main()
