"""Inter-stage verification gate.

A lightweight quality check that runs between pipeline stages to catch
drift before it compounds. Uses Haiku for speed and cost efficiency.

Each verification checks:
1. Writing style consistency (no banned words, no em dashes)
2. Factual consistency with prior stages
3. Source attribution preservation
4. Customer problem grounding (original problem statement referenced)

Usage:
    from pm_agent_system.verification import verify_stage

    result = verify_stage(
        stage_output="<the output text from the just-completed stage>",
        input_brief="<original input brief>",
        prior_outputs={"research": "<research output>"},  # outputs from earlier stages
        stage_name="prfaq",
    )

    if not result.passed:
        print(result.summary)
        for issue in result.issues:
            print(f"  [{issue.category}] {issue.description}")
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VerificationIssue:
    category: str  # style, consistency, sources, grounding
    severity: str  # error, warning
    description: str


@dataclass
class VerificationResult:
    stage_name: str
    passed: bool
    issues: list[VerificationIssue] = field(default_factory=list)
    summary: str = ""
    raw_response: str = ""


_VERIFICATION_SYSTEM = """You are a quality gate between pipeline stages in a PM artifact generation system.

Your job is to verify that the output from one stage is ready to be consumed by the next stage. You check for four categories of issues:

1. **style**: Writing style violations. Check for:
   - Em dashes used as punctuation (should use colons or sentence breaks)
   - Banned marketing words: robust, comprehensive, powerful, cutting-edge, transformative, game-changing, revolutionary, best-in-class, seamless
   - Rhetorical contrast hooks ("not X, instead Y" as a device)
   - Rhetorical questions as section openers

2. **consistency**: Factual consistency with prior stages. Check for:
   - Numbers or statistics that contradict prior stage outputs
   - Claims that appear in this stage but have no basis in prior stages
   - Scope changes (features, timelines, or constraints that shifted)

3. **sources**: Source attribution preservation. Check for:
   - Factual claims that had citations in prior stages but lost them here
   - New factual claims introduced without any attribution
   - Citation URLs that changed or disappeared

4. **grounding**: Customer problem preservation. Check for:
   - Whether the original customer problem from the input brief is referenced
   - Whether the target user segment is preserved accurately
   - Whether success metrics align with the original goals

Return your evaluation as a JSON object:
{
  "passed": true/false,
  "issues": [
    {"category": "<style|consistency|sources|grounding>", "severity": "<error|warning>", "description": "<specific issue>"}
  ],
  "summary": "<1-2 sentence overall assessment>"
}

Rules:
- "passed" is false if ANY issue has severity "error"
- "passed" is true if there are only warnings or no issues
- Be specific: quote the problematic text when flagging style issues
- Be concise: one sentence per issue description
- Do not flag issues that are acceptable (e.g., internal metrics without external citations are fine if labeled as internal)

Return ONLY the JSON object, no other text."""


def _call_verifier(system_prompt: str, user_prompt: str) -> str:
    """Call the verification model (Haiku) and return response text."""
    provider = os.getenv("LLM_PROVIDER", "bedrock").strip().lower()

    if provider == "bedrock":
        return _call_verifier_bedrock(system_prompt, user_prompt)
    return _call_verifier_anthropic(system_prompt, user_prompt)


def _call_verifier_bedrock(system_prompt: str, user_prompt: str) -> str:
    import boto3
    from botocore.config import Config

    region = os.getenv("AWS_BEDROCK_REGION") or os.getenv("AWS_REGION", "us-east-2")
    model_id = os.getenv(
        "BEDROCK_MODEL_HAIKU", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    )
    client = boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=Config(read_timeout=60, connect_timeout=10),
    )
    response = client.converse(
        modelId=model_id,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": user_prompt}]}],
        inferenceConfig={"maxTokens": 4096, "temperature": 0.0},
    )
    return response["output"]["message"]["content"][0]["text"]


def _call_verifier_anthropic(system_prompt: str, user_prompt: str) -> str:
    import anthropic

    model_id = os.getenv("ANTHROPIC_MODEL_HAIKU", "claude-haiku-4-5-20251001")
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model_id,
        max_tokens=4096,
        temperature=0.0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


def _parse_verification_response(raw: str) -> tuple[bool, list[VerificationIssue], str]:
    """Parse the JSON verification response."""
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return False, [VerificationIssue("style", "error", "Failed to parse verifier response")], ""

    try:
        data = json.loads(raw[start:end])
        passed = data.get("passed", False)
        summary = data.get("summary", "")
        issues = [
            VerificationIssue(
                category=item.get("category", "unknown"),
                severity=item.get("severity", "warning"),
                description=item.get("description", ""),
            )
            for item in data.get("issues", [])
        ]
        return passed, issues, summary
    except (json.JSONDecodeError, KeyError):
        return False, [VerificationIssue("style", "error", "Failed to parse verifier JSON")], ""


def verify_stage(
    stage_output: str,
    input_brief: str,
    prior_outputs: dict[str, str] | None = None,
    stage_name: str = "unknown",
) -> VerificationResult:
    """Run the verification gate on a stage's output.

    Args:
        stage_output: The text output from the stage being verified.
        input_brief: The original input brief (problem statement, goals, etc.).
        prior_outputs: Dict of {stage_name: output_text} for all prior stages.
        stage_name: Name of the current stage being verified.

    Returns:
        VerificationResult with pass/fail, issues, and summary.
    """
    prior_context = ""
    if prior_outputs:
        for name, text in prior_outputs.items():
            prior_context += f"\n<prior_stage name=\"{name}\">\n{text[:10000]}\n</prior_stage>\n"

    user_prompt = f"""Verify the following {stage_name} output.

<input_brief>
{input_brief[:5000]}
</input_brief>

{prior_context if prior_context else "<no prior stages>"}

<current_stage name="{stage_name}">
{stage_output[:20000]}
</current_stage>"""

    raw = _call_verifier(_VERIFICATION_SYSTEM, user_prompt)
    passed, issues, summary = _parse_verification_response(raw)

    return VerificationResult(
        stage_name=stage_name,
        passed=passed,
        issues=issues,
        summary=summary,
        raw_response=raw,
    )
